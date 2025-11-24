import discord
from discord.ext import commands
from datetime import datetime, timedelta
import config
from database import db

class Marketplace(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command(name="market", description="Browse marketplace listings")
    async def market(self, ctx):
        """View marketplace"""
        async with db.pool.acquire() as conn:
            listings = await conn.fetch(
                """SELECT ml.*, u.discord_tag, bt.name as box_name, i.name as item_name
                   FROM market_listings ml
                   LEFT JOIN users u ON ml.seller_id = u.user_id
                   LEFT JOIN box_types bt ON ml.box_type_id = bt.box_type_id
                   LEFT JOIN items i ON ml.item_id = i.item_id
                   WHERE ml.status = 'active' AND ml.expires_at > NOW()
                   ORDER BY ml.created_at DESC
                   LIMIT 10"""
            )
        
        if not listings:
            embed = discord.Embed(
                description=config.Design.small_caps("no active listings"),
                color=config.Colors.INFO
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(color=config.Colors.PRIMARY)
        header = config.Design.header("MARKET", 28)
        embed.description = f"```\n{header}\n```"
        
        view = discord.ui.View(timeout=300)
        
        for listing in listings:
            item_name = listing['box_name'] or listing['item_name']
            seller = listing['discord_tag'] or f"User {listing['seller_id']}"
            
            listing_text = (
                f"\n{config.Design.section(item_name)}\n"
                f"{config.Design.field('seller', seller, 20)}\n"
                f"{config.Design.field('price', f'{listing["price_bst"]:.2f} BST', 20)}\n"
                f"{config.Design.field('quantity', str(listing['quantity']), 20)}\n"
            )
            
            embed.add_field(name="\u200b", value=listing_text, inline=False)
            
            # Add buy button
            if listing['seller_id'] != ctx.author.id:
                button = discord.ui.Button(
                    label=f"Buy for {listing['price_bst']:.2f} BST",
                    style=discord.ButtonStyle.green,
                    custom_id=f"buy:{listing['listing_id']}"
                )
                
                async def buy_callback(interaction: discord.Interaction, listing_id=listing['listing_id']):
                    await self.handle_purchase(interaction, listing_id)
                
                button.callback = buy_callback
                view.add_item(button)
        
        await ctx.send(embed=embed, view=view)
    
    async def handle_purchase(self, interaction: discord.Interaction, listing_id):
        """Handle marketplace purchase"""
        await interaction.response.defer(ephemeral=True)
        
        async with db.pool.acquire() as conn:
            async with conn.transaction():
                # Get listing
                listing = await conn.fetchrow(
                    """SELECT ml.*, bt.name as box_name, i.name as item_name
                       FROM market_listings ml
                       LEFT JOIN box_types bt ON ml.box_type_id = bt.box_type_id
                       LEFT JOIN items i ON ml.item_id = i.item_id
                       WHERE ml.listing_id = $1 AND ml.status = 'active'
                       FOR UPDATE""",
                    listing_id
                )
                
                if not listing:
                    embed = discord.Embed(
                        description=config.Design.small_caps("listing no longer available"),
                        color=config.Colors.ERROR
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
                
                # Check buyer balance
                buyer_balance = await db.get_balance(interaction.user.id)
                total_cost = float(listing['price_bst'])
                
                if buyer_balance < total_cost:
                    embed = discord.Embed(
                        description=config.Design.small_caps("insufficient balance"),
                        color=config.Colors.ERROR
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
                
                # Calculate fee
                fee = total_cost * (config.MARKET_FEE / 100)
                seller_receives = total_cost - fee
                
                # Transfer BST
                await conn.execute(
                    "UPDATE users SET bst_balance = bst_balance - $1 WHERE user_id = $2",
                    total_cost, interaction.user.id
                )
                await conn.execute(
                    "UPDATE users SET bst_balance = bst_balance + $1 WHERE user_id = $2",
                    seller_receives, listing['seller_id']
                )
                
                # Transfer item/box
                if listing['item_type'] == 'box':
                    # Transfer box ownership
                    await conn.execute(
                        """UPDATE boxes 
                           SET owner_user_id = $1 
                           WHERE box_type_id = $2 AND owner_user_id = $3 AND status = 'stored'
                           LIMIT $4""",
                        interaction.user.id, listing['box_type_id'], 
                        listing['seller_id'], listing['quantity']
                    )
                elif listing['item_type'] == 'item':
                    # Transfer items
                    # Check if buyer already has this item
                    existing = await conn.fetchrow(
                        "SELECT user_item_id, quantity FROM user_items WHERE user_id = $1 AND item_id = $2",
                        interaction.user.id, listing['item_id']
                    )
                    
                    if existing:
                        await conn.execute(
                            "UPDATE user_items SET quantity = quantity + $1 WHERE user_item_id = $2",
                            listing['quantity'], existing['user_item_id']
                        )
                    else:
                        await conn.execute(
                            """INSERT INTO user_items (user_id, item_id, quantity)
                               VALUES ($1, $2, $3)""",
                            interaction.user.id, listing['item_id'], listing['quantity']
                        )
                    
                    # Remove from seller
                    await conn.execute(
                        """UPDATE user_items 
                           SET quantity = quantity - $1 
                           WHERE user_id = $2 AND item_id = $3""",
                        listing['quantity'], listing['seller_id'], listing['item_id']
                    )
                
                # Mark listing as sold
                await conn.execute(
                    "UPDATE market_listings SET status = 'sold' WHERE listing_id = $1",
                    listing_id
                )
                
                # Log transaction
                await conn.execute(
                    """INSERT INTO transactions (tx_type, from_user, to_user, amount_bst, item_data)
                       VALUES ('market_purchase', $1, $2, $3, $4)""",
                    interaction.user.id, listing['seller_id'], total_cost,
                    {'listing_id': str(listing_id), 'item': listing['box_name'] or listing['item_name'], 'fee': float(fee)}
                )
        
        # Success message
        embed = discord.Embed(color=config.Colors.SUCCESS)
        
        header = config.Design.header("PURCHASED", 28)
        embed.description = f"```\n{header}\n```"
        
        item_name = listing['box_name'] or listing['item_name']
        content = (
            f"\n{config.Design.field('item', item_name, 20)}\n"
            f"{config.Design.field('quantity', str(listing['quantity']), 20)}\n"
            f"{config.Design.field('cost', f'{total_cost:.2f} BST', 20)}\n"
        )
        
        embed.add_field(name="Success", value=content, inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @commands.hybrid_command(name="list", description="Create a marketplace listing")
    async def create_listing(self, ctx):
        """Create a marketplace listing"""
        # Show modal for listing creation
        modal = ListingModal()
        await ctx.interaction.response.send_modal(modal)

class ListingModal(discord.ui.Modal, title="Create Listing"):
    item_type = discord.ui.TextInput(
        label="Item Type (box/item)",
        placeholder="box or item",
        required=True,
        max_length=10
    )
    
    item_name = discord.ui.TextInput(
        label="Item Name",
        placeholder="Base Mystery Box",
        required=True,
        max_length=100
    )
    
    quantity = discord.ui.TextInput(
        label="Quantity",
        placeholder="1",
        required=True,
        max_length=5
    )
    
    price = discord.ui.TextInput(
        label="Price (BST)",
        placeholder="1.50",
        required=True,
        max_length=10
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            qty = int(self.quantity.value)
            price = float(self.price.value)
            
            if qty <= 0 or price <= 0:
                raise ValueError("Values must be positive")
        except ValueError:
            await interaction.followup.send(
                config.Design.small_caps("invalid quantity or price"),
                ephemeral=True
            )
            return
        
        item_type = self.item_type.value.lower()
        
        if item_type not in ['box', 'item']:
            await interaction.followup.send(
                config.Design.small_caps("item type must be 'box' or 'item'"),
                ephemeral=True
            )
            return
        
        # Create listing
        async with db.pool.acquire() as conn:
            # Verify user owns the items
            if item_type == 'box':
                box_type = await conn.fetchrow(
                    "SELECT box_type_id FROM box_types WHERE name ILIKE $1",
                    self.item_name.value
                )
                
                if not box_type:
                    await interaction.followup.send(
                        config.Design.small_caps("box type not found"),
                        ephemeral=True
                    )
                    return
                
                user_boxes = await conn.fetchval(
                    """SELECT COUNT(*) FROM boxes 
                       WHERE owner_user_id = $1 AND box_type_id = $2 AND status = 'stored'""",
                    interaction.user.id, box_type['box_type_id']
                )
                
                if user_boxes < qty:
                    await interaction.followup.send(
                        config.Design.small_caps("you don't have enough boxes"),
                        ephemeral=True
                    )
                    return
                
                listing_id = await conn.fetchval(
                    """INSERT INTO market_listings 
                       (seller_id, item_type, box_type_id, quantity, price_bst, expires_at)
                       VALUES ($1, 'box', $2, $3, $4, $5)
                       RETURNING listing_id""",
                    interaction.user.id, box_type['box_type_id'], qty, price,
                    datetime.now() + timedelta(days=7)
                )
            else:
                item = await conn.fetchrow(
                    "SELECT item_id FROM items WHERE name ILIKE $1",
                    self.item_name.value
                )
                
                if not item:
                    await interaction.followup.send(
                        config.Design.small_caps("item not found"),
                        ephemeral=True
                    )
                    return
                
                user_item = await conn.fetchrow(
                    "SELECT quantity FROM user_items WHERE user_id = $1 AND item_id = $2",
                    interaction.user.id, item['item_id']
                )
                
                if not user_item or user_item['quantity'] < qty:
                    await interaction.followup.send(
                        config.Design.small_caps("you don't have enough items"),
                        ephemeral=True
                    )
                    return
                
                listing_id = await conn.fetchval(
                    """INSERT INTO market_listings 
                       (seller_id, item_type, item_id, quantity, price_bst, expires_at)
                       VALUES ($1, 'item', $2, $3, $4, $5)
                       RETURNING listing_id""",
                    interaction.user.id, item['item_id'], qty, price,
                    datetime.now() + timedelta(days=7)
                )
        
        embed = discord.Embed(
            description=config.Design.small_caps("listing created successfully"),
            color=config.Colors.SUCCESS
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Marketplace(bot))