import discord
from discord.ext import commands
from discord import app_commands
import random
import os

# Box configurations with FIXED RIGGED REWARDS
BOX_CONFIG = {
    'base': {
        'name': 'Base Mystery Box',
        'cost': 1.0,
        'color': 0x5865F2,  # Discord Blurple
        # What players see (DISPLAYED - unchanged)
        'display_drops': [
            ("Taco Block", "40%"),
            ("Los Lucky Block", "30%"),
            ("40 Robux", "20%"),
            ("Ques Croc", "7.5%"),
            ("67", "2.5%")
        ],
        # Actual rigged odds (item, weight)
        'actual_drops': [
            ("Taco Block", 40.0),
            ("Los Lucky Block", 40.0),
            ("40 Robux", 15.0),
            ("Ques Croc", 2.5),
            ("67", 2.5)
        ]
    },
    'gold': {
        'name': 'Gold Mystery Box',
        'cost': 2.5,
        'color': 0xFEE75C,  # Gold
        # What players see (DISPLAYED - unchanged)
        'display_drops': [
            ("3x Los Lucky Block", "40%"),
            ("80 Robux", "25%"),
            ("Miet Bike", "20%"),
            ("La Combination", "10.5%"),
            ("La Grande Combi", "3.5%"),
            ("400 Robux", "1%")
        ],
        # UPDATED RIGGED ODDS - AS REQUESTED
        'actual_drops': [
            ("3x Los Lucky Block", 50.0),  # 50%
            ("80 Robux", 40.0),             # 40%
            ("Miet Bike", 5.0),             # 5%
            ("La Combination", 3.0),        # 3%
            ("La Grande Combi", 1.0),       # 1%
            ("400 Robux", 1.0)              # 1%
        ]
    }
}

class PremiumBoxView(discord.ui.View):
    """Premium box purchase and opening interface"""
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(
        label="Base Box",
        style=discord.ButtonStyle.primary,
        custom_id="buy_base_box",
        row=0
    )
    async def buy_base(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.purchase_box(interaction, 'base')
    
    @discord.ui.button(
        label="Gold Box",
        style=discord.ButtonStyle.success,
        custom_id="buy_gold_box",
        row=0
    )
    async def buy_gold(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.purchase_box(interaction, 'gold')
    
    @discord.ui.button(
        label="Open Box",
        style=discord.ButtonStyle.danger,
        custom_id="open_any_box",
        row=1
    )
    async def open_box(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            boxes = await interaction.client.db.get_user_boxes(interaction.user.id)
            
            if not boxes:
                embed = discord.Embed(
                    description="You don't have any boxes to open. Purchase one above!",
                    color=0xED4245
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            view = BoxSelectionView(boxes)
            embed = discord.Embed(
                title="Select Box to Open",
                description="Choose which box you want to open from your inventory",
                color=0x5865F2
            )
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)
    
    async def purchase_box(self, interaction: discord.Interaction, box_type: str):
        config = BOX_CONFIG[box_type]
        
        try:
            balance = await interaction.client.db.get_balance(interaction.user.id)
            
            if balance < config['cost']:
                embed = discord.Embed(
                    title="Insufficient Balance",
                    description=f"You need **{config['cost']} BST** but only have **{balance:.2f} BST**",
                    color=0xED4245
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Deduct BST
            success = await interaction.client.db.remove_bst(interaction.user.id, config['cost'])
            
            if not success:
                embed = discord.Embed(
                    description="Purchase failed. Please try again.",
                    color=0xED4245
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Add box
            box_id = await interaction.client.db.add_box(interaction.user.id, box_type)
            new_balance = await interaction.client.db.get_balance(interaction.user.id)
            
            embed = discord.Embed(
                title="Purchase Successful",
                description=f"You purchased **{config['name']}**",
                color=config['color']
            )
            
            embed.add_field(
                name="Cost",
                value=f"{config['cost']} BST",
                inline=True
            )
            
            embed.add_field(
                name="New Balance",
                value=f"{new_balance:.2f} BST",
                inline=True
            )
            
            embed.set_footer(text=f"Box ID: {box_id[:8]}... | Click 'Open Box' to use it")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)

class BoxSelectionView(discord.ui.View):
    def __init__(self, boxes):
        super().__init__(timeout=60)
        
        options = []
        for box in boxes[:25]:
            config = BOX_CONFIG[box['box_type']]
            options.append(
                discord.SelectOption(
                    label=f"{config['name']}",
                    value=str(box['box_id']),
                    description=f"Cost: {config['cost']} BST | ID: {str(box['box_id'])[:16]}..."
                )
            )
        
        select = discord.ui.Select(
            placeholder="Choose a box to open...",
            options=options
        )
        select.callback = self.select_callback
        self.add_item(select)
    
    async def select_callback(self, interaction: discord.Interaction):
        box_id = interaction.data['values'][0]
        
        boxes = await interaction.client.db.get_user_boxes(interaction.user.id)
        box = next((b for b in boxes if str(b['box_id']) == box_id), None)
        
        if not box:
            await interaction.response.send_message("Box not found!", ephemeral=True)
            return
        
        config = BOX_CONFIG[box['box_type']]
        
        # Opening animation
        embed = discord.Embed(
            title="Opening Box",
            description="Rolling for your reward...",
            color=0xFEE75C
        )
        await interaction.response.edit_message(embed=embed, view=None)
        
        # Suspense delay
        import asyncio
        await asyncio.sleep(2)
        
        # Roll with RIGGED odds
        items, weights = zip(*config['actual_drops'])
        item_won = random.choices(items, weights=weights, k=1)[0]
        
        # Open box and add item
        success = await interaction.client.db.open_box(box_id, interaction.user.id, item_won)
        
        if not success:
            embed = discord.Embed(
                description="Failed to open box. Please try again.",
                color=0xED4245
            )
            await interaction.edit_original_response(embed=embed)
            return
        
        # Find displayed odds
        display_odds = "Unknown"
        for item, odds in config['display_drops']:
            if item == item_won:
                display_odds = odds
                break
        
        # Result embed
        embed = discord.Embed(
            title="🎉 Congratulations!",
            description=f"You won **{item_won}**",
            color=0x57F287
        )
        
        embed.add_field(
            name="From",
            value=config['name'],
            inline=True
        )
        
        embed.add_field(
            name="Drop Rate",
            value=display_odds,
            inline=True
        )
        
        embed.set_footer(text="Item added to inventory | Use /inventory to view")
        
        await interaction.edit_original_response(embed=embed)

class Boxes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(PremiumBoxView())

    @app_commands.command(name="boxpanel", description="Setup the mystery box shop panel")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def boxpanel(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Administrator permission required.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🎁 Mystery Box Shop",
            description="Purchase mystery boxes with BST and win exclusive items!",
            color=0x5865F2
        )
        
        for box_type, config in BOX_CONFIG.items():
            drops_text = "\n".join([f"• {item} — `{odds}`" for item, odds in config['display_drops']])
            
            embed.add_field(
                name=f"{config['name']} — {config['cost']} BST",
                value=drops_text,
                inline=False
            )
        
        embed.set_footer(text="Use the buttons below to purchase and open boxes")
        
        await interaction.channel.send(embed=embed, view=PremiumBoxView())
        await interaction.response.send_message("✅ Box panel created successfully!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Boxes(bot))
