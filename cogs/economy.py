import discord
from discord.ext import commands
from discord import app_commands
import os

COUNTING_CHANNELS = [int(x.strip()) for x in os.getenv('COUNTING_CHANNELS', '').split(',') if x.strip()]
MESSAGES_PER_BST = 800

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        
        if COUNTING_CHANNELS and message.channel.id not in COUNTING_CHANNELS:
            return

        try:
            new_count = await self.bot.db.increment_messages(message.author.id)
            
            if new_count % MESSAGES_PER_BST == 0:
                await self.bot.db.add_bst(message.author.id, 1.0)
                await self.bot.db.reset_messages(message.author.id)
                
                balance = await self.bot.db.get_balance(message.author.id)
                
                embed = discord.Embed(
                    title="🎉 BST Earned!",
                    description=f"{message.author.mention} earned **1 BST**!",
                    color=discord.Color.gold()
                )
                embed.add_field(name="💰 Balance", value=f"**{balance:.2f} BST**")
                
                await message.channel.send(embed=embed, delete_after=10)
        except Exception as e:
            print(f"Message tracking error: {e}")

    @app_commands.command(name="balance", description="Check your BST balance")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def balance(self, interaction: discord.Interaction, user: discord.Member = None):
        """Public balance check"""
        target = user or interaction.user
        
        try:
            balance = await self.bot.db.get_balance(target.id)
            msg_count = await self.bot.db.get_message_count(target.id)
            remaining = MESSAGES_PER_BST - msg_count
            progress = (msg_count / MESSAGES_PER_BST) * 100
            
            # Create progress bar
            filled = int(progress / 5)
            bar = "█" * filled + "░" * (20 - filled)
            
            embed = discord.Embed(
                title=f"💰 {target.display_name}'s Balance",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="BST Balance",
                value=f"# {balance:.2f} BST",
                inline=False
            )
            
            embed.add_field(
                name="📊 Progress to Next BST",
                value=f"`{bar}` {progress:.1f}%\n**{msg_count}/{MESSAGES_PER_BST}** messages ({remaining} left)",
                inline=False
            )
            
            embed.set_footer(text="Send messages to earn BST!")
            
            # Public if checking others, private if checking self
            await interaction.response.send_message(embed=embed, ephemeral=(target == interaction.user))
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="messages", description="Check message progress")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def messages(self, interaction: discord.Interaction):
        """Show message progress with bar"""
        try:
            msg_count = await self.bot.db.get_message_count(interaction.user.id)
            remaining = MESSAGES_PER_BST - msg_count
            progress = (msg_count / MESSAGES_PER_BST) * 100
            
            # Fancy progress bar
            filled = int(progress / 2.5)
            bar = "▓" * filled + "░" * (40 - filled)
            
            embed = discord.Embed(
                title="📊 Message Progress",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="Progress Bar",
                value=f"```{bar}```",
                inline=False
            )
            
            embed.add_field(
                name="📈 Stats",
                value=f"**{msg_count}/{MESSAGES_PER_BST}** messages ({progress:.1f}%)",
                inline=True
            )
            
            embed.add_field(
                name="⏳ Remaining",
                value=f"**{remaining}** messages until next BST",
                inline=True
            )
            
            embed.set_footer(text="Keep chatting to earn BST!")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="leaderboard", description="View BST leaderboard")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def leaderboard(self, interaction: discord.Interaction):
        """Public leaderboard"""
        try:
            balances = await self.bot.db.get_all_balances()
            
            if not balances:
                await interaction.response.send_message("No one has BST yet!", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="🏆 BST Leaderboard",
                description="Top BST holders",
                color=discord.Color.gold()
            )
            
            medals = ["🥇", "🥈", "🥉"]
            
            leaderboard_text = ""
            for i, (user_id, balance) in enumerate(balances[:10], 1):
                member = interaction.guild.get_member(user_id)
                if not member:
                    continue
                
                medal = medals[i-1] if i <= 3 else f"`#{i}`"
                leaderboard_text += f"{medal} **{member.display_name}** —
