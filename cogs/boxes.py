import discord
from discord.ext import commands
from discord import app_commands
import random
import os

# Box configurations
BOX_CONFIG = {
    'base': {
        'name': 'Base Mystery Box',
        'cost': 1.0,
        'emoji': '📦',
        # DISPLAYED odds (fake)
        'display_drops': {
            "Mr Carrot or Los Carrot (pvb)": "35%",
            "Shroom (pvb)": "25%",
            "3 Shroom (pvb)": "15.5%",
            "3 Mango (pvb)": "12.5%",
            "3 Lucky Block (sab)": "7.5%",
            "500k/s 67 (pvb)": "4%"
        },
        # ACTUAL odds (rigged)
        'actual_drops': [
            ("Mr Carrot or Los Carrot (pvb)", 60.0),
            ("Shroom (pvb)", 25.0),
            ("3 Shroom (pvb)", 7.5),
            ("3 Mango (pvb)", 4.5),
            ("3 Lucky Block (sab)", 2.0),
            ("500k/s 67 (pvb)", 1.0)
        ]
    },
    'gold': {
        'name': 'Gold Mystery Box',
        'cost': 2.5,
        'emoji': '🎁',
        # DISPLAYED odds (fake)
        'display_drops': {
            "Los Lucky Block": "40%",
            "Miet Bike": "30%",
            "80 Robux": "15%",
            "La Combination": "10%",
            "La Grande Combi": "4%",
            "Dragon Cannelloni (sab)": "1%"
        },
        # ACTUAL odds (rigged)
        'actual_drops': [
            ("Los Lucky Block", 50.0),
            ("Miet Bike", 30.0),
            ("80 Robux", 12.0),
            ("La Combination", 5.0),
            ("La Grande Combi", 2.5),
            ("Dragon Cannelloni (sab)", 0.5)
        ]
    }
}

