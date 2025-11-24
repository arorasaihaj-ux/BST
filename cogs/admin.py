import discord
from discord.ext import commands
import config
from database import db

def is_owner():
    """Check if user is the bot owner"""
    def predicate(ctx):
        return ctx.author.id == config.OWNER_ID
    return commands.check(predicate)

def is_manager():
    """Check if user is a manager or owner"""
    def predicate(ctx):
        if ctx.author.id == config.OWNER_ID:
            return True
        if any(role.id in config.MANAGER_ROLES for role in ctx.author.roles):
            return True
        return False
    return commands.check(predicate)

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command(name="admin", description="Admin control panel")
    @is_owner()
    async def admin_panel(self, ctx):
        """Display admin panel"""
        embed = discord.Embed(color=config.Colors.PRIMARY)
        
        header = config.Design.header("ADMIN PANEL", 28)
        embed.description = f"```\n{header}\n```"
        
        # Stats
        async with db.pool.acquire() as conn:
            total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
            total_bst = await conn.fetchval("SELECT SUM(bst_balance) FROM users")
            total_boxes = await conn.fetchval("SELECT COUNT(*) FROM boxes WHERE status = 'stored'")
            active_trades = await conn.fetchval("SELECT COUNT(*) FROM trades WHERE status = 'pending'")
        
        stats = (
            f"\n{config.Design.section('STATISTICS')}\n"
            f"{config.Design.field('total users', str(total_users), 20)}\n"
            f"{config.Design.field('total bst', f'{total_bst:.2f}', 20)}\n"
            f"{config.Design.field('stored boxes', str(total_boxes), 20)}\n"
            f"{config.Design.field('active trades', str(active_trades), 20)}\n"
        )
        
        embed.add_field(name="\u200b", value=stats, inline=False)
        
        # Create view with admin actions
        view = AdminView(self.bot)
        
        await ctx.send(embed=embed, view=view)
    
    @commands.hybrid_command(name="mint", description="Mint BST to a user")
    @is_owner()
    async def mint_bst(self, ctx, user: discord.Member, amount: float):
        """Mint BST (owner only)"""
        if amount <= 0:
            embed = discord.Embed(
                description=config.Design.small_caps("amount must be positive"),
                color=config.Colors.ERROR
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        await db.update_balance(user.id, amount, 'add')
        await db.log_action(ctx.author.id, 'mint', user.id, {'amount': amount})
        
        embed = discord.Embed(color=config.Colors.SUCCESS)
        
        header = config.Design.header("MINTED", 28)
        embed.description = f"```\n{header}\n```"
        
        content = (
            f"\n{config.Design.field('user', user.display_name, 20)}\n"
            f"{config.Design.field('amount', f'{amount:.2f} BST', 20)}\n"
        )
        
        embed.add_field(name="Success", value=content, inline=False)
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name="remove", description="Remove BST from a user")
    @is_owner()
    async def remove_bst(self, ctx, user: discord.Member, amount: float):
        """Remove BST (owner only)"""
        if amount <= 0:
            embed = discord.Embed(
                description=config.Design.small_caps("amount must be positive"),
                color=config.Colors.ERROR
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        balance = await db.get_balance(user.id)
        if balance < amount:
            embed = discord.Embed(
                description=config.Design.small_caps("user doesn't have enough bst"),
                color=config.Colors.ERROR
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        await db.update_balance(user.id, amount, 'subtract')
        await db.log_action(ctx.author.id, 'remove', user.id, {'amount': amount})
        
        embed = discord.Embed(color=config.Colors.SUCCESS)
        
        header = config.Design.header("REMOVED", 28)
        embed.description = f"```\n{header}\n```"
        
        content = (
            f"\n{config.Design.field('user', user.display_name, 20)}\n"
            f"{config.Design.field('amount', f'{amount:.2f} BST', 20)}\n"
        )
        
        embed.add_field(name="Success", value=content, inline=False)
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name="release", description="Release more boxes")
    @is_owner()
    async def release_boxes(self, ctx, box_type: str, amount: int):
        """Release more box supply"""
        if amount <= 0:
            embed = discord.Embed(
                description=config.Design.small_caps("amount must be positive"),
                color=config.Colors.ERROR
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        async with db.pool.acquire() as conn:
            box = await conn.fetchrow(
                "SELECT * FROM box_types WHERE short_name = $1",
                box_type
            )
            
            if not box:
                embed = discord.Embed(
                    description=config.Design.small_caps("box type not found"),
                    color=config.Colors.ERROR
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            await conn.execute(
                "UPDATE box_types SET initial_release = initial_release + $1 WHERE box_type_id = $2",
                amount, box['box_type_id']
            )
        
        await db.log_action(ctx.author.id, 'release_boxes', None, 
                           {'box_type': box_type, 'amount': amount})
        
        embed = discord.Embed(color=config.Colors.SUCCESS)
        
        header = config.Design.header("RELEASED", 28)
        embed.description = f"```\n{header}\n```"
        
        content = (
            f"\n{config.Design.field('box type', box['name'], 20)}\n"
            f"{config.Design.field('amount', str(amount), 20)}\n"
            f"{config.Design.field('new total', str(box['initial_release'] + amount), 20)}\n"
        )
        
        embed.add_field(name="Success", value=content, inline=False)
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name="award", description="Award BST to a user")
    @is_manager()
    async def award_bst(self, ctx, user: discord.Member, amount: float, reason: str = "Manual award"):
        """Award BST (manager command)"""
        if amount <= 0:
            embed = discord.Embed(
                description=config.Design.small_caps("amount must be positive"),
                color=config.Colors.ERROR
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        await db.update_balance(user.id, amount, 'add')
        await db.log_action(ctx.author.id, 'award', user.id, 
                           {'amount': amount, 'reason': reason})
        
        embed = discord.Embed(color=config.Colors.SUCCESS)
        
        header = config.Design.header("AWARDED", 28)
        embed.description = f"```\n{header}\n```"
        
        content = (
            f"\n{config.Design.field('user', user.display_name, 20)}\n"
            f"{config.Design.field('amount', f'{amount:.2f} BST', 20)}\n"
            f"{config.Design.field('reason', reason, 20)}\n"
        )
        
        embed.add_field(name="Success", value=content, inline=False)
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name="reset", description="Reset a user's inventory")
    @is_owner()
    async def reset_user(self, ctx, user: discord.Member):
        """Reset user inventory (owner only)"""
        async with db.pool.acquire() as conn:
            async with conn.transaction():
                # Delete boxes
                await conn.execute(
                    "DELETE FROM boxes WHERE owner_user_id = $1",
                    user.id
                )
                
                # Delete items
                await conn.execute(
                    "DELETE FROM user_items WHERE user_id = $1",
                    user.id
                )
                
                # Reset balance
                await conn.execute(
                    "UPDATE users SET bst_balance = 0, weekly_bst_earned = 0, invite_bst_earned = 0 WHERE user_id = $1",
                    user.id
                )
        
        await db.log_action(ctx.author.id, 'reset_user', user.id, {})
        
        embed = discord.Embed(
            description=config.Design.small_caps(f"reset {user.display_name}'s inventory"),
            color=config.Colors.SUCCESS
        )
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name="logs", description="View recent admin logs")
    @is_owner()
    async def view_logs(self, ctx, limit: int = 10):
        """View admin action logs"""
        async with db.pool.acquire() as conn:
            logs = await conn.fetch(
                """SELECT l.*, u.discord_tag
                   FROM logs l
                   LEFT JOIN users u ON l.actor_id = u.user_id
                   ORDER BY l.created_at DESC
                   LIMIT $1""",
                limit
            )
        
        if not logs:
            embed = discord.Embed(
                description=config.Design.small_caps("no logs found"),
                color=config.Colors.INFO
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(color=config.Colors.PRIMARY)
        
        header = config.Design.header("ADMIN LOGS", 28)
        embed.description = f"```\n{header}\n```"
        
        for log in logs:
            actor = log['discord_tag'] or f"User {log['actor_id']}"
            timestamp = log['created_at'].strftime("%Y-%m-%d %H:%M")
            
            log_text = (
                f"\n{config.Design.section(log['action'].upper())}\n"
                f"{config.Design.field('actor', actor, 20)}\n"
                f"{config.Design.field('time', timestamp, 20)}\n"
            )
            
            embed.add_field(name="\u200b", value=log_text, inline=False)
        
        await ctx.send(embed=embed)

class AdminView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=300)
        self.bot = bot
    
    @discord.ui.button(label="View Stats", style=discord.ButtonStyle.primary)
    async def view_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        """View detailed statistics"""
        await interaction.response.defer(ephemeral=True)
        
        async with db.pool.acquire() as conn:
            # Detailed stats
            total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
            total_bst = await conn.fetchval("SELECT SUM(bst_balance) FROM users")
            total_boxes_purchased = await conn.fetchval(
                "SELECT COUNT(*) FROM transactions WHERE tx_type = 'purchase'"
            )
            total_boxes_opened = await conn.fetchval(
                "SELECT COUNT(*) FROM open_logs"
            )
            total_trades = await conn.fetchval("SELECT COUNT(*) FROM trades WHERE status = 'completed'")
            
            # Top earners
            top_earners = await conn.fetch(
                """SELECT user_id, discord_tag, bst_balance 
                   FROM users 
                   ORDER BY bst_balance DESC 
                   LIMIT 5"""
            )
        
        embed = discord.Embed(color=config.Colors.INFO)
        
        header = config.Design.header("STATISTICS", 28)
        embed.description = f"```\n{header}\n```"
        
        general_stats = (
            f"\n{config.Design.section('GENERAL')}\n"
            f"{config.Design.field('total users', str(total_users), 20)}\n"
            f"{config.Design.field('total bst', f'{total_bst:.2f}', 20)}\n"
            f"{config.Design.field('boxes purchased', str(total_boxes_purchased), 20)}\n"
            f"{config.Design.field('boxes opened', str(total_boxes_opened), 20)}\n"
            f"{config.Design.field('completed trades', str(total_trades), 20)}\n"
        )
        
        embed.add_field(name="\u200b", value=general_stats, inline=False)
        
        # Top earners
        top_text = f"\n{config.Design.section('TOP EARNERS')}\n"
        for i, user in enumerate(top_earners, 1):
            user_obj = self.bot.get_user(user['user_id'])
            name = user_obj.display_name if user_obj else user['discord_tag'] or f"User {user['user_id']}"
            top_text += f"{config.Design.item(f'{i}. {name}', f'{user["bst_balance"]:.2f} BST')}\n"
        
        embed.add_field(name="\u200b", value=top_text, inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="Refresh Panel", style=discord.ButtonStyle.secondary)
    async def refresh_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Refresh the admin panel"""
        await interaction.response.defer(ephemeral=True)
        
        # Get updated stats
        async with db.pool.acquire() as conn:
            total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
            total_bst = await conn.fetchval("SELECT SUM(bst_balance) FROM users")
            total_boxes = await conn.fetchval("SELECT COUNT(*) FROM boxes WHERE status = 'stored'")
            active_trades = await conn.fetchval("SELECT COUNT(*) FROM trades WHERE status = 'pending'")
        
        embed = discord.Embed(color=config.Colors.PRIMARY)
        
        header = config.Design.header("ADMIN PANEL", 28)
        embed.description = f"```\n{header}\n```"
        
        stats = (
            f"\n{config.Design.section('STATISTICS')}\n"
            f"{config.Design.field('total users', str(total_users), 20)}\n"
            f"{config.Design.field('total bst', f'{total_bst:.2f}', 20)}\n"
            f"{config.Design.field('stored boxes', str(total_boxes), 20)}\n"
            f"{config.Design.field('active trades', str(active_trades), 20)}\n"
        )
        
        embed.add_field(name="\u200b", value=stats, inline=False)
        
        await interaction.message.edit(embed=embed, view=self)
        await interaction.followup.send(
            config.Design.small_caps("panel refreshed"),
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(Admin(bot))