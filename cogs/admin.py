import discord
from discord.ext import commands
from discord import app_commands
import config
from database import db
from utils.checks import is_owner, is_manager

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @is_owner()
    @app_commands.command(name="addpoints", description="Add BST to a user (Owner only)")
    async def add_points(self, interaction: discord.Interaction, user: discord.Member, amount: float):
        """Add BST to user (Owner only)"""
        try:
            if amount <= 0:
                await interaction.response.send_message(
                    "Amount must be positive.",
                    ephemeral=True
                )
                return
            
            success = await db.admin_add_points(user.id, amount, interaction.user.id)
            
            if success:
                embed = discord.Embed(
                    description=config.Design.small_caps(
                        f"added {amount} bst to {user.display_name}"
                    ),
                    color=config.Colors.SUCCESS
                )
            else:
                embed = discord.Embed(
                    description=config.Design.small_caps("failed to add points"),
                    color=config.Colors.ERROR
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @is_owner()
    @app_commands.command(name="removepoints", description="Remove BST from a user (Owner only)")
    async def remove_points(self, interaction: discord.Interaction, user: discord.Member, amount: float):
        """Remove BST from user (Owner only)"""
        try:
            if amount <= 0:
                await interaction.response.send_message(
                    "Amount must be positive.",
                    ephemeral=True
                )
                return
            
            success = await db.update_user_balance(user.id, -amount)
            
            if success:
                # Record transaction
                async with db.pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO transactions (user_id, tx_type, amount_bst, metadata)
                        VALUES ($1, 'admin_remove', $2, $3)
                    """, user.id, -amount, {"admin_id": interaction.user.id})
                
                embed = discord.Embed(
                    description=config.Design.small_caps(
                        f"removed {amount} bst from {user.display_name}"
                    ),
                    color=config.Colors.SUCCESS
                )
            else:
                embed = discord.Embed(
                    description=config.Design.small_caps("user doesn't have enough BST"),
                    color=config.Colors.ERROR
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @is_owner()
    @app_commands.command(name="resetbst", description="Reset user's BST to 0 (Owner only)")
    async def reset_bst(self, interaction: discord.Interaction, user: discord.Member):
        """Reset user's BST to 0 (Owner only)"""
        try:
            async with db.pool.acquire() as conn:
                user_data = await conn.fetchrow("SELECT bst_balance FROM users WHERE user_id = $1", user.id)
                
                if user_data and user_data['bst_balance'] > 0:
                    amount = -user_data['bst_balance']
                    await conn.execute("""
                        UPDATE users SET bst_balance = 0
                        WHERE user_id = $1
                    """, user.id)
                    
                    # Record transaction
                    await conn.execute("""
                        INSERT INTO transactions (user_id, tx_type, amount_bst, metadata)
                        VALUES ($1, 'admin_reset', $2, $3)
                    """, user.id, amount, {"admin_id": interaction.user.id})
                    
                    embed = discord.Embed(
                        description=config.Design.small_caps(
                            f"reset {user.display_name}'s bst to 0 (was {user_data['bst_balance']} bst)"
                        ),
                        color=config.Colors.SUCCESS
                    )
                else:
                    embed = discord.Embed(
                        description=config.Design.small_caps(f"{user.display_name} already has 0 bst"),
                        color=config.Colors.WARNING
                    )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @is_owner()
    @app_commands.command(name="mint", description="Mint new BST into circulation (Owner only)")
    async def mint_bst(self, interaction: discord.Interaction, amount: float):
        """Mint new BST (Owner only)"""
        try:
            if amount <= 0:
                await interaction.response.send_message(
                    "Amount must be positive.",
                    ephemeral=True
                )
                return
            
            # This would typically go to a specific user or the economy pool
            # For now, we'll just record the minting
            async with db.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO transactions (user_id, tx_type, amount_bst, metadata)
                    VALUES ($1, 'mint', $2, $3)
                """, interaction.user.id, amount, {"admin_id": interaction.user.id})
            
            embed = discord.Embed(
                description=config.Design.small_caps(
                    f"minted {amount} bst into circulation"
                ),
                color=config.Colors.SUCCESS
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @is_owner()
    @app_commands.command(name="releaseboxes", description="Release more boxes (Owner only)")
    async def release_boxes(self, interaction: discord.Interaction, box_type: str, amount: int):
        """Release more boxes (Owner only)"""
        try:
            if box_type.lower() not in ['base', 'gold']:
                await interaction.response.send_message(
                    "Invalid box type. Use 'base' or 'gold'.",
                    ephemeral=True
                )
                return
            
            if amount <= 0:
                await interaction.response.send_message(
                    "Amount must be positive.",
                    ephemeral=True
                )
                return
            
            async with db.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE box_types 
                    SET initial_release = initial_release + $1
                    WHERE box_type_id = $2
                """, amount, box_type.lower())
            
            embed = discord.Embed(
                description=config.Design.small_caps(
                    f"released {amount} more {box_type} boxes"
                ),
                color=config.Colors.SUCCESS
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @is_owner()
    @app_commands.command(name="setboxprice", description="Set box price (Owner only)")
    async def set_box_price(self, interaction: discord.Interaction, box_type: str, price: float):
        """Set box price (Owner only)"""
        try:
            if box_type.lower() not in ['base', 'gold']:
                await interaction.response.send_message(
                    "Invalid box type. Use 'base' or 'gold'.",
                    ephemeral=True
                )
                return
            
            if price <= 0:
                await interaction.response.send_message(
                    "Price must be positive.",
                    ephemeral=True
                )
                return
            
            async with db.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE box_types 
                    SET cost_bst = $1
                    WHERE box_type_id = $2
                """, price, box_type.lower())
            
            # Update config
            config.BOX_TYPES[box_type.lower()]['cost'] = price
            
            embed = discord.Embed(
                description=config.Design.small_caps(
                    f"set {box_type} box price to {price} bst"
                ),
                color=config.Colors.SUCCESS
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @is_owner()
    @app_commands.command(name="economystats", description="View economy statistics (Owner only)")
    async def economy_stats(self, interaction: discord.Interaction):
        """View economy statistics (Owner only)"""
        try:
            stats = await db.get_economy_stats()
            
            async with db.pool.acquire() as conn:
                # Get additional stats
                active_users = await conn.fetchval("""
                    SELECT COUNT(*) FROM users 
                    WHERE last_active > NOW() - INTERVAL '7 days'
                """)
                
                total_boxes_opened = await conn.fetchval("""
                    SELECT COUNT(*) FROM boxes 
                    WHERE status = 'opened'
                """)
                
                total_trades = await conn.fetchval("""
                    SELECT COUNT(*) FROM tickets 
                    WHERE status = 'completed'
                """)
                
                recent_transactions = await conn.fetch("""
                    SELECT tx_type, SUM(amount_bst) as total, COUNT(*) as count
                    FROM transactions 
                    WHERE created_at > NOW() - INTERVAL '24 hours'
                    GROUP BY tx_type
                    ORDER BY total DESC
                """)
            
            embed = discord.Embed(color=config.Colors.PRIMARY)
            
            header = config.Design.header("ECONOMY STATISTICS", 28)
            embed.description = f"\n{header}\n"
            
            # Basic stats
            basic_stats = (
                f"\n{config.Design.field('Total BST', f'{stats['total_bst']:.2f}', 20)}\n"
                f"{config.Design.field('Total Users', stats['total_users'], 20)}\n"
                f"{config.Design.field('Active Users (7d)', active_users, 20)}\n"
                f"{config.Design.field('Boxes Opened', total_boxes_opened, 20)}\n"
                f"{config.Design.field('Trades Completed', total_trades, 20)}\n"
                f"{config.Design.field('Total Transactions', stats['total_transactions'], 20)}\n"
            )
            
            embed.add_field(name="Overview", value=basic_stats, inline=False)
            
            # Recent transactions
            if recent_transactions:
                tx_content = "\n**Last 24 Hours:**\n"
                for tx in recent_transactions:
                    tx_content += f"{tx['tx_type']}: {tx['total']:.2f} BST ({tx['count']} tx)\n"
                
                embed.add_field(name="Transactions", value=tx_content, inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @is_owner()
    @app_commands.command(name="userstats", description="View detailed user statistics (Owner only)")
    async def user_stats(self, interaction: discord.Interaction, user: discord.Member):
        """View detailed user statistics (Owner only)"""
        try:
            async with db.pool.acquire() as conn:
                user_data = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user.id)
                inventory = await db.get_user_inventory(user.id)
                
                # Get transaction summary
                tx_summary = await conn.fetch("""
                    SELECT tx_type, SUM(amount_bst) as total, COUNT(*) as count
                    FROM transactions 
                    WHERE user_id = $1
                    GROUP BY tx_type
                    ORDER BY total DESC
                """, user.id)
            
            embed = discord.Embed(color=config.Colors.PRIMARY)
            
            header = config.Design.header(f"USER STATS: {user.display_name}", 28)
            embed.description = f"\n{header}\n"
            
            # User info
            user_info = (
                f"\n{config.Design.field('BST Balance', f'{user_data['bst_balance']:.2f}', 18)}\n"
                f"{config.Design.field('Total Messages', user_data['total_messages'], 18)}\n"
                f"{config.Design.field('Weekly Messages', user_data['weekly_messages'], 18)}\n"
                f"{config.Design.field('Daily Streak', user_data['daily_streak'], 18)}\n"
                f"{config.Design.field('Last Active', user_data['last_active'].strftime('%Y-%m-%d'), 18)}\n"
            )
            
            embed.add_field(name="User Data", value=user_info, inline=False)
            
            # Inventory summary
            box_count = len(inventory['boxes'])
            item_count = sum(item['quantity'] for item in inventory['items'])
            
            inventory_info = (
                f"\n{config.Design.field('Boxes Owned', box_count, 15)}\n"
                f"{config.Design.field('Unique Items', len(inventory['items']), 15)}\n"
                f"{config.Design.field('Total Items', item_count, 15)}\n"
            )
            
            embed.add_field(name="Inventory", value=inventory_info, inline=False)
            
            # Transaction summary
            if tx_summary:
                tx_info = "\n"
                for tx in tx_summary:
                    tx_info += f"{tx['tx_type']}: {tx['total']:.2f} BST\n"
                
                embed.add_field(name="Transaction Summary", value=tx_info, inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @is_owner()
    @app_commands.command(name="resetuser", description="Reset user data (Owner only)")
    async def reset_user(self, interaction: discord.Interaction, user: discord.Member):
        """Reset user data (Owner only)"""
        try:
            # Create confirmation button
            class ConfirmView(discord.ui.View):
                def __init__(self, cog, target_user):
                    super().__init__(timeout=30)
                    self.cog = cog
                    self.target_user = target_user
                    self.confirmed = False
                
                @discord.ui.button(label="Confirm Reset", style=discord.ButtonStyle.danger)
                async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.confirmed = True
                    
                    # Reset user data
                    async with db.pool.acquire() as conn:
                        await conn.execute("DELETE FROM user_items WHERE user_id = $1", self.target_user.id)
                        await conn.execute("DELETE FROM boxes WHERE owner_user_id = $1", self.target_user.id)
                        await conn.execute("""
                            UPDATE users SET 
                                bst_balance = 0,
                                total_messages = 0,
                                weekly_messages = 0,
                                daily_streak = 0,
                                last_daily_claim = NULL
                            WHERE user_id = $1
                        """, self.target_user.id)
                    
                    embed = discord.Embed(
                        description=config.Design.small_caps(
                            f"reset all data for {self.target_user.display_name}"
                        ),
                        color=config.Colors.SUCCESS
                    )
                    
                    await interaction.response.edit_message(embed=embed, view=None)
                    self.stop()
                
                @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
                async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
                    embed = discord.Embed(
                        description=config.Design.small_caps("reset cancelled"),
                        color=config.Colors.WARNING
                    )
                    await interaction.response.edit_message(embed=embed, view=None)
                    self.stop()
            
            embed = discord.Embed(
                description=config.Design.small_caps(
                    f"are you sure you want to reset all data for {user.display_name}? this cannot be undone!"
                ),
                color=config.Colors.WARNING
            )
            
            view = ConfirmView(self, user)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Admin(bot))