import discord
from discord.ext import commands
from discord import app_commands
from database import db

class TestCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="test", description="Test if bot is working")
    async def test_command(self, interaction: discord.Interaction):
        """Test command to verify bot functionality"""
        try:
            # Test database connection
            user_data = await db.get_user(interaction.user.id)
            
            embed = discord.Embed(
                title="✅ Bot Status",
                description="Bot is working correctly!",
                color=0x00ff00
            )
            embed.add_field(name="Database", value="✅ Connected", inline=True)
            embed.add_field(name="Commands", value="✅ Working", inline=True)
            embed.add_field(name="User Data", value="✅ Retrieved", inline=True)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            error_embed = discord.Embed(
                title="❌ Bot Error",
                description="There's an issue with the bot",
                color=0xff0000
            )
            error_embed.add_field(name="Error", value=str(e), inline=False)
            await interaction.response.send_message(embed=error_embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(TestCog(bot))