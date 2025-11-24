import discord
from discord.ext import commands
import config
from database import db

class Commands(commands.Cog):
    """Handle command-only channel restrictions"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Delete non-command messages in command channel"""
        # Ignore bots
        if message.author.bot:
            return
        
        # Check if in command channel
        if not hasattr(config, 'COMMAND_CHANNEL_ID') or not config.COMMAND_CHANNEL_ID:
            return
        
        if message.channel.id != config.COMMAND_CHANNEL_ID:
            return
        
        # Check if it's a valid command
        ctx = await self.bot.get_context(message)
        
        # If not a command, delete it
        if not ctx.valid:
            try:
                await message.delete()
                
                # Send ephemeral warning
                embed = discord.Embed(
                    description=config.Design.small_caps("this channel is for commands only"),
                    color=config.Colors.WARNING
                )
                
                warning = await message.channel.send(
                    f"{message.author.mention}",
                    embed=embed,
                    delete_after=5
                )
            except:
                pass
    
    @commands.hybrid_command(name="bal", description="Check BST balance")
    async def balance_short(self, ctx, user: discord.Member = None):
        """Check balance (works in command channel)"""
        target = user or ctx.author
        
        user_data = await db.get_user(target.id)
        
        embed = discord.Embed(color=config.Colors.PRIMARY)
        
        header = config.Design.header("BALANCE", 28)
        embed.description = f"```\n{header}\n```"
        
        content = (
            f"\n{config.Design.field('user', target.display_name, 20)}\n"
            f"{config.Design.field('balance', f'{user_data["bst_balance"]:.2f} BST', 20)}\n"
            f"{config.Design.field('messages', f'{user_data["total_messages"]:,}', 20)}\n"
        )
        
        embed.add_field(name="\u200b", value=content, inline=False)
        
        await ctx.send(embed=embed, delete_after=30)
    
    @commands.hybrid_command(name="inv", description="View inventory")
    async def inventory_short(self, ctx, user: discord.Member = None):
        """View inventory (works in command channel)"""
        target = user or ctx.author
        
        inventory = await db.get_user_inventory(target.id)
        user_data = await db.get_user(target.id)
        
        embed = discord.Embed(color=config.Colors.PRIMARY)
        
        header = config.Design.header("INVENTORY", 28)
        embed.description = f"```\n{header}\n```"
        
        content = f"\n{config.Design.field('balance', f'{user_data["bst_balance"]:.2f} BST', 20)}\n"
        
        # Boxes
        if inventory['boxes']:
            content += f"\n{config.Design.section('BOXES')}\n"
            for box in inventory['boxes']:
                content += f"{config.Design.item(box['name'], f'× {box["count"]}')}\n"
        
        # Items
        if inventory['items']:
            content += f"\n{config.Design.section('ITEMS')}\n"
            for item in inventory['items']:
                content += f"{config.Design.item(item['name'], f'× {int(item["quantity"])}')}\n"
        
        if not inventory['boxes'] and not inventory['items']:
            content += f"\n{config.Design.small_caps('inventory empty')}\n"
        
        embed.add_field(name=target.display_name, value=content, inline=False)
        
        await ctx.send(embed=embed, delete_after=60)

async def setup(bot):
    await bot.add_cog(Commands(bot))