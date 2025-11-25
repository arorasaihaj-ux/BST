import discord
from discord.ext import commands
from discord import app_commands
import os

class Inventory(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="inventory", description="View BST balance, boxes, and items")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def inventory(self, interaction: discord.Interaction, user: discord.Member = None):
        """View user inventory"""
        target = user or interaction.user
        
        try:
            # Get BST balance
            balance = await self.bot.db.get_balance(target.id)
            
            # Get inventory
            inventory = await self.bot.db.get_inventory(target.id)
            
            embed = discord.Embed(
                title=f"📦 {target.display_name}'s Inventory",
                color=discord.Color.blue()
            )
            
            # BST Balance
            embed.add_field(
                name="💰 BST Balance",
                value=f"**{balance:.2f} BST**",
                inline=False
            )
            
            # Unopened Boxes
            if inventory['boxes']:
                box_text = ""
                for box in inventory['boxes']:
                    box_emoji = "📦" if box['box_type'] == 'base' else "🎁"
                    box_text += f"{box_emoji} **{box['box_type'].title()} Box** x{box['count']}\n"
                
                embed.add_field(
                    name="📦 Unopened Boxes",
                    value=box_text,
                    inline=False
                )
            else:
                embed.add_field(
                    name="📦 Unopened Boxes",
                    value="*No boxes*",
                    inline=False
                )
            
            # Items Won from Boxes
            if inventory['items']:
                # Group items
                items_text = ""
                for item in inventory['items'][:15]:  # Limit to 15 items
                    items_text += f"• **{item['item_name']}** x{item['quantity']}\n"
                
                if len(inventory['items']) > 15:
                    items_text += f"\n*...and {len(inventory['items']) - 15} more items*"
                
                embed.add_field(
                    name="🎁 Items Won",
                    value=items_text,
                    inline=False
                )
            else:
                embed.add_field(
                    name="🎁 Items Won",
                    value="*No items yet*\n\n*Open boxes to get items!*",
                    inline=False
                )
            
            embed.set_footer(text="Use /boxpanel to purchase boxes • Open boxes with the opening panel")
            
            await interaction.response.send_message(embed=embed, ephemeral=target != interaction.user)
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Inventory(bot))