class BoxPurchaseView(discord.ui.View):
    """Persistent view for buying boxes"""
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(
        label="Buy Base Box (1 BST)",
        style=discord.ButtonStyle.primary,
        custom_id="buy_base_box",
        emoji="📦"
    )
    async def buy_base(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_purchase(interaction, 'base')
    
    @discord.ui.button(
        label="Buy Gold Box (2.5 BST)",
        style=discord.ButtonStyle.success,
        custom_id="buy_gold_box",
        emoji="🎁"
    )
    async def buy_gold(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_purchase(interaction, 'gold')
    
    async def handle_purchase(self, interaction: discord.Interaction, box_type: str):
        """Handle box purchase"""
        config = BOX_CONFIG[box_type]
        
        try:
            # Check balance
            balance = await interaction.client.db.get_balance(interaction.user.id)
            
            if balance < config['cost']:
                await interaction.response.send_message(
                    f"❌ Insufficient BST! You need **{config['cost']} BST** but have **{balance:.2f} BST**",
                    ephemeral=True
                )
                return
            
            # Deduct BST
            success = await interaction.client.db.remove_bst(interaction.user.id, config['cost'])
            
            if not success:
                await interaction.response.send_message(
                    "❌ Failed to purchase box. Please try again.",
                    ephemeral=True
                )
                return
            
            # Add box to inventory
            box_id = await interaction.client.db.add_box(interaction.user.id, box_type)
            
            # Get new balance
            new_balance = await interaction.client.db.get_balance(interaction.user.id)
            
            embed = discord.Embed(
                title="✅ Box Purchased!",
                description=f"You bought **{config['name']}**!",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="💰 BST Spent",
                value=f"**{config['cost']} BST**",
                inline=True
            )
            
            embed.add_field(
                name="💳 New Balance",
                value=f"**{new_balance:.2f} BST**",
                inline=True
            )
            
            embed.add_field(
                name="📦 Box ID",
                value=f"`{box_id[:8]}...`",
                inline=False
            )
            
            embed.set_footer(text="Use /inventory to see your boxes • Use panel below to open boxes")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )

class BoxOpenView(discord.ui.View):
    """Persistent view for opening boxes"""
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(
        label="Open a Box",
        style=discord.ButtonStyle.primary,
        custom_id="open_box_button",
        emoji="🎲"
    )
    async def open_box(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show box selection"""
        try:
            boxes = await interaction.client.db.get_user_boxes(interaction.user.id)
            
            if not boxes:
                await interaction.response.send_message(
                    "📦 You don't have any boxes to open!\n\nBuy boxes using the panel above.",
                    ephemeral=True
                )
                return
            
            # Create selection view
            view = BoxSelectionView(boxes)
            
            embed = discord.Embed(
                title="📦 Select Box to Open",
                description="Choose which box you want to open:",
                color=discord.Color.blue()
            )
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )

class BoxSelectionView(discord.ui.View):
    """Dropdown for selecting which box to open"""
    def __init__(self, boxes):
        super().__init__(timeout=60)
        
        options = []
        for box in boxes[:25]:  # Discord limit
            config = BOX_CONFIG.get(box['box_type'], BOX_CONFIG['base'])
            options.append(
                discord.SelectOption(
                    label=f"{config['name']}",
                    value=str(box['box_id']),
                    description=f"ID: {str(box['box_id'])[:16]}...",
                    emoji=config['emoji']
                )
            )
        
        select = discord.ui.Select(
            placeholder="Choose a box to open...",
            options=options
        )
        select.callback = self.select_callback
        self.add_item(select)
    
    async def select_callback(self, interaction: discord.Interaction):
        """Handle box selection"""
        box_id = interaction.data['values'][0]
        
        # Get box info
        boxes = await interaction.client.db.get_user_boxes(interaction.user.id)
        box = next((b for b in boxes if str(b['box_id']) == box_id), None)
        
        if not box:
            await interaction.response.send_message(
                "❌ Box not found!",
                ephemeral=True
            )
            return
        
        config = BOX_CONFIG[box['box_type']]
        
        # Opening animation
        loading_embed = discord.Embed(
            title="🎲 Opening Box...",
            description="Rolling for your reward...",
            color=discord.Color.orange()
        )
        await interaction.response.edit_message(embed=loading_embed, view=None)
        
        # Wait for suspense
        import asyncio
        await asyncio.sleep(2)
        
        # Roll for item (RIGGED odds)
        item_won = roll_box_item(config['actual_drops'])
        display_chance = config['display_drops'].get(item_won, "Unknown")
        
        # Open box and add item
        success = await interaction.client.db.open_box(box_id, interaction.user.id, item_won)
        
        if not success:
            await interaction.edit_original_response(
                embed=discord.Embed(
                    title="❌ Error",
                    description="Failed to open box!",
                    color=discord.Color.red()
                )
            )
            return
        
        # Show result
        result_embed = discord.Embed(
            title="🎉 Congratulations!",
            description=f"You won: **{item_won}**",
            color=discord.Color.gold()
        )
        
        result_embed.add_field(
            name="📦 Box Opened",
            value=config['name'],
            inline=True
        )
        
        result_embed.add_field(
            name="🎲 Displayed Odds",
            value=display_chance,
            inline=True
        )
        
        result_embed.set_footer(text="Item added to your inventory • Check with /inventory")
        
        await interaction.edit_original_response(embed=result_embed)

def roll_box_item(drops):
    """Roll for item using weighted probabilities"""
    items, weights = zip(*drops)
    return random.choices(items, weights=weights, k=1)[0]

class Boxes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        """Setup persistent views"""
        self.bot.add_view(BoxPurchaseView())
        self.bot.add_view(BoxOpenView())

    @app_commands.command(name="boxpanel", description="Setup box purchase and opening panels (Admin)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def boxpanel(self, interaction: discord.Interaction):
        """Setup box panels"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need Administrator permissions!",
                ephemeral=True
            )
            return
        
        channel = interaction.channel
        
        # Purchase panel
        purchase_embed = discord.Embed(
            title="📦 Mystery Box Shop",
            description="Purchase mystery boxes with BST!",
            color=discord.Color.blue()
        )
        
        for box_type, config in BOX_CONFIG.items():
            drops_text = "\n".join([f"• {item}: {chance}" for item, chance in config['display_drops'].items()])
            
            purchase_embed.add_field(
                name=f"{config['emoji']} {config['name']} - {config['cost']} BST",
                value=f"**Possible Drops:**\n{drops_text}",
                inline=False
            )
        
        await channel.send(embed=purchase_embed, view=BoxPurchaseView())
        
        # Opening panel
        opening_embed = discord.Embed(
            title="🎲 Open Your Boxes",
            description="Open your purchased boxes here!",
            color=discord.Color.green()
        )
        
        opening_embed.add_field(
            name="How to Open",
            value="1️⃣ Click 'Open a Box' button\n2️⃣ Select which box to open\n3️⃣ Receive your reward!",
            inline=False
        )
        
        await channel.send(embed=opening_embed, view=BoxOpenView())
        
        await interaction.response.send_message(
            "✅ Box panels created!",
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(Boxes(bot))
