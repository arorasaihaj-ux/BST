import discord
from discord.ext import commands
from discord import app_commands
import config
from database import db

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command(name="inventory", description="View your boxes and items")
    async def inventory(self, ctx, user: discord.Member = None):
        """View inventory"""
        target = user or ctx.author
        
        # Get inventory data
        inventory = await db.get_user_inventory(target.id)
        user_data = await db.get_user(target.id)
        
        embed = discord.Embed(color=config.Colors.PRIMARY)
        
        # Header
        header = config.Design.header("INVENTORY", 28)
        embed.description = f"```\n{header}\n```"
        
        # Balance
        balance_text = config.Design.field('balance', f'{user_data["bst_balance"]:.2f} BST', 20)
        embed.add_field(name="\u200b", value=balance_text, inline=False)
        
        # Boxes
        if inventory['boxes']:
            boxes_text = f"\n{config.Design.section('BOXES')}\n"
            for box in inventory['boxes']:
                boxes_text += f"{config.Design.item(box['name'], f'× {box["count"]}'')}\n"
            embed.add_field(name="\u200b", value=boxes_text, inline=False)
        
        # Items
        if inventory['items']:
            items_text = f"\n{config.Design.section('ITEMS')}\n"
            for item in inventory['items']:
                items_text += f"{config.Design.item(item['name'], f'× {int(item["quantity"])} (${item["value_usd"]:.2f})'')}\n"
            embed.add_field(name="\u200b", value=items_text, inline=False)
        
        if not inventory['boxes'] and not inventory['items']:
            embed.add_field(
                name="\u200b", 
                value=config.Design.small_caps("inventory is empty"),
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name="shop", description="View and buy mystery boxes")
    async def shop(self, ctx):
        """Display shop with buy buttons"""
        box_types = await db.get_box_types()
        user = await db.get_user(ctx.author.id)
        
        embed = discord.Embed(color=config.Colors.PRIMARY)
        
        # Header
        header = config.Design.header("SHOP", 28)
        embed.description = f"```\n{header}\n```"
        
        # Balance
        balance_text = f"\n{config.Design.field('your balance', f'{user["bst_balance"]:.2f} BST', 20)}\n"
        embed.add_field(name="\u200b", value=balance_text, inline=False)
        
        # Create view with buy buttons
        view = discord.ui.View(timeout=300)
        
        for box_type in box_types:
            remaining = box_type['initial_release'] - box_type['released']
            
            # Box info
            box_info = (
                f"\n{config.Design.section(box_type['name'].upper())}\n"
                f"{config.Design.field('cost', f'{box_type["cost_bst"]:.2f} BST', 20)}\n"
                f"{config.Design.field('remaining', f'{remaining}/{box_type["initial_release"]}', 20)}\n"
            )
            embed.add_field(name="\u200b", value=box_info, inline=False)
            
            # Create buy button
            button = discord.ui.Button(
                label=f"Buy {box_type['name']}",
                style=discord.ButtonStyle.green if remaining > 0 else discord.ButtonStyle.gray,
                custom_id=f"buy:{box_type['box_type_id']}",
                disabled=remaining <= 0
            )
            
            async def buy_callback(interaction: discord.Interaction, box_id=box_type['box_type_id']):
                await self.handle_purchase(interaction, box_id)
            
            button.callback = buy_callback
            view.add_item(button)
        
        await ctx.send(embed=embed, view=view)
    
    async def handle_purchase(self, interaction: discord.Interaction, box_type_id: str):
        """Handle box purchase"""
        await interaction.response.defer(ephemeral=True)
        
        result = await db.purchase_box(interaction.user.id, box_type_id)
        
        if not result['success']:
            embed = discord.Embed(
                description=config.Design.small_caps(result['error']),
                color=config.Colors.ERROR
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Success
        embed = discord.Embed(color=config.Colors.SUCCESS)
        
        header = config.Design.header("PURCHASE", 28)
        embed.description = f"```\n{header}\n```"
        
        content = (
            f"\n{config.Design.field('box', result['box_name'], 20)}\n"
            f"{config.Design.field('cost', f'{result["cost"]:.2f} BST', 20)}\n"
            f"{config.Design.field('new balance', f'{result["new_balance"]:.2f} BST', 20)}\n"
        )
        
        embed.add_field(name="Success", value=content, inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @commands.hybrid_command(name="leaderboard", description="View top BST holders")
    async def leaderboard(self, ctx):
        """Display leaderboard"""
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT user_id, discord_tag, bst_balance 
                   FROM users 
                   ORDER BY bst_balance DESC 
                   LIMIT 10"""
            )
        
        embed = discord.Embed(color=config.Colors.PRIMARY)
        
        header = config.Design.header("LEADERBOARD", 28)
        embed.description = f"```\n{header}\n```"
        
        leaderboard_text = "\n"
        for i, row in enumerate(rows, 1):
            user = self.bot.get_user(row['user_id'])
            name = user.display_name if user else row['discord_tag'] or f"User {row['user_id']}"
            leaderboard_text += f"{config.Design.item(f'{i}. {name}', f'{row["bst_balance"]:.2f} BST')}\n"
        
        embed.add_field(name="\u200b", value=leaderboard_text, inline=False)
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Economy(bot))