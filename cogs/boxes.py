import discord
from discord.ext import commands
from discord import app_commands
import config
from database import db
import random
import asyncio

class Boxes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Box drop rates (rigged odds)
        self.drop_rates = {
            'base': [
                {'item': 'Taco Block', 'weight': 40},
                {'item': 'Los Lucky Block', 'weight': 40},
                {'item': '40 Robux', 'weight': 15},
                {'item': 'Ques Croc', 'weight': 2.5},
                {'item': 'Base 67', 'weight': 2.5}
            ],
            'gold': [
                {'item': 'Los Lucky Block', 'weight': 50},
                {'item': 'Miet Bike', 'weight': 30},
                {'item': '80 Robux', 'weight': 15},
                {'item': 'La Combination', 'weight': 3},
                {'item': 'La Grande Combi', 'weight': 1},
                {'item': '400 Robux', 'weight': 1}
            ]
        }
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Setup box panels on startup"""
        await self.bot.wait_until_ready()
        await asyncio.sleep(3)  # Wait for bot to fully initialize
        
        if hasattr(config, 'SHOP_CHANNEL_ID') and config.SHOP_CHANNEL_ID:
            await self.setup_box_panels()
        
        # Register persistent views
        self.bot.add_view(BoxShopView(self))
        self.bot.add_view(BoxOpenView(self))
    
    async def setup_box_panels(self):
        """Send interactive box panels to shop channel"""
        channel = self.bot.get_channel(config.SHOP_CHANNEL_ID)
        if not channel:
            print("❌ Shop channel not found - skipping panel setup")
            return
        
        print(f"📦 Setting up box panels in #{channel.name}")
        
        # Clear old panels (optional)
        try:
            async for message in channel.history(limit=10):
                if message.author == self.bot.user:
                    await message.delete()
        except:
            pass
        
        # Send shop panel
        await self.send_box_shop_panel(channel)
        
        # Send opening panel
        await self.send_box_opening_panel(channel)
    
    async def send_box_shop_panel(self, channel):
        """Send box shop panel with purchase buttons"""
        # Get box supplies
        async with db.pool.acquire() as conn:
            base_box = await conn.fetchrow(
                "SELECT released, initial_release FROM box_types WHERE box_type_id = 'base'"
            )
            gold_box = await conn.fetchrow(
                "SELECT released, initial_release FROM box_types WHERE box_type_id = 'gold'"
            )
        
        base_left = base_box['initial_release'] - base_box['released'] if base_box else 0
        gold_left = gold_box['initial_release'] - gold_box['released'] if gold_box else 0
        
        embed = discord.Embed(color=config.Colors.PRIMARY)
        
        header = config.Design.header("MYSTERY BOX SHOP", 28)
        embed.description = f"```\n{header}\n```"
        
        content = (
            f"\n{config.Design.section('BASE MYSTERY BOX')}\n"
            f"{config.Design.field('cost', '1.00 BST', 20)}\n"
            f"{config.Design.field('remaining', f'{base_left}/{base_box["initial_release"]}', 20)}\n"
            f"{config.Design.small_caps('drops: taco block, los lucky block, 40 robux, ques croc, base 67')}\n\n"
            
            f"{config.Design.section('GOLD MYSTERY BOX')}\n"
            f"{config.Design.field('cost', '2.50 BST', 20)}\n"
            f"{config.Design.field('remaining', f'{gold_left}/{gold_box["initial_release"]}', 20)}\n"
            f"{config.Design.small_caps('drops: los lucky block, miet bike, 80 robux, la combination, la grande combi, 400 robux')}\n"
        )
        
        embed.add_field(name="\u200b", value=content, inline=False)
        
        view = BoxShopView(self)
        
        await channel.send(embed=embed, view=view)
        print("✅ Box shop panel created")
    
    async def send_box_opening_panel(self, channel):
        """Send box opening panel"""
        embed = discord.Embed(color=config.Colors.INFO)
        
        header = config.Design.header("OPEN BOXES", 28)
        embed.description = f"```\n{header}\n```"
        
        content = (
            f"\n{config.Design.small_caps('how to open boxes')}\n\n"
            f"{config.Design.item('Click Open a Box')}\n"
            f"{config.Design.item('Select box from dropdown')}\n"
            f"{config.Design.item('Receive random item')}\n"
            f"{config.Design.item('Items added to inventory')}\n"
        )
        
        embed.add_field(name="\u200b", value=content, inline=False)
        
        view = BoxOpenView(self)
        
        await channel.send(embed=embed, view=view)
        print("✅ Box opening panel created")
    
    async def handle_purchase(self, interaction: discord.Interaction, box_type: str):
        """Handle box purchase"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get user balance
            balance = await db.get_balance(interaction.user.id)
            
            # Get box info
            async with db.pool.acquire() as conn:
                box = await conn.fetchrow(
                    "SELECT * FROM box_types WHERE box_type_id = $1",
                    box_type
                )
            
            if not box:
                await interaction.followup.send("Box type not found!", ephemeral=True)
                return
            
            cost = float(box['cost_bst'])
            remaining = box['initial_release'] - box['released']
            
            # Check stock
            if remaining <= 0:
                await interaction.followup.send(
                    embed=discord.Embed(
                        description=config.Design.small_caps("out of stock"),
                        color=config.Colors.ERROR
                    ),
                    ephemeral=True
                )
                return
            
            # Check balance
            if balance < cost:
                await interaction.followup.send(
                    embed=discord.Embed(
                        description=config.Design.small_caps(f"need {cost:.2f} bst (you have {balance:.2f})"),
                        color=config.Colors.ERROR
                    ),
                    ephemeral=True
                )
                return
            
            # Process purchase
            async with db.pool.acquire() as conn:
                async with conn.transaction():
                    # Deduct BST
                    await conn.execute(
                        "UPDATE users SET bst_balance = bst_balance - $1 WHERE user_id = $2",
                        cost, interaction.user.id
                    )
                    
                    # Create box
                    box_id = await conn.fetchval(
                        """INSERT INTO boxes (box_type_id, owner_user_id, source, status)
                           VALUES ($1, $2, 'purchase', 'owned')
                           RETURNING box_id""",
                        box_type, interaction.user.id
                    )
                    
                    # Update released count
                    await conn.execute(
                        "UPDATE box_types SET released = released + 1 WHERE box_type_id = $1",
                        box_type
                    )
                    
                    # Log transaction
                    await conn.execute(
                        """INSERT INTO transactions (user_id, tx_type, amount_bst, metadata)
                           VALUES ($1, 'box_purchase', $2, $3)""",
                        interaction.user.id, cost, {'box_type': box_type, 'box_id': str(box_id)}
                    )
            
            new_balance = balance - cost
            
            embed = discord.Embed(color=config.Colors.SUCCESS)
            header = config.Design.header("PURCHASED", 28)
            embed.description = f"```\n{header}\n```"
            
            content = (
                f"\n{config.Design.field('box', box['name'], 20)}\n"
                f"{config.Design.field('cost', f'{cost:.2f} BST', 20)}\n"
                f"{config.Design.field('new balance', f'{new_balance:.2f} BST', 20)}\n"
            )
            
            embed.add_field(name="\u200b", value=content, inline=False)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(
                f"Error: {str(e)}",
                ephemeral=True
            )
    
    async def handle_open(self, interaction: discord.Interaction):
        """Show box selection dropdown"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get user's boxes
            async with db.pool.acquire() as conn:
                boxes = await conn.fetch(
                    """SELECT b.box_id, bt.name, bt.box_type_id
                       FROM boxes b
                       JOIN box_types bt ON b.box_type_id = bt.box_type_id
                       WHERE b.owner_user_id = $1 AND b.status = 'owned'
                       ORDER BY bt.cost_bst DESC""",
                    interaction.user.id
                )
            
            if not boxes:
                await interaction.followup.send(
                    embed=discord.Embed(
                        description=config.Design.small_caps("you don't have any boxes"),
                        color=config.Colors.ERROR
                    ),
                    ephemeral=True
                )
                return
            
            # Create dropdown view
            view = BoxSelectionView(self, boxes)
            
            embed = discord.Embed(color=config.Colors.PRIMARY)
            header = config.Design.header("SELECT BOX", 28)
            embed.description = f"```\n{header}\n```\n{config.Design.small_caps('choose a box to open')}"
            
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)
    
    async def open_box(self, interaction: discord.Interaction, box_id: str):
        """Open a specific box"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get box info
            async with db.pool.acquire() as conn:
                box = await conn.fetchrow(
                    """SELECT b.*, bt.name as box_name, bt.box_type_id
                       FROM boxes b
                       JOIN box_types bt ON b.box_type_id = bt.box_type_id
                       WHERE b.box_id = $1 AND b.owner_user_id = $2 AND b.status = 'owned'""",
                    box_id, interaction.user.id
                )
            
            if not box:
                await interaction.followup.send("Box not found!", ephemeral=True)
                return
            
            # Opening animation
            loading = discord.Embed(
                description=f"```\n{config.Design.header('OPENING', 28)}\n```\n{config.Design.small_caps('rolling...')}",
                color=config.Colors.YELLOW
            )
            await interaction.followup.send(embed=loading, ephemeral=True)
            await asyncio.sleep(2)
            
            # Roll for item
            box_type = box['box_type_id']
            item_name = self.roll_item(box_type)
            
            # Mark box as opened and add item
            async with db.pool.acquire() as conn:
                async with conn.transaction():
                    # Update box status
                    await conn.execute(
                        "UPDATE boxes SET status = 'opened', opened_at = NOW() WHERE box_id = $1",
                        box_id
                    )
                    
                    # Get item info
                    item = await conn.fetchrow(
                        "SELECT * FROM items WHERE name = $1",
                        item_name
                    )
                    
                    if item:
                        # Add to user inventory
                        await conn.execute(
                            """INSERT INTO user_items (user_id, item_id, quantity, obtained_from)
                               VALUES ($1, $2, 1, $3)
                               ON CONFLICT (user_id, item_id)
                               DO UPDATE SET quantity = user_items.quantity + 1""",
                            interaction.user.id, item['item_id'], box_id
                        )
            
            # Show result
            result = discord.Embed(color=config.Colors.SUCCESS)
            header = config.Design.header("REWARD", 28)
            result.description = f"```\n{header}\n```"
            
            item_value = float(item['value_usd']) if item else 0
            
            content = (
                f"\n{config.Design.field('opened', box['box_name'], 20)}\n"
                f"{config.Design.field('received', item_name, 20)}\n"
                f"{config.Design.field('value', f'${item_value:.2f}', 20)}\n"
            )
            
            result.add_field(name="\u200b", value=content, inline=False)
            
            await interaction.edit_original_response(embed=result)
            
        except Exception as e:
            await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)
    
    def roll_item(self, box_type: str) -> str:
        """Roll for item based on box type"""
        rates = self.drop_rates.get(box_type, self.drop_rates['base'])
        
        total_weight = sum(item['weight'] for item in rates)
        roll = random.uniform(0, total_weight)
        
        current = 0
        for item in rates:
            current += item['weight']
            if roll <= current:
                return item['item']
        
        return rates[0]['item']  # Fallback
    
    # Manual commands for users who prefer typing
    @app_commands.command(name="buybox", description="Buy a mystery box manually")
    @app_commands.describe(box_type="Type of box (base or gold)")
    async def buybox_command(self, interaction: discord.Interaction, box_type: str):
        """Manual buy command"""
        if box_type.lower() not in ['base', 'gold']:
            await interaction.response.send_message("Use 'base' or 'gold'", ephemeral=True)
            return
        
        await self.handle_purchase(interaction, box_type.lower())
    
    @app_commands.command(name="openbox", description="Open a mystery box manually")
    async def openbox_command(self, interaction: discord.Interaction):
        """Manual open command"""
        await self.handle_open(interaction)

