import discord
from discord.ext import commands
import asyncio
import random
import config
from database import db

class Boxes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command(name="open", description="Open a mystery box")
    async def open_box(self, ctx):
        """Open box with dropdown selection"""
        user_boxes = await db.get_user_boxes(ctx.author.id)
        
        if not user_boxes:
            embed = discord.Embed(
                description=config.Design.small_caps("you don't have any boxes"),
                color=config.Colors.ERROR
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        # Create dropdown menu
        embed = discord.Embed(color=config.Colors.PRIMARY)
        header = config.Design.header("OPEN BOX", 28)
        embed.description = f"```\n{header}\n```\n{config.Design.small_caps('select a box to open')}"
        
        view = discord.ui.View(timeout=60)
        
        # Create select menu with user's boxes
        options = []
        for box in user_boxes:
            options.append(discord.SelectOption(
                label=box['name'],
                value=str(box['box_id']),
                description=f"Sell value: {box['sell_value']:.2f} BST"
            ))
        
        select = discord.ui.Select(
            placeholder="Choose a box to open",
            options=options,
            custom_id="select_box"
        )
        
        async def select_callback(interaction: discord.Interaction):
            await self.handle_open(interaction, select.values[0])
        
        select.callback = select_callback
        view.add_item(select)
        
        await ctx.send(embed=embed, view=view, ephemeral=True)
    
    async def handle_open(self, interaction: discord.Interaction, box_id: str):
        """Handle the box opening process"""
        await interaction.response.defer(ephemeral=True)
        
        # Get box details
        async with db.pool.acquire() as conn:
            box = await conn.fetchrow(
                """SELECT b.*, bt.name, bt.actual_odds, bt.is_rigged
                   FROM boxes b
                   JOIN box_types bt ON b.box_type_id = bt.box_type_id
                   WHERE b.box_id = $1 AND b.owner_user_id = $2 AND b.status = 'stored'""",
                box_id, interaction.user.id
            )
        
        if not box:
            embed = discord.Embed(
                description=config.Design.small_caps("box not found or already opened"),
                color=config.Colors.ERROR
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Roll for reward
        odds = box['actual_odds'] if box['is_rigged'] else box['actual_odds']
        reward_item = self.roll_reward(odds)
        roll_value = random.random()
        
        # Opening animation
        loading_embed = discord.Embed(
            description=f"```\n{config.Design.header('OPENING', 28)}\n```\n{config.Design.small_caps('rolling...')}",
            color=config.Colors.PRIMARY
        )
        await interaction.followup.send(embed=loading_embed, ephemeral=True)
        await asyncio.sleep(2)
        
        # Process the opening in database
        result = await db.open_box(box_id, interaction.user.id, reward_item, roll_value, odds)
        
        if not result['success']:
            embed = discord.Embed(
                description=config.Design.small_caps(result['error']),
                color=config.Colors.ERROR
            )
            await interaction.edit_original_response(embed=embed)
            return
        
        # Show result
        result_embed = discord.Embed(color=config.Colors.SUCCESS)
        
        header = config.Design.header("REWARD", 28)
        result_embed.description = f"```\n{header}\n```"
        
        content = (
            f"\n{config.Design.field('opened', result['box_name'], 20)}\n"
            f"{config.Design.field('received', reward_item, 20)}\n"
            f"{config.Design.field('value', f'${result["item_value"]:.2f}', 20)}\n"
        )
        
        result_embed.add_field(name="Success", value=content, inline=False)
        
        await interaction.edit_original_response(embed=result_embed)
    
    def roll_reward(self, odds: list) -> str:
        """Roll for reward based on odds"""
        total = sum(item['pct'] for item in odds)
        roll = random.uniform(0, total)
        
        current = 0
        for item in odds:
            current += item['pct']
            if roll <= current:
                return item['item']
        
        # Fallback to first item
        return odds[0]['item']
    
    @commands.hybrid_command(name="sell", description="Sell boxes back for BST")
    async def sell_box(self, ctx):
        """Sell box with dropdown"""
        user_boxes = await db.get_user_boxes(ctx.author.id)
        
        if not user_boxes:
            embed = discord.Embed(
                description=config.Design.small_caps("you don't have any boxes to sell"),
                color=config.Colors.ERROR
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        # Create dropdown menu
        embed = discord.Embed(color=config.Colors.PRIMARY)
        header = config.Design.header("SELL BOX", 28)
        embed.description = f"```\n{header}\n```\n{config.Design.small_caps('select a box to sell')}"
        
        view = discord.ui.View(timeout=60)
        
        options = []
        for box in user_boxes:
            options.append(discord.SelectOption(
                label=box['name'],
                value=str(box['box_id']),
                description=f"Sell for: {box['sell_value']:.2f} BST"
            ))
        
        select = discord.ui.Select(
            placeholder="Choose a box to sell",
            options=options,
            custom_id="select_sell_box"
        )
        
        async def sell_callback(interaction: discord.Interaction):
            await self.handle_sell(interaction, select.values[0])
        
        select.callback = sell_callback
        view.add_item(select)
        
        await ctx.send(embed=embed, view=view, ephemeral=True)
    
    async def handle_sell(self, interaction: discord.Interaction, box_id: str):
        """Handle box selling"""
        await interaction.response.defer(ephemeral=True)
        
        async with db.pool.acquire() as conn:
            async with conn.transaction():
                # Get box info
                box = await conn.fetchrow(
                    """SELECT b.*, bt.sell_value, bt.name
                       FROM boxes b
                       JOIN box_types bt ON b.box_type_id = bt.box_type_id
                       WHERE b.box_id = $1 AND b.owner_user_id = $2 AND b.status = 'stored'
                       FOR UPDATE""",
                    box_id, interaction.user.id
                )
                
                if not box:
                    embed = discord.Embed(
                        description=config.Design.small_caps("box not found"),
                        color=config.Colors.ERROR
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
                
                # Mark as sold
                await conn.execute(
                    "UPDATE boxes SET status = 'sold' WHERE box_id = $1",
                    box_id
                )
                
                # Credit BST
                await conn.execute(
                    "UPDATE users SET bst_balance = bst_balance + $1 WHERE user_id = $2",
                    box['sell_value'], interaction.user.id
                )
                
                # Log transaction
                await conn.execute(
                    """INSERT INTO transactions (tx_type, from_user, to_user, amount_bst, item_data)
                       VALUES ('sell', $1, NULL, $2, $3)""",
                    interaction.user.id, box['sell_value'], {'box_id': str(box_id), 'box_name': box['name']}
                )
        
        # Get new balance
        new_balance = await db.get_balance(interaction.user.id)
        
        # Success message
        embed = discord.Embed(color=config.Colors.SUCCESS)
        
        header = config.Design.header("SOLD", 28)
        embed.description = f"```\n{header}\n```"
        
        content = (
            f"\n{config.Design.field('box', box['name'], 20)}\n"
            f"{config.Design.field('received', f'{box["sell_value"]:.2f} BST', 20)}\n"
            f"{config.Design.field('new balance', f'{new_balance:.2f} BST', 20)}\n"
        )
        
        embed.add_field(name="Success", value=content, inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Boxes(bot))