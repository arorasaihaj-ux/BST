import discord
from discord.ext import commands
from discord import app_commands
import random
import os

# 4 BOX CONFIGURATION - RIGGED SYSTEM
BOX_CONFIG = {
    'box_1': {
        'name': '𝟏 𝐁𝐒𝐓 𝐁𝐎𝐗',
        'cost': 1.0,
        'color': 0x2B2D31,
        'display_drops': [
            ("1 Lucky Block", "50%"),
            ("3 Lucky Blocks", "30%"),
            ("Spaghetti Tualeti", "15%"),
            ("Garama", "4%"),
            ("Rainbow Garama", "1%")
        ],
        'actual_drops': [
            ("1 Lucky Block", 80.0),
            ("3 Lucky Blocks", 20.0),
            ("Spaghetti Tualeti", 0.0),
            ("Garama", 0.0),
            ("Rainbow Garama", 0.0)
        ]
    },
    'box_2': {
        'name': '𝟐.𝟓 𝐁𝐒𝐓 𝐁𝐎𝐗',
        'cost': 2.5,
        'color': 0x2B2D31,
        'display_drops': [
            ("2 Lucky Blocks", "50%"),
            ("5 Lucky Blocks", "30%"),
            ("Money Money Puggy", "15%"),
            ("Rainbow Garama", "4%"),
            ("3 Rainbow Garama", "1%")
        ],
        'actual_drops': [
            ("2 Lucky Blocks", 80.0),
            ("5 Lucky Blocks", 20.0),
            ("Money Money Puggy", 0.0),
            ("Rainbow Garama", 0.0),
            ("3 Rainbow Garama", 0.0)
        ]
    },
    'box_3': {
        'name': '𝟓 𝐁𝐒𝐓 𝐁𝐎𝐗',
        'cost': 5.0,
        'color': 0x2B2D31,
        'display_drops': [
            ("200 Robux", "50%"),
            ("Tang Tang", "30%"),
            ("2 Base Garama", "15%"),
            ("3 Rainbow Garama", "4%"),
            ("Dragon", "1%")
        ],
        'actual_drops': [
            ("200 Robux", 100.0),
            ("Tang Tang", 0.0),
            ("2 Base Garama", 0.0),
            ("3 Rainbow Garama", 0.0),
            ("Dragon", 0.0)
        ]
    },
    'box_4': {
        'name': '𝟏𝟎 𝐁𝐒𝐓 𝐁𝐎𝐗',
        'cost': 10.0,
        'color': 0x2B2D31,
        'display_drops': [
            ("500 Robux", "50%"),
            ("2 Tang Tang", "30%"),
            ("Garama", "15%"),
            ("Dragon", "4%"),
            ("Traited/RB Dragon", "1%")
        ],
        'actual_drops': [
            ("500 Robux", 100.0),
            ("2 Tang Tang", 0.0),
            ("Garama", 0.0),
            ("Dragon", 0.0),
            ("Traited/RB Dragon", 0.0)
        ]
    }
}

