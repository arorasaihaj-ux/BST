import discord
from discord.ext import commands
from discord import app_commands
import os

# Channels where messages count
COUNTING_CHANNELS = [int(x.strip()) for x in os.getenv('COUNTING_CHANNELS', '').split(',') if x.strip()]
MESSAGES_PER_BST = 800  # Changed from 100 to 800

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        """Track messages and award BST"""
        # Ignore bots
        if message.author.bot:
            return
        
        # Check if in counting channel
        if COUNTING_CHANNELS and message.channel.id not in COUNTING_CHANNELS:
            return

        try:
            # Increment message count
            new_count = await self.bot.db.increment_messages(message.author.id)
            
            # Check if earned BST
            if new_count % MESSAGES_PER_BST == 0:
                # Award 1 BST
                await self.bot.db.add_bst(message.author.id, 1.0)
                
                # Reset counter
                await self.bot.db.reset_messages(message.author.id)
                
                # Get new balance
                balance = await self.bot.db.get_balance(message.author.id)
                
                # Send notification
                embed = discord.Embed(
                    title="🎉 BST Earned!",
                    description=f"{message.author.mention} earned **1 BST** for sending {MESSAGES_PER_BST} messages!",
                    color=discord.Color.gold()
                )
                embed.add_field(name="💰 New Balance", value=f"**{balance:.2f} BST**")
                
                await message.channel.send(embed=embed, delete_after=10)
                
        except Exception as e:
            print(f"Error tracking message: {e}")

    @app_commands.command(name="balance", description="Check BST balance")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def balance(self, interaction: discord.Interaction, user: discord.Member = None):
        """Check BST balance"""
        target = user or interaction.user
        
        try:
            balance = await self.bot.db.get_balance(target.id)
            msg_count = await self.bot.db.get_message_count(target.id)
            remaining = MESSAGES_PER_BST - msg_count
            progress = (msg_count / MESSAGES_PER_BST) * 100
            
            embed = discord.Embed(
                title=f"💰 {target.display_name}'s Balance",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="BST Balance",
                value=f"**{balance:.2f} BST**",
                inline=False
            )
            
            embed.add_field(
                name="📊 Progress to Next BST",
                value=f"**{msg_count}/{MESSAGES_PER_BST}** messages ({progress:.1f}%)\n{remaining} messages remaining",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="leaderboard", description="View BST leaderboard")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def leaderboard(self, interaction: discord.Interaction):
        """Show BST leaderboard"""
        try:
            balances = await self.bot.db.get_all_balances()
            
            if not balances:
                await interaction.response.send_message(
                    "No one has BST yet!",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(
                title="🏆 BST Leaderboard",
                color=discord.Color.gold()
            )
            
            medals = ["🥇", "🥈", "🥉"]
            
            for i, (user_id, balance) in enumerate(balances[:10], 1):
                member = interaction.guild.get_member(user_id)
                if not member:
                    continue
                
                medal = medals[i-1] if i <= 3 else f"#{i}"
                
                embed.add_field(
                    name=f"{medal} {member.display_name}",
                    value=f"💰 **{balance:.2f} BST**",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Economy(bot))
