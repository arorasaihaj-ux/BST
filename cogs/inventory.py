import discord
from discord.ext import commands
from discord import app_commands
import os

class Inventory(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="inventory", description="View your inventory")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def inventory(self, interaction: discord.Interaction, user: discord.Member = None):
        target = user or interaction.user
        
        try:
            balance = await self.bot.db.get_balance(target.id)
            inventory = await self.bot.db.get_inventory(target.id)
            
            embed = discord.Embed(
                title=f"{target.display_name}'s Inventory",
                color=0x5865F2
            )
            
            # BST Balance
            embed.add_field(
                name="BST Balance",
                value=f"```{balance:.2f} BST```",
                inline=False
            )
            
            # Unopened Boxes
            if inventory['boxes']:
                box_list = []
                for box in inventory['boxes']:
                    box_name = "Base Box" if box['box_type'] == 'base' else "Gold Box"
                    box_list.append(f"• {box_name} x{box['count']}")
                
                embed.add_field(
                    name="Unopened Boxes",
                    value="\n".join(box_list),
                    inline=False
                )
            else:
                embed.add_field(
                    name="Unopened Boxes",
                    value="*No boxes available*",
                    inline=False
                )
            
            # Items Won
            if inventory['items']:
                items_list = []
                for item in inventory['items'][:20]:
                    items_list.append(f"• {item['item_name']} x{item['quantity']}")
                
                if len(inventory['items']) > 20:
                    items_list.append(f"\n*...and {len(inventory['items']) - 20} more items*")
                
                embed.add_field(
                    name="Items Won from Boxes",
                    value="\n".join(items_list),
                    inline=False
                )
            else:
                embed.add_field(
                    name="Items Won from Boxes",
                    value="*No items yet*\n\nOpen boxes to win items!",
                    inline=False
                )
            
            embed.set_footer(text="Use /boxpanel to purchase boxes")
            
            # PUBLIC - SEND TO CHANNEL
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(f"Error: {str(e)}")

async def setup(bot):
    await bot.add_cog(Inventory(bot))
