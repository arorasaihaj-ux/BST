import discord
from discord.ext import commands
from discord import app_commands
import os

class Inventory(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="inventory", description="View inventory")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def inventory(self, interaction: discord.Interaction, user: discord.Member = None):
        target = user or interaction.user
        
        try:
            balance = await self.bot.db.get_balance(target.id)
            inventory = await self.bot.db.get_inventory(target.id)
            
            embed = discord.Embed(
                title="𝐈𝐍𝐕𝐄𝐍𝐓𝐎𝐑𝐘",
                description=f"**{target.display_name}**\n**𝐁𝐒𝐓:** {balance:.2f}",
                color=0x2B2D31
            )
            
            # BOXES
            if inventory['boxes']:
                box_list = ""
                for box in inventory['boxes']:
                    box_name = {
                        'box_1': '𝟏 𝐁𝐒𝐓',
                        'box_2': '𝟐.𝟓 𝐁𝐒𝐓',
                        'box_3': '𝟓 𝐁𝐒𝐓',
                        'box_4': '𝟏𝟎 𝐁𝐒𝐓'
                    }.get(box['box_type'], box['box_type'])
                    box_list += f"**{box_name}** x{box['count']}\n"
                
                embed.add_field(
                    name="𝐁𝐨𝐱𝐞𝐬",
                    value=box_list,
                    inline=False
                )
            else:
                embed.add_field(
                    name="𝐁𝐨𝐱𝐞𝐬",
                    value="𝐍𝐨 𝐛𝐨𝐱𝐞𝐬",
                    inline=False
                )
            
            # ITEMS
            if inventory['items']:
                items_list = ""
                for item in inventory['items'][:25]:
                    items_list += f"**{item['item_name']}** x{item['quantity']}\n"
                
                if len(inventory['items']) > 25:
                    items_list += f"\n...{len(inventory['items']) - 25} 𝐦𝐨𝐫𝐞"
                
                embed.add_field(
                    name="𝐈𝐭𝐞𝐦𝐬",
                    value=items_list,
                    inline=False
                )
            else:
                embed.add_field(
                    name="𝐈𝐭𝐞𝐦𝐬",
                    value="𝐍𝐨 𝐢𝐭𝐞𝐦𝐬",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(f"**𝐄𝐑𝐑𝐎𝐑**\n{e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Inventory(bot))