# ==================== VIEWS ====================

class BoxShopView(discord.ui.View):
    """Persistent view for box shop"""
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
    
    @discord.ui.button(
        label="Buy Base Box (1 BST)",
        style=discord.ButtonStyle.primary,
        custom_id="persistent_buy_base"
    )
    async def buy_base(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_purchase(interaction, 'base')
    
    @discord.ui.button(
        label="Buy Gold Box (2.5 BST)",
        style=discord.ButtonStyle.success,
        custom_id="persistent_buy_gold"
    )
    async def buy_gold(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_purchase(interaction, 'gold')

class BoxOpenView(discord.ui.View):
    """Persistent view for opening boxes"""
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
    
    @discord.ui.button(
        label="Open a Box",
        style=discord.ButtonStyle.primary,
        custom_id="persistent_open_box"
    )
    async def open_box(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_open(interaction)

class BoxSelectionView(discord.ui.View):
    """Dropdown for selecting which box to open"""
    def __init__(self, cog, boxes):
        super().__init__(timeout=60)
        self.cog = cog
        
        # Create dropdown options
        options = []
        for box in boxes[:25]:  # Discord limit
            options.append(discord.SelectOption(
                label=box['name'],
                value=str(box['box_id']),
                description=f"Box ID: {str(box['box_id'])[:8]}..."
            ))
        
        select = discord.ui.Select(
            placeholder="Choose a box to open...",
            options=options
        )
        
        async def select_callback(interaction: discord.Interaction):
            await self.cog.open_box(interaction, select.values[0])
        
        select.callback = select_callback
        self.add_item(select)

async def setup(bot):
    await bot.add_cog(Boxes(bot))