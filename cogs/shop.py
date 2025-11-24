import discord
from discord.ext import commands
from discord import app_commands
import config
from database import db
from utils.checks import is_manager

class Shop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="listitem", description="List an item in the shop (Admin only)")
    @app_commands.describe(
        name="Item name",
        description="Item description",
        price="Price in BST",
        stock="Stock (-1 for unlimited)"
    )
    async def list_shop_item(
        self,
        interaction: discord.Interaction,
        name: str,
        description: str,
        price: float,
        stock: int = -1
    ):
        """List item in shop (managers only)"""
        # Check permissions
        if interaction.user.id != config.OWNER_ID:
            if not any(role.id in config.MANAGER_ROLES for role in interaction.user.roles):
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description=config.Design.small_caps("manager role required"),
                        color=config.Colors.ERROR
                    ),
                    ephemeral=True
                )
                return
        
        await interaction.response.defer(ephemeral=True)
        
        if price <= 0:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=config.Design.small_caps("price must be positive"),
                    color=config.Colors.ERROR
                ),
                ephemeral=True
            )
            return
        
        # Create shop item
        item_id = await db.create_shop_item(
            name=name,
            description=description,
            price=price,
            stock=stock,
            created_by=interaction.user.id
        )
        
        # Create shop panel
        embed = self.create_shop_item_embed(name, description, price, stock)
        view = ShopItemView(item_id)
        
        panel_message = await interaction.channel.send(embed=embed, view=view)
        
        # Update with message ID
        async with db.pool.acquire() as conn:
            await conn.execute(
                "UPDATE shop_items SET panel_message_id = $1 WHERE shop_item_id = $2",
                panel_message.id, item_id
            )
        
        await interaction.followup.send(
            embed=discord.Embed(
                description=config.Design.small_caps(f"item listed • {name}"),
                color=config.Colors.SUCCESS
            ),
            ephemeral=True
        )
    
    def create_shop_item_embed(self, name: str, description: str, price: float, stock: int):
        """Create shop item embed"""
        embed = discord.Embed(color=config.Colors.PRIMARY)
        
        header = config.Design.header("SHOP ITEM", 28)
        embed.description = f"```\n{header}\n```"
        
        stock_text = "Unlimited" if stock == -1 else f"{stock} left"
        
        content = (
            f"\n{config.Design.section(name.upper())}\n"
            f"{description}\n\n"
            f"{config.Design.field('price', f'{price:.2f} BST', 20)}\n"
            f"{config.Design.field('stock', stock_text, 20)}\n"
        )
        
        embed.add_field(name="\u200b", value=content, inline=False)
        
        return embed
    
    @commands.hybrid_command(name="shoplist", description="View all shop items")
    async def view_shop(self, ctx):
        """View all shop items"""
        items = await db.get_shop_items()
        
        if not items:
            embed = discord.Embed(
                description=config.Design.small_caps("shop is empty"),
                color=config.Colors.INFO
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(color=config.Colors.PRIMARY)
        header = config.Design.header("SHOP", 28)
        embed.description = f"```\n{header}\n```"
        
        for item in items:
            stock_text = "∞" if item['stock'] == -1 else f"{item['stock']}"
            
            item_info = (
                f"\n{config.Design.section(item['name'].upper())}\n"
                f"{item['description']}\n"
                f"{config.Design.field('price', f'{item["price_bst"]:.2f} BST', 20)}\n"
                f"{config.Design.field('stock', stock_text, 20)}\n"
            )
            
            embed.add_field(name="\u200b", value=item_info, inline=False)
        
        await ctx.send(embed=embed)
    
    @app_commands.command(name="removeitem", description="Remove item from shop (Admin only)")
    @app_commands.describe(item_name="Name of item to remove")
    async def remove_shop_item(self, interaction: discord.Interaction, item_name: str):
        """Remove shop item (managers only)"""
        # Check permissions
        if interaction.user.id != config.OWNER_ID:
            if not any(role.id in config.MANAGER_ROLES for role in interaction.user.roles):
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description=config.Design.small_caps("manager role required"),
                        color=config.Colors.ERROR
                    ),
                    ephemeral=True
                )
                return
        
        await interaction.response.defer(ephemeral=True)
        
        async with db.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE shop_items SET is_active = FALSE WHERE name ILIKE $1",
                item_name
            )
        
        if result == "UPDATE 0":
            await interaction.followup.send(
                embed=discord.Embed(
                    description=config.Design.small_caps("item not found"),
                    color=config.Colors.ERROR
                ),
                ephemeral=True
            )
            return
        
        await interaction.followup.send(
            embed=discord.Embed(
                description=config.Design.small_caps(f"removed • {item_name}"),
                color=config.Colors.SUCCESS
            ),
            ephemeral=True
        )

class ShopItemView(discord.ui.View):
    def __init__(self, item_id: str):
        super().__init__(timeout=None)
        self.item_id = item_id
    
    @discord.ui.button(label="💳 Buy", style=discord.ButtonStyle.green, custom_id="buy_shop_item")
    async def buy_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Buy shop item"""
        await interaction.response.defer(ephemeral=True)
        
        # Purchase item
        result = await db.purchase_shop_item(self.item_id, interaction.user.id)
        
        if not result['success']:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=config.Design.small_caps(result['error']),
                    color=config.Colors.ERROR
                ),
                ephemeral=True
            )
            return
        
        # Success
        embed = discord.Embed(color=config.Colors.SUCCESS)
        
        header = config.Design.header("PURCHASED", 28)
        embed.description = f"```\n{header}\n```"
        
        content = (
            f"\n{config.Design.field('item', result['item_name'], 20)}\n"
            f"{config.Design.field('cost', f'{result["price"]:.2f} BST', 20)}\n"
            f"{config.Design.field('new balance', f'{result["new_balance"]:.2f} BST', 20)}\n"
        )
        
        embed.add_field(name="Success", value=content, inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        # Update panel stock if needed
        async with db.pool.acquire() as conn:
            item = await conn.fetchrow(
                "SELECT * FROM shop_items WHERE shop_item_id = $1",
                self.item_id
            )
            
            if item and item['stock'] == 0:
                # Out of stock - disable button
                button.disabled = True
                button.label = "Out of Stock"
                button.style = discord.ButtonStyle.gray
                
                try:
                    await interaction.message.edit(view=self)
                except:
                    pass

async def setup(bot):
    await bot.add_cog(Shop(bot))