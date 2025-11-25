import discord
from discord.ext import commands, tasks
from discord import app_commands
import config
from database import db
from datetime import datetime, timedelta
import asyncio

class Auctions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_auctions.start()

    @app_commands.command(name="auctions", description="View active auctions")
    async def view_auctions(self, interaction: discord.Interaction):
        """View active auctions"""
        try:
            async with db.pool.acquire() as conn:
                auctions = await conn.fetch("""
                    SELECT a.*, i.name as item_name, u.discord_tag as seller_name
                    FROM auctions a
                    JOIN items i ON a.item_id = i.item_id
                    JOIN users u ON a.seller_id = u.user_id
                    WHERE a.status = 'active' AND a.end_time > NOW()
                    ORDER BY a.end_time ASC
                """)
            
            if not auctions:
                await interaction.response.send_message(
                    "No active auctions right now.",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(color=config.Colors.PRIMARY)
            
            header = config.Design.header("ACTIVE AUCTIONS", 28)
            embed.description = f"\n{header}\n"
            
            for auction in auctions:
                time_left = auction['end_time'] - datetime.utcnow()
                hours_left = max(0, int(time_left.total_seconds() // 3600))
                minutes_left = max(0, int((time_left.total_seconds() % 3600) // 60))
                
                current_bid = auction['current_bid'] or auction['start_price']
                bidder_info = ""
                if auction['current_bidder']:
                    bidder = self.bot.get_user(auction['current_bidder'])
                    bidder_name = bidder.display_name if bidder else f"User {auction['current_bidder']}"
                    bidder_info = f"\nHigh bidder: {bidder_name}"
                
                embed.add_field(
                    name=f"🏷️ {auction['item_name']}",
                    value=(
                        f"Current bid: {current_bid} BST\n"
                        f"Time left: {hours_left}h {minutes_left}m\n"
                        f"Seller: {auction['seller_name']}\n"
                        f"ID: `{auction['auction_id']}`{bidder_info}"
                    ),
                    inline=False
                )
            
            view = discord.ui.View()
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label="Create Auction",
                custom_id="create_auction"
            ))
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.success,
                label="Place Bid",
                custom_id="place_bid"
            ))
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="createauction", description="Create a new auction")
    async def create_auction(self, interaction: discord.Interaction, item_name: str, start_price: float, duration_hours: int = 24):
        """Create a new auction"""
        try:
            if start_price <= 0:
                await interaction.response.send_message(
                    "Start price must be positive.",
                    ephemeral=True
                )
                return
            
            if duration_hours < 1 or duration_hours > 168:  # Max 1 week
                await interaction.response.send_message(
                    "Duration must be between 1 and 168 hours.",
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
                
                # Remove item from user
                await conn.execute("""
                    UPDATE user_items SET quantity = quantity - 1
                    WHERE user_id = $1 AND item_id = $2
                """, interaction.user.id, user_item['item_id'])
                
                # Create auction
                end_time = datetime.utcnow() + timedelta(hours=duration_hours)
                auction = await conn.fetchrow("""
                    INSERT INTO auctions (item_id, seller_id, start_price, end_time)
                    VALUES ($1, $2, $3, $4)
                    RETURNING *
                """, user_item['item_id'], interaction.user.id, start_price, end_time)
            
            embed = discord.Embed(
                description=config.Design.small_caps(
                    f"created auction for {item_name} starting at {start_price} bst (ends in {duration_hours} hours)"
                ),
                color=config.Colors.SUCCESS
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="bid", description="Place a bid on an auction")
    async def place_bid(self, interaction: discord.Interaction, auction_id: str, amount: float):
        """Place a bid on an auction"""
        try:
            if amount <= 0:
                await interaction.response.send_message(
                    "Bid amount must be positive.",
                    ephemeral=True
                )
                return
            
            async with db.pool.acquire() as conn:
                # Get auction
                auction = await conn.fetchrow("""
                    SELECT * FROM auctions 
                    WHERE auction_id = $1 AND status = 'active' AND end_time > NOW()
                """, auction_id)
                
                if not auction:
                    await interaction.response.send_message(
                        "Auction not found or ended.",
                        ephemeral=True
                    )
                    return
                
                # Check minimum bid
                current_bid = auction['current_bid'] or auction['start_price']
                min_bid = current_bid * 1.05  # 5% minimum increase
                
                if amount < min_bid:
                    await interaction.response.send_message(
                        f"Minimum bid is {min_bid:.2f} BST.",
                        ephemeral=True
                    )
                    return
                
                # Check user balance
                user_data = await db.get_user(interaction.user.id)
                if user_data['bst_balance'] < amount:
                    await interaction.response.send_message(
                        "Insufficient BST for bid.",
                        ephemeral=True
                    )
                    return
                
                # Refund previous bidder if any
                if auction['current_bidder']:
                    await conn.execute("""
                        UPDATE users SET bst_balance = bst_balance + $1
                        WHERE user_id = $2
                    """, auction['current_bid'], auction['current_bidder'])
                
                # Hold new bid
                await conn.execute("""
                    UPDATE users SET bst_balance = bst_balance - $1
                    WHERE user_id = $2
                """, amount, interaction.user.id)
                
                # Update auction
                await conn.execute("""
                    UPDATE auctions 
                    SET current_bid = $1, current_bidder = $2
                    WHERE auction_id = $3
                """, amount, interaction.user.id, auction_id)
                
                # Record bid
                await conn.execute("""
                    INSERT INTO auction_bids (auction_id, bidder_id, amount)
                    VALUES ($1, $2, $3)
                """, auction_id, interaction.user.id, amount)
            
            embed = discord.Embed(
                description=config.Design.small_caps(
                    f"bid {amount} bst on auction {auction_id}"
                ),
                color=config.Colors.SUCCESS
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="myauctions", description="View your auctions")
    async def my_auctions(self, interaction: discord.Interaction):
        """View user's auctions"""
        try:
            async with db.pool.acquire() as conn:
                created_auctions = await conn.fetch("""
                    SELECT a.*, i.name as item_name
                    FROM auctions a
                    JOIN items i ON a.item_id = i.item_id
                    WHERE a.seller_id = $1
                    ORDER BY a.created_at DESC
                """, interaction.user.id)
                
                bid_auctions = await conn.fetch("""
                    SELECT DISTINCT a.*, i.name as item_name, ab.amount as my_bid
                    FROM auctions a
                    JOIN auction_bids ab ON a.auction_id = ab.auction_id
                    JOIN items i ON a.item_id = i.item_id
                    WHERE ab.bidder_id = $1
                    ORDER BY ab.created_at DESC
                """, interaction.user.id)
            
            embed = discord.Embed(color=config.Colors.PRIMARY)
            
            # Created auctions
            if created_auctions:
                created_content = ""
                for auction in created_auctions:
                    status = "Active" if auction['status'] == 'active' and auction['end_time'] > datetime.utcnow() else "Ended"
                    created_content += f"{auction['item_name']} - {auction['start_price']} BST ({status})\n"
                
                embed.add_field(name="Auctions You Created", value=created_content or "None", inline=False)
            
            # Auctions bid on
            if bid_auctions:
                bid_content = ""
                for auction in bid_auctions:
                    status = "Active" if auction['status'] == 'active' and auction['end_time'] > datetime.utcnow() else "Ended"
                    is_winning = auction['current_bidder'] == interaction.user.id
                    winning_status = " 🏆" if is_winning else ""
                    bid_content += f"{auction['item_name']} - {auction['my_bid']} BST ({status}){winning_status}\n"
                
                embed.add_field(name="Auctions You Bid On", value=bid_content or "None", inline=False)
            
            if not created_auctions and not bid_auctions:
                embed.description = "You haven't participated in any auctions."
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @tasks.loop(minutes=1)
    async def check_auctions(self):
        """Check and end expired auctions"""
        try:
            async with db.pool.acquire() as conn:
                # Get expired auctions
                expired_auctions = await conn.fetch("""
                    SELECT * FROM auctions 
                    WHERE status = 'active' AND end_time <= NOW()
                """)
                
                for auction in expired_auctions:
                    if auction['current_bidder']:
                        # Auction sold
                        await conn.execute("""
                            UPDATE auctions SET status = 'sold'
                            WHERE auction_id = $1
                        """, auction['auction_id'])
                        
                        # Give item to winner
                        await conn.execute("""
                            INSERT INTO user_items (user_id, item_id, obtained_from)
                            VALUES ($1, $2, 'auction')
                            ON CONFLICT (user_id, item_id) DO UPDATE SET
                                quantity = user_items.quantity + 1
                        """, auction['current_bidder'], auction['item_id'])
                        
                        # Pay seller (minus 2% fee)
                        sale_amount = auction['current_bid'] * 0.98
                        await conn.execute("""
                            UPDATE users SET bst_balance = bst_balance + $1
                            WHERE user_id = $2
                        """, sale_amount, auction['seller_id'])
                        
                        # Record transactions
                        await conn.execute("""
                            INSERT INTO transactions (user_id, tx_type, amount_bst, metadata)
                            VALUES ($1, 'auction_sale', $2, $3)
                        """, auction['seller_id'], sale_amount, {
                            "auction_id": auction['auction_id'], 
                            "item_id": str(auction['item_id']),
                            "fee": auction['current_bid'] * 0.02
                        })
                        
                        # Notify winner and seller
                        winner = self.bot.get_user(auction['current_bidder'])
                        seller = self.bot.get_user(auction['seller_id'])
                        item = await conn.fetchrow("SELECT name FROM items WHERE item_id = $1", auction['item_id'])
                        
                        if winner:
                            try:
                                embed = discord.Embed(
                                    description=config.Design.small_caps(
                                        f"you won the auction for {item['name']} with bid of {auction['current_bid']} bst"
                                    ),
                                    color=config.Colors.SUCCESS
                                )
                                await winner.send(embed=embed)
                            except:
                                pass
                        
                        if seller:
                            try:
                                embed = discord.Embed(
                                    description=config.Design.small_caps(
                                        f"your auction for {item['name']} sold for {auction['current_bid']} bst (you received {sale_amount} bst after fees)"
                                    ),
                                    color=config.Colors.SUCCESS
                                )
                                await seller.send(embed=embed)
                            except:
                                pass
                    
                    else:
                        # Auction ended with no bids - return item to seller
                        await conn.execute("""
                            UPDATE auctions SET status = 'expired'
                            WHERE auction_id = $1
                        """, auction['auction_id'])
                        
                        await conn.execute("""
                            INSERT INTO user_items (user_id, item_id, obtained_from)
                            VALUES ($1, $2, 'auction_return')
                            ON CONFLICT (user_id, item_id) DO UPDATE SET
                                quantity = user_items.quantity + 1
                        """, auction['seller_id'], auction['item_id'])
                        
                        # Notify seller
                        seller = self.bot.get_user(auction['seller_id'])
                        item = await conn.fetchrow("SELECT name FROM items WHERE item_id = $1", auction['item_id'])
                        
                        if seller:
                            try:
                                embed = discord.Embed(
                                    description=config.Design.small_caps(
                                        f"your auction for {item['name']} ended with no bids - item returned to you"
                                    ),
                                    color=config.Colors.WARNING
                                )
                                await seller.send(embed=embed)
                            except:
                                pass
                
        except Exception as e:
            print(f"Error in auction check: {e}")

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Handle auction button interactions"""
        if not interaction.data or 'custom_id' not in interaction.data:
            return
        
        custom_id = interaction.data['custom_id']
        
        if custom_id == "create_auction":
            # Send modal for creating auction
            class AuctionModal(discord.ui.Modal, title="Create Auction"):
                item_name = discord.ui.TextInput(
                    label="Item Name",
                    placeholder="Enter the item name...",
                    max_length=100
                )
                start_price = discord.ui.TextInput(
                    label="Start Price (BST)",
                    placeholder="Enter starting price...",
                    max_length=10
                )
                duration = discord.ui.TextInput(
                    label="Duration (hours)",
                    placeholder="Enter duration in hours...",
                    default="24",
                    max_length=3
                )
                
                async def on_submit(self, interaction: discord.Interaction):
                    try:
                        price = float(self.start_price.value)
                        hours = int(self.duration.value)
                        await self.cog.create_auction(interaction, self.item_name.value, price, hours)
                    except ValueError:
                        await interaction.response.send_message(
                            "Invalid price or duration.",
                            ephemeral=True
                        )
            
            AuctionModal.cog = self
            await interaction.response.send_modal(AuctionModal())
            
        elif custom_id == "place_bid":
            # Send modal for placing bid
            class BidModal(discord.ui.Modal, title="Place Bid"):
                auction_id = discord.ui.TextInput(
                    label="Auction ID",
                    placeholder="Enter the auction ID...",
                    max_length=100
                )
                amount = discord.ui.TextInput(
                    label="Bid Amount (BST)",
                    placeholder="Enter your bid amount...",
                    max_length=10
                )
                
                async def on_submit(self, interaction: discord.Interaction):
                    try:
                        amount = float(self.amount.value)
                        await self.cog.place_bid(interaction, self.auction_id.value, amount)
                    except ValueError:
                        await interaction.response.send_message(
                            "Invalid bid amount.",
                            ephemeral=True
                        )
            
            BidModal.cog = self
            await interaction.response.send_modal(BidModal())

    def cog_unload(self):
        self.check_auctions.cancel()

async def setup(bot):
    await bot.add_cog(Auctions(bot))