import discord
from discord.ext import commands
from discord import app_commands
import config
from database import db
from utils.checks import is_manager

class Shop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="shop", description="Browse the shop")
    async def shop(self, interaction: discord.Interaction):
        """View shop items"""
        try:
            items = await db.get_shop_items()
            
            if not items:
                await interaction.response.send_message(
                    "No items available in the shop right now.",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(color=config.Colors.PRIMARY)
            
            header = config.Design.header("SHOP", 28)
            embed.description = f"\n{header}\n"
            
            content = ""
            for item in items:
                content += f"\n{config.Design.section(item['name'])}\n"
                content += f"Price: {item['price_bst']} BST\n"
                content += f"Stock: {item['quantity']}\n"
                if item['description']:
                    content += f"{item['description']}\n"
                content += f"ID: `{item['shop_item_id']}`\n"
            
            embed.add_field(name="\u200b", value=content, inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="buy", description="Buy an item from the shop")
    async def buy_item(self, interaction: discord.Interaction, item_id: str):
        """Purchase item from shop"""
        try:
            item = await db.purchase_shop_item(interaction.user.id, item_id)
            
            embed = discord.Embed(
                description=config.Design.small_caps(
                    f"purchased {item['name']} for {item['price_bst']} bst"
                ),
                color=config.Colors.SUCCESS
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @is_manager()
    @app_commands.command(name="listitem", description="List a new item in the shop")
    async def list_item(self, interaction: discord.Interaction, name: str, price: float, quantity: int, description: str = None):
        """List new item in shop (managers only)"""
        try:
            # First get or create the base item
            async with db.pool.acquire() as conn:
                base_item = await conn.fetchrow("""
                    INSERT INTO items (name, value_usd)
                    VALUES ($1, $2)
                    ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                    RETURNING item_id
                """, name, price * 0.8)  # Estimate USD value
                
                # Create shop listing
                shop_item = await conn.fetchrow("""
                    INSERT INTO shop_items (base_item_id, name, description, price_bst, quantity, created_by)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING *
                """, base_item['item_id'], name, description, price, quantity, interaction.user.id)
            
            embed = discord.Embed(
                description=config.Design.small_caps(
                    f"listed {name} in shop for {price} bst (quantity: {quantity})"
                ),
                color=config.Colors.SUCCESS
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @is_manager()
    @app_commands.command(name="removeshopitem", description="Remove an item from the shop")
    async def remove_shop_item(self, interaction: discord.Interaction, item_id: str):
        """Remove shop item (managers only)"""
        try:
            async with db.pool.acquire() as conn:
                result = await conn.execute("""
                    UPDATE shop_items SET is_active = false
                    WHERE shop_item_id = $1
                """, item_id)
                
                if "UPDATE 1" in result:
                    await interaction.response.send_message(
                        "Item removed from shop.",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        "Item not found.",
                        ephemeral=True
                    )
                    
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @is_manager()
    @app_commands.command(name="restockshop", description="Restock a shop item")
    async def restock_shop(self, interaction: discord.Interaction, item_id: str, quantity: int):
        """Restock shop item (managers only)"""
        try:
            async with db.pool.acquire() as conn:
                result = await conn.execute("""
                    UPDATE shop_items SET quantity = quantity + $1
                    WHERE shop_item_id = $2
                """, quantity, item_id)
                
                if "UPDATE 1" in result:
                    await interaction.response.send_message(
                        f"Restocked item with {quantity} more units.",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        "Item not found.",
                        ephemeral=True
                    )
                    
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Shop(bot))