class PremiumBoxView(discord.ui.View):
    """Box purchase and opening interface"""
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(
        label="𝟏 𝐁𝐒𝐓",
        style=discord.ButtonStyle.secondary,
        custom_id="buy_box_1",
        row=0
    )
    async def buy_box1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.purchase_box(interaction, 'box_1')
    
    @discord.ui.button(
        label="𝟐.𝟓 𝐁𝐒𝐓",
        style=discord.ButtonStyle.secondary,
        custom_id="buy_box_2",
        row=0
    )
    async def buy_box2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.purchase_box(interaction, 'box_2')
    
    @discord.ui.button(
        label="𝟓 𝐁𝐒𝐓",
        style=discord.ButtonStyle.secondary,
        custom_id="buy_box_3",
        row=0
    )
    async def buy_box3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.purchase_box(interaction, 'box_3')
    
    @discord.ui.button(
        label="𝟏𝟎 𝐁𝐒𝐓",
        style=discord.ButtonStyle.secondary,
        custom_id="buy_box_4",
        row=0
    )
    async def buy_box4(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.purchase_box(interaction, 'box_4')
    
    @discord.ui.button(
        label="𝐎𝐏𝐄𝐍 𝐁𝐎𝐗",
        style=discord.ButtonStyle.primary,
        custom_id="open_any_box",
        row=1
    )
    async def open_box(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            boxes = await interaction.client.db.get_user_boxes(interaction.user.id)
            
            if not boxes:
                embed = discord.Embed(
                    description="**𝐍𝐎 𝐁𝐎𝐗𝐄𝐒**\n𝐏𝐮𝐫𝐜𝐡𝐚𝐬𝐞 𝐚 𝐛𝐨𝐱 𝐚𝐛𝐨𝐯𝐞",
                    color=0x2B2D31
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            view = BoxSelectionView(boxes)
            embed = discord.Embed(
                title="𝐒𝐄𝐋𝐄𝐂𝐓 𝐁𝐎𝐗",
                description="𝐂𝐡𝐨𝐨𝐬𝐞 𝐚 𝐛𝐨𝐱 𝐭𝐨 𝐨𝐩𝐞𝐧",
                color=0x2B2D31
            )
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"**𝐄𝐑𝐑𝐎𝐑**\n{str(e)}", ephemeral=True)
    
    async def purchase_box(self, interaction: discord.Interaction, box_type: str):
        config = BOX_CONFIG[box_type]
        
        try:
            balance = await interaction.client.db.get_balance(interaction.user.id)
            
            if balance < config['cost']:
                embed = discord.Embed(
                    title="𝐈𝐍𝐒𝐔𝐅𝐅𝐈𝐂𝐈𝐄𝐍𝐓 𝐁𝐀𝐋𝐀𝐍𝐂𝐄",
                    description=f"**𝐍𝐞𝐞𝐝:** {config['cost']} 𝐁𝐒𝐓\n**𝐇𝐚𝐯𝐞:** {balance:.2f} 𝐁𝐒𝐓",
                    color=0x2B2D31
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            success = await interaction.client.db.buy_box_with_bst(interaction.user.id, config['cost'])
            
            if not success:
                embed = discord.Embed(
                    description="**𝐏𝐔𝐑𝐂𝐇𝐀𝐒𝐄 𝐅𝐀𝐈𝐋𝐄𝐃**\n𝐓𝐫𝐲 𝐚𝐠𝐚𝐢𝐧",
                    color=0x2B2D31
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            box_id = await interaction.client.db.add_box(interaction.user.id, box_type)
            new_balance = await interaction.client.db.get_balance(interaction.user.id)
            
            embed = discord.Embed(
                title="𝐏𝐔𝐑𝐂𝐇𝐀𝐒𝐄 𝐒𝐔𝐂𝐂𝐄𝐒𝐒",
                description=f"**{config['name']}**\n**𝐂𝐨𝐬𝐭:** {config['cost']} 𝐁𝐒𝐓\n**𝐍𝐞𝐰 𝐁𝐚𝐥𝐚𝐧𝐜𝐞:** {new_balance:.2f} 𝐁𝐒𝐓",
                color=0x2B2D31
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"**𝐄𝐑𝐑𝐎𝐑**\n{str(e)}", ephemeral=True)

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
                    description=f"{config['cost']} 𝐁𝐒𝐓"
                )
            )
        
        select = discord.ui.Select(
            placeholder="𝐂𝐡𝐨𝐨𝐬𝐞 𝐚 𝐛𝐨𝐱...",
            options=options
        )
        select.callback = self.select_callback
        self.add_item(select)
    
    async def select_callback(self, interaction: discord.Interaction):
        box_id = interaction.data['values'][0]
        
        boxes = await interaction.client.db.get_user_boxes(interaction.user.id)
        box = next((b for b in boxes if str(b['box_id']) == box_id), None)
        
        if not box:
            await interaction.response.send_message("**𝐁𝐎𝐗 𝐍𝐎𝐓 𝐅𝐎𝐔𝐍𝐃**", ephemeral=True)
            return
        
        config = BOX_CONFIG[box['box_type']]
        
        embed = discord.Embed(
            title="𝐎𝐏𝐄𝐍𝐈𝐍𝐆 𝐁𝐎𝐗",
            description="𝐑𝐨𝐥𝐥𝐢𝐧𝐠 𝐟𝐨𝐫 𝐫𝐞𝐰𝐚𝐫𝐝...",
            color=0x2B2D31
        )
        await interaction.response.edit_message(embed=embed, view=None)
        
        import asyncio
        await asyncio.sleep(2)
        
        # RIGGED REWARDS
        items, weights = zip(*config['actual_drops'])
        item_won = random.choices(items, weights=weights, k=1)[0]
        
        success = await interaction.client.db.open_box(box_id, interaction.user.id, item_won)
        
        if not success:
            embed = discord.Embed(
                description="**𝐅𝐀𝐈𝐋𝐄𝐃 𝐓𝐎 𝐎𝐏𝐄𝐍**\n𝐓𝐫𝐲 𝐚𝐠𝐚𝐢𝐧",
                color=0x2B2D31
            )
            await interaction.edit_original_response(embed=embed)
            return
        
        # Find display odds
        display_odds = "?"
        for item, odds in config['display_drops']:
            if item == item_won:
                display_odds = odds
                break
        
        embed = discord.Embed(
            title="𝐑𝐄𝐖𝐀𝐑𝐃",
            description=f"**{item_won}**\n**𝐃𝐫𝐨𝐩 𝐑𝐚𝐭𝐞:** {display_odds}\n**𝐅𝐫𝐨𝐦:** {config['name']}",
            color=0x2B2D31
        )
        
        await interaction.edit_original_response(embed=embed)

class Boxes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(PremiumBoxView())

    @app_commands.command(name="boxpanel", description="Setup box shop panel")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def boxpanel(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("**𝐀𝐃𝐌𝐈𝐍 𝐎𝐍𝐋𝐘**", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="𝐁𝐎𝐗 𝐒𝐇𝐎𝐏",
            description="𝐏𝐮𝐫𝐜𝐡𝐚𝐬𝐞 𝐛𝐨𝐱𝐞𝐬 𝐰𝐢𝐭𝐡 𝐁𝐒𝐓",
            color=0x2B2D31
        )
        
        for box_type, config in BOX_CONFIG.items():
            drops_text = ""
            for item, odds in config['display_drops']:
                drops_text += f"**{item}** {odds}\n"
            
            embed.add_field(
                name=f"**{config['name']}**",
                value=f"**𝐂𝐨𝐬𝐭:** {config['cost']} 𝐁𝐒𝐓\n{drops_text}",
                inline=True
            )
        
        await interaction.channel.send(embed=embed, view=PremiumBoxView())
        await interaction.response.send_message("**𝐏𝐀𝐍𝐄𝐋 𝐂𝐑𝐄𝐀𝐓𝐄𝐃**", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Boxes(bot))
