import discord
from discord.ext import commands, tasks
from discord import app_commands
import config
from database import db
from datetime import datetime, timedelta

class Rentals(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_rentals.start()

    @app_commands.command(name="rentals", description="View available rentals")
    async def view_rentals(self, interaction: discord.Interaction):
        """View available rentals"""
        try:
            async with db.pool.acquire() as conn:
                rentals = await conn.fetch("""
                    SELECT r.*, i.name as item_name, u.discord_tag as owner_name
                    FROM rentals r
                    JOIN items i ON r.item_id = i.item_id
                    JOIN users u ON r.owner_id = u.user_id
                    WHERE r.status = 'active'
                    ORDER BY r.daily_price ASC
                """)
            
            if not rentals:
                await interaction.response.send_message(
                    "No items available for rent right now.",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(color=config.Colors.PRIMARY)
            
            header = config.Design.header("AVAILABLE RENTALS", 28)
            embed.description = f"\n{header}\n"
            
            for rental in rentals:
                total_cost = rental['daily_price'] * rental['duration_days']
                
                embed.add_field(
                    name=f"🏠 {rental['item_name']}",
                    value=(
                        f"Daily: {rental['daily_price']} BST\n"
                        f"Duration: {rental['duration_days']} days\n"
                        f"Total: {total_cost} BST\n"
                        f"Owner: {rental['owner_name']}\n"
                        f"ID: `{rental['rental_id']}`"
                    ),
                    inline=False
                )
            
            view = discord.ui.View()
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label="List Item for Rent",
                custom_id="list_rental"
            ))
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.success,
                label="Rent Item",
                custom_id="rent_item"
            ))
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="listrental", description="List an item for rent")
    async def list_rental(self, interaction: discord.Interaction, item_name: str, daily_price: float, duration_days: int = 7):
        """List an item for rent"""
        try:
            if daily_price <= 0:
                await interaction.response.send_message(
                    "Daily price must be positive.",
                    ephemeral=True
                )
                return
            
            if duration_days < 1 or duration_days > 30:
                await interaction.response.send_message(
                    "Duration must be between 1 and 30 days.",
                    ephemeral=True
                )
                return
            
            async with db.pool.acquire() as conn:
                # Check if user has the item
                user_item = await conn.fetchrow("""
                    SELECT ui.*, i.item_id 
                    FROM user_items ui
                    JOIN items i ON ui.item_id = i.item_id
                    WHERE ui.user_id = $1 AND i.name = $2 AND ui.quantity > 0
                """, interaction.user.id, item_name)
                
                if not user_item:
                    await interaction.response.send_message(
                        f"You don't have {item_name}.",
                        ephemeral=True
                    )
                    return
                
                # Remove item from user (held in escrow)
                await conn.execute("""
                    UPDATE user_items SET quantity = quantity - 1
                    WHERE user_id = $1 AND item_id = $2
                """, interaction.user.id, user_item['item_id'])
                
                # Create rental listing
                total_price = daily_price * duration_days
                rental = await conn.fetchrow("""
                    INSERT INTO rentals (item_id, owner_id, daily_price, duration_days, total_price)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING *
                """, user_item['item_id'], interaction.user.id, daily_price, duration_days, total_price)
            
            embed = discord.Embed(
                description=config.Design.small_caps(
                    f"listed {item_name} for rent at {daily_price} bst/day for {duration_days} days"
                ),
                color=config.Colors.SUCCESS
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="rent", description="Rent an item")
    async def rent_item(self, interaction: discord.Interaction, rental_id: str):
        """Rent an item"""
        try:
            async with db.pool.acquire() as conn:
                # Get rental
                rental = await conn.fetchrow("""
                    SELECT * FROM rentals 
                    WHERE rental_id = $1 AND status = 'active'
                """, rental_id)
                
                if not rental:
                    await interaction.response.send_message(
                        "Rental not available.",
                        ephemeral=True
                    )
                    return
                
                # Check user balance
                user_data = await db.get_user(interaction.user.id)
                if user_data['bst_balance'] < rental['total_price']:
                    await interaction.response.send_message(
                        f"Insufficient BST. Rental costs {rental['total_price']} BST.",
                        ephemeral=True
                    )
                    return
                
                # Process payment
                await conn.execute("""
                    UPDATE users SET bst_balance = bst_balance - $1
                    WHERE user_id = $2
                """, rental['total_price'], interaction.user.id)
                
                # Pay owner (minus 10% fee)
                owner_amount = rental['total_price'] * 0.90
                await conn.execute("""
                    UPDATE users SET bst_balance = bst_balance + $1
                    WHERE user_id = $2
                """, owner_amount, rental['owner_id'])
                
                # Update rental
                start_date = datetime.utcnow()
                end_date = start_date + timedelta(days=rental['duration_days'])
                
                await conn.execute("""
                    UPDATE rentals 
                    SET renter_id = $1, status = 'rented', start_date = $2, end_date = $3
                    WHERE rental_id = $4
                """, interaction.user.id, start_date, end_date, rental_id)
                
                # Give item to renter temporarily
                await conn.execute("""
                    INSERT INTO user_items (user_id, item_id, obtained_from)
                    VALUES ($1, $2, 'rental')
                    ON CONFLICT (user_id, item_id) DO UPDATE SET
                        quantity = user_items.quantity + 1
                """, interaction.user.id, rental['item_id'])
                
                # Record transactions
                await conn.execute("""
                    INSERT INTO transactions (user_id, tx_type, amount_bst, metadata)
                    VALUES ($1, 'rental_payment', $2, $3)
                """, interaction.user.id, -rental['total_price'], {
                    "rental_id": rental_id,
                    "item_id": str(rental['item_id']),
                    "duration": rental['duration_days']
                })
                
                await conn.execute("""
                    INSERT INTO transactions (user_id, tx_type, amount_bst, metadata)
                    VALUES ($1, 'rental_income', $2, $3)
                """, rental['owner_id'], owner_amount, {
                    "rental_id": rental_id,
                    "fee": rental['total_price'] * 0.10
                })
            
            item = await conn.fetchrow("SELECT name FROM items WHERE item_id = $1", rental['item_id'])
            
            embed = discord.Embed(
                description=config.Design.small_caps(
                    f"rented {item['name']} for {rental['duration_days']} days at total cost of {rental['total_price']} bst"
                ),
                color=config.Colors.SUCCESS
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @tasks.loop(hours=1)
    async def check_rentals(self):
        """Check and process rental expirations"""
        try:
            async with db.pool.acquire() as conn:
                # Get expired rentals
                expired_rentals = await conn.fetch("""
                    SELECT * FROM rentals 
                    WHERE status = 'rented' AND end_date <= NOW()
                """)
                
                for rental in expired_rentals:
                    # Remove item from renter
                    await conn.execute("""
                        UPDATE user_items SET quantity = quantity - 1
                        WHERE user_id = $1 AND item_id = $2
                    """, rental['renter_id'], rental['item_id'])
                    
                    # Return item to owner
                    await conn.execute("""
                        INSERT INTO user_items (user_id, item_id, obtained_from)
                        VALUES ($1, $2, 'rental_return')
                        ON CONFLICT (user_id, item_id) DO UPDATE SET
                            quantity = user_items.quantity + 1
                    """, rental['owner_id'], rental['item_id'])
                    
                    # Update rental status
                    await conn.execute("""
                        UPDATE rentals SET status = 'completed'
                        WHERE rental_id = $1
                    """, rental['rental_id'])
                    
                    # Notify parties
                    renter = self.bot.get_user(rental['renter_id'])
                    owner = self.bot.get_user(rental['owner_id'])
                    item = await conn.fetchrow("SELECT name FROM items WHERE item_id = $1", rental['item_id'])
                    
                    if renter:
                        try:
                            embed = discord.Embed(
                                description=config.Design.small_caps(
                                    f"your rental of {item['name']} has ended - item returned to owner"
                                ),
                                color=config.Colors.INFO
                            )
                            await renter.send(embed=embed)
                        except:
                            pass
                    
                    if owner:
                        try:
                            embed = discord.Embed(
                                description=config.Design.small_caps(
                                    f"your {item['name']} has been returned from rental"
                                ),
                                color=config.Colors.INFO
                            )
                            await owner.send(embed=embed)
                        except:
                            pass
                
        except Exception as e:
            print(f"Error in rental check: {e}")

    @app_commands.command(name="myrentals", description="View your rental activity")
    async def my_rentals(self, interaction: discord.Interaction):
        """View user's rental activity"""
        try:
            async with db.pool.acquire() as conn:
                owned_rentals = await conn.fetch("""
                    SELECT r.*, i.name as item_name
                    FROM rentals r
                    JOIN items i ON r.item_id = i.item_id
                    WHERE r.owner_id = $1
                    ORDER BY r.created_at DESC
                """, interaction.user.id)
                
                rented_rentals = await conn.fetch("""
                    SELECT r.*, i.name as item_name
                    FROM rentals r
                    JOIN items i ON r.item_id = i.item_id
                    WHERE r.renter_id = $1
                    ORDER BY r.created_at DESC
                """, interaction.user.id)
            
            embed = discord.Embed(color=config.Colors.PRIMARY)
            
            # Owned rentals
            if owned_rentals:
                owned_content = ""
                for rental in owned_rentals:
                    status = rental['status'].title()
                    if rental['status'] == 'rented':
                        time_left = rental['end_date'] - datetime.utcnow()
                        days_left = max(0, int(time_left.total_seconds() // 86400))
                        status = f"Rented ({days_left}d left)"
                    
                    owned_content += f"{rental['item_name']} - {rental['daily_price']} BST/day ({status})\n"
                
                embed.add_field(name="Items You're Renting Out", value=owned_content or "None", inline=False)
            
            # Rented items
            if rented_rentals:
                rented_content = ""
                for rental in rented_rentals:
                    status = rental['status'].title()
                    if rental['status'] == 'rented':
                        time_left = rental['end_date'] - datetime.utcnow()
                        days_left = max(0, int(time_left.total_seconds() // 86400))
                        status = f"Rented ({days_left}d left)"
                    
                    rented_content += f"{rental['item_name']} - {rental['daily_price']} BST/day ({status})\n"
                
                embed.add_field(name="Items You're Renting", value=rented_content or "None", inline=False)
            
            if not owned_rentals and not rented_rentals:
                embed.description = "You haven't participated in any rentals."
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Handle rental button interactions"""
        if not interaction.data or 'custom_id' not in interaction.data:
            return
        
        custom_id = interaction.data['custom_id']
        
        if custom_id == "list_rental":
            # Send modal for listing rental
            class RentalModal(discord.ui.Modal, title="List Item for Rent"):
                item_name = discord.ui.TextInput(
                    label="Item Name",
                    placeholder="Enter the item name...",
                    max_length=100
                )
                daily_price = discord.ui.TextInput(
                    label="Daily Price (BST)",
                    placeholder="Enter daily rental price...",
                    max_length=10
                )
                duration = discord.ui.TextInput(
                    label="Duration (days)",
                    placeholder="Enter rental duration in days...",
                    default="7",
                    max_length=2
                )
                
                async def on_submit(self, interaction: discord.Interaction):
                    try:
                        price = float(self.daily_price.value)
                        days = int(self.duration.value)
                        await self.cog.list_rental(interaction, self.item_name.value, price, days)
                    except ValueError:
                        await interaction.response.send_message(
                            "Invalid price or duration.",
                            ephemeral=True
                        )
            
            RentalModal.cog = self
            await interaction.response.send_modal(RentalModal())
            
        elif custom_id == "rent_item":
            # Send modal for renting
            class RentModal(discord.ui.Modal, title="Rent Item"):
                rental_id = discord.ui.TextInput(
                    label="Rental ID",
                    placeholder="Enter the rental ID...",
                    max_length=100
                )
                
                async def on_submit(self, interaction: discord.Interaction):
                    await self.cog.rent_item(interaction, self.rental_id.value)
            
            RentModal.cog = self
            await interaction.response.send_modal(RentModal())

    def cog_unload(self):
        self.check_rentals.cancel()

async def setup(bot):
    await bot.add_cog(Rentals(bot))