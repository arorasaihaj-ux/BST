import discord
from discord import app_commands
from discord.ext import commands
from database import db
import config
from typing import Optional

def is_owner():
    """Check if user is bot owner"""
    async def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.id == config.OWNER_ID
    return app_commands.check(predicate)

def is_manager():
    """Check if user has manager role"""
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id == config.OWNER_ID:
            return True
        return any(role.id in config.MANAGER_ROLES for role in interaction.user.roles)
    return app_commands.check(predicate)

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ==========================================
    # ECONOMY POOL COMMANDS (OWNER ONLY)
    # ==========================================

    @is_owner()
    @app_commands.command(name="mint", description="[OWNER] Mint BST from economy pool to user")
    async def mint_bst(
        self, 
        interaction: discord.Interaction, 
        amount: float, 
        user: Optional[discord.Member] = None,
        reason: Optional[str] = None
    ):
        """Mint BST from economy pool"""
        try:
            if amount <= 0:
                await interaction.response.send_message("❌ Amount must be positive", ephemeral=True)
                return
            
            target = user or interaction.user
            
            # Check pool balance
            pool_balance = await db.get_economy_pool()
            if amount > pool_balance:
                embed = discord.Embed(
                    title="❌ Insufficient Pool Balance",
                    description=f"**Pool Balance:** {pool_balance:.2f} BST\n**Requested:** {amount:.2f} BST",
                    color=config.Colors.ERROR
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Mint BST
            success = await db.admin_mint_bst(target.id, amount, interaction.user.id, reason)
            
            if success:
                new_pool_balance = await db.get_economy_pool()
                
                embed = discord.Embed(
                    title="✅ BST Minted",
                    color=config.Colors.SUCCESS
                )
                embed.add_field(
                    name="Amount",
                    value=f"{amount:.2f} BST",
                    inline=True
                )
                embed.add_field(
                    name="Recipient",
                    value=target.mention,
                    inline=True
                )
                embed.add_field(
                    name="Pool Remaining",
                    value=f"{new_pool_balance:.2f} BST",
                    inline=False
                )
                if reason:
                    embed.add_field(name="Reason", value=reason, inline=False)
                
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message("❌ Failed to mint BST", ephemeral=True)
                
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

    @is_owner()
    @app_commands.command(name="poolbalance", description="[OWNER] Check economy pool balance")
    async def pool_balance(self, interaction: discord.Interaction):
        """Check economy pool balance"""
        try:
            pool_balance = await db.get_economy_pool()
            circulating = await db.get_total_circulating_bst()
            
            embed = discord.Embed(
                title="🏦 Economy Pool Status",
                color=config.Colors.INFO
            )
            embed.add_field(
                name="Pool Balance",
                value=f"{pool_balance:.2f} BST",
                inline=True
            )
            embed.add_field(
                name="Circulating",
                value=f"{circulating:.2f} BST",
                inline=True
            )
            embed.add_field(
                name="Total Supply",
                value=f"{pool_balance + circulating:.2f} BST",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

    # ==========================================
    # MANAGER COMMANDS (ADD/REMOVE POINTS)
    # ==========================================

    @is_manager()
    @app_commands.command(name="addpoints", description="[MANAGER] Add BST to a user from pool")
    async def add_points(
        self, 
        interaction: discord.Interaction, 
        user: discord.Member, 
        amount: float,
        reason: Optional[str] = None
    ):
        """Add BST to user from economy pool"""
        try:
            if amount <= 0:
                await interaction.response.send_message("❌ Amount must be positive", ephemeral=True)
                return
            
            # Check pool balance
            pool_balance = await db.get_economy_pool()
            if amount > pool_balance:
                await interaction.response.send_message(
                    f"❌ Insufficient pool balance. Available: {pool_balance:.2f} BST",
                    ephemeral=True
                )
                return
            
            # Add points from pool
            success = await db.admin_add_points(user.id, amount, interaction.user.id, from_pool=True)
            
            if success:
                embed = discord.Embed(
                    title="✅ Points Added",
                    description=f"Added **{amount:.2f} BST** to {user.mention}",
                    color=config.Colors.SUCCESS
                )
                if reason:
                    embed.add_field(name="Reason", value=reason, inline=False)
                
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message("❌ Failed to add points", ephemeral=True)
                
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

    @is_manager()
    @app_commands.command(name="removepoints", description="[MANAGER] Remove BST from user (returns to pool)")
    async def remove_points(
        self, 
        interaction: discord.Interaction, 
        user: discord.Member, 
        amount: float,
        reason: Optional[str] = None
    ):
        """Remove BST from user and return to pool"""
        try:
            if amount <= 0:
                await interaction.response.send_message("❌ Amount must be positive", ephemeral=True)
                return
            
            # Remove points and return to pool
            success = await db.admin_remove_points(user.id, amount, interaction.user.id, to_pool=True)
            
            if success:
                embed = discord.Embed(
                    title="✅ Points Removed",
                    description=f"Removed **{amount:.2f} BST** from {user.mention}\nReturned to economy pool",
                    color=config.Colors.WARNING
                )
                if reason:
                    embed.add_field(name="Reason", value=reason, inline=False)
                
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message(
                    "❌ Failed to remove points. User may have insufficient balance.",
                    ephemeral=True
                )
                
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

    @is_owner()
    @app_commands.command(name="resetuser", description="[OWNER] Reset user balance to 0")
    async def reset_user(self, interaction: discord.Interaction, user: discord.Member):
        """Reset user's balance to 0"""
        try:
            success = await db.admin_reset_user(user.id, interaction.user.id)
            
            if success:
                embed = discord.Embed(
                    title="✅ User Reset",
                    description=f"Reset {user.mention}'s balance to 0 BST",
                    color=config.Colors.WARNING
                )
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message("❌ Failed to reset user", ephemeral=True)
                
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

    # ==========================================
    # ECONOMY STATS
    # ==========================================

    @is_manager()
    @app_commands.command(name="economystats", description="[MANAGER] View economy statistics")
    async def economy_stats(self, interaction: discord.Interaction):
        """View economy statistics"""
        try:
            stats = await db.get_economy_stats()
            
            embed = discord.Embed(
                title="📊 Economy Statistics",
                color=config.Colors.INFO
            )
            
            embed.add_field(
                name="💰 Pool Balance",
                value=f"{stats['pool_balance']:.2f} BST",
                inline=True
            )
            
            embed.add_field(
                name="🔄 Circulating",
                value=f"{stats['total_circulating']:.2f} BST",
                inline=True
            )
            
            embed.add_field(
                name="📈 Total Supply",
                value=f"{stats['total_supply']:.2f} BST",
                inline=False
            )
            
            embed.add_field(
                name="👥 Total Users",
                value=f"{stats['total_users']:,}",
                inline=True
            )
            
            embed.add_field(
                name="💳 Transactions",
                value=f"{stats['total_transactions']:,}",
                inline=True
            )
            
            # Calculate percentage in circulation
            if stats['total_supply'] > 0:
                circulation_pct = (stats['total_circulating'] / stats['total_supply']) * 100
                embed.add_field(
                    name="📊 In Circulation",
                    value=f"{circulation_pct:.1f}%",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

    # ==========================================
    # BOX MANAGEMENT
    # ==========================================

    @is_owner()
    @app_commands.command(name="releaseboxes", description="[OWNER] Release more mystery boxes")
    async def release_boxes(
        self, 
        interaction: discord.Interaction,
        box_type: str,
        quantity: int
    ):
        """Release additional boxes to the market"""
        try:
            if box_type not in config.BOX_TYPES:
                await interaction.response.send_message(
                    f"❌ Invalid box type. Available: {', '.join(config.BOX_TYPES.keys())}",
                    ephemeral=True
                )
                return
            
            async with db.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE box_types 
                    SET initial_release = initial_release + $1
                    WHERE box_type_id = $2
                """, quantity, box_type)
            
            embed = discord.Embed(
                title="✅ Boxes Released",
                description=f"Released {quantity} **{config.BOX_TYPES[box_type]['name']}** boxes",
                color=config.Colors.SUCCESS
            )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

    @is_owner()
    @app_commands.command(name="setboxprice", description="[OWNER] Change box price")
    async def set_box_price(
        self, 
        interaction: discord.Interaction,
        box_type: str,
        new_price: float
    ):
        """Set box price"""
        try:
            if box_type not in config.BOX_TYPES:
                await interaction.response.send_message(
                    f"❌ Invalid box type. Available: {', '.join(config.BOX_TYPES.keys())}",
                    ephemeral=True
                )
                return
            
            async with db.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE box_types 
                    SET cost_bst = $1
                    WHERE box_type_id = $2
                """, new_price, box_type)
            
            # Update config (only for current session)
            config.BOX_TYPES[box_type]['cost'] = new_price
            
            embed = discord.Embed(
                title="✅ Price Updated",
                description=f"**{config.BOX_TYPES[box_type]['name']}** price set to {new_price:.2f} BST",
                color=config.Colors.SUCCESS
            )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Admin(bot))
