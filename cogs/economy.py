import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
from datetime import datetime, timedelta

COUNTING_CHANNELS = [int(x.strip()) for x in os.getenv('COUNTING_CHANNELS', '').split(',') if x.strip()]
MESSAGES_PER_BST = 800
WEEKLY_CAP = 10.0

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.weekly_reset.start()

    def cog_unload(self):
        self.weekly_reset.cancel()

    @tasks.loop(hours=24)
    async def weekly_reset(self):
        """Reset weekly cap every Monday"""
        if datetime.now().weekday() == 0:  # Monday
            await self.bot.db.reset_weekly_cap()
            print("✅ Weekly cap reset!")

    @weekly_reset.before_loop
    async def before_weekly_reset(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        
        if COUNTING_CHANNELS and message.channel.id not in COUNTING_CHANNELS:
            return

        try:
            new_count = await self.bot.db.increment_messages(message.author.id)
            
            # Check if user reached 800 messages
            if new_count % MESSAGES_PER_BST == 0:
                # Check weekly cap
                weekly_remaining = await self.bot.db.get_weekly_remaining()
                pool_balance = await self.bot.db.get_pool_balance()
                
                if weekly_remaining >= 1.0 and pool_balance >= 1.0:
                    # Give BST to user
                    await self.bot.db.add_bst(message.author.id, 1.0)
                    
                    # Remove from pool and update weekly cap
                    await self.bot.db.remove_from_pool(1.0)
                    await self.bot.db.increment_weekly_distributed(1.0)
                    await self.bot.db.reset_messages(message.author.id)
                    
                    balance = await self.bot.db.get_balance(message.author.id)
                    weekly_remaining = await self.bot.db.get_weekly_remaining()
                    
                    embed = discord.Embed(
                        title="🎉 BST Earned!",
                        description=f"{message.author.mention} earned **1 BST** from messages!",
                        color=discord.Color.gold()
                    )
                    embed.add_field(name="💰 Your Balance", value=f"**{balance:.2f} BST**", inline=True)
                    embed.add_field(name="📅 Weekly Remaining", value=f"**{weekly_remaining:.1f} BST**", inline=True)
                    embed.add_field(name="💬 Messages", value=f"**{new_count}** total messages", inline=False)
                    
                    await message.channel.send(embed=embed, delete_after=15)
                else:
                    # Not enough in pool or weekly cap reached
                    if weekly_remaining < 1.0:
                        reason = "Weekly cap reached! Wait for reset."
                    else:
                        reason = "Economy pool empty! Ask owner to mint more BST."
                    
                    embed = discord.Embed(
                        title="❌ BST Not Available",
                        description=f"{message.author.mention} reached 800 messages but: {reason}",
                        color=discord.Color.red()
                    )
                    await message.channel.send(embed=embed, delete_after=10)
                    
        except Exception as e:
            print(f"Message tracking error: {e}")

    @app_commands.command(name="balance", description="Check your BST balance and progress")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def balance(self, interaction: discord.Interaction, user: discord.Member = None):
        """PUBLIC balance check"""
        target = user or interaction.user
        
        try:
            balance = await self.bot.db.get_balance(target.id)
            msg_count = await self.bot.db.get_message_count(target.id)
            weekly_remaining = await self.bot.db.get_weekly_remaining()
            
            # Progress calculations
            progress_to_next = msg_count % MESSAGES_PER_BST
            remaining_messages = MESSAGES_PER_BST - progress_to_next
            progress_percent = (progress_to_next / MESSAGES_PER_BST) * 100
            
            # Create progress bar
            filled = int(progress_percent / 5)
            bar = "█" * filled + "░" * (20 - filled)
            
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
                value=f"`{bar}` {progress_percent:.1f}%\n**{progress_to_next}/{MESSAGES_PER_BST}** messages ({remaining_messages} left)",
                inline=False
            )
            
            embed.add_field(
                name="📅 Weekly Status",
                value=f"**{weekly_remaining:.1f}/{WEEKLY_CAP} BST** remaining this week",
                inline=False
            )
            
            embed.set_footer(text="Send 800 messages to earn 1 BST • Weekly cap: 10 BST")
            
            # PUBLIC - SEND TO CHANNEL
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}")

    @app_commands.command(name="messages", description="Check your message progress")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def messages(self, interaction: discord.Interaction):
        """PUBLIC message progress"""
        try:
            msg_count = await self.bot.db.get_message_count(interaction.user.id)
            weekly_remaining = await self.bot.db.get_weekly_remaining()
            
            progress_to_next = msg_count % MESSAGES_PER_BST
            remaining_messages = MESSAGES_PER_BST - progress_to_next
            progress_percent = (progress_to_next / MESSAGES_PER_BST) * 100
            
            # Fancy progress bar
            filled = int(progress_percent / 2.5)
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
                value=f"**{progress_to_next}/{MESSAGES_PER_BST}** messages ({progress_percent:.1f}%)",
                inline=True
            )
            
            embed.add_field(
                name="⏳ Remaining",
                value=f"**{remaining_messages}** messages until next BST",
                inline=True
            )
            
            embed.add_field(
                name="📅 Weekly Cap",
                value=f"**{weekly_remaining:.1f} BST** available this week",
                inline=False
            )
            
            embed.set_footer(text="Keep chatting to earn BST! 800 messages = 1 BST")
            
            # PUBLIC - SEND TO CHANNEL
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}")

    @app_commands.command(name="leaderboard", description="View BST leaderboard")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def leaderboard(self, interaction: discord.Interaction):
        """PUBLIC leaderboard"""
        try:
            balances = await self.bot.db.get_all_balances()
            weekly_remaining = await self.bot.db.get_weekly_remaining()
            pool_balance = await self.bot.db.get_pool_balance()
            total_circulation = await self.bot.db.get_total_bst_in_circulation()
            
            if not balances:
                await interaction.response.send_message("No one has BST yet! Start chatting to earn BST.")
                return
            
            embed = discord.Embed(
                title="🏆 BST Leaderboard",
                description="Top BST holders in the server",
                color=discord.Color.gold()
            )
            
            medals = ["🥇", "🥈", "🥉"]
            
            leaderboard_text = ""
            for i, (user_id, balance) in enumerate(balances[:10], 1):
                member = interaction.guild.get_member(user_id)
                if not member:
                    continue
                
                medal = medals[i-1] if i <= 3 else f"`#{i}`"
                leaderboard_text += f"{medal} **{member.display_name}** — {balance:.2f} BST\n"
            
            embed.add_field(
                name="Top Earners",
                value=leaderboard_text,
                inline=False
            )
            
            embed.add_field(
                name="💰 Economy Status",
                value=f"**Pool:** {pool_balance:.2f} BST\n**In Circulation:** {total_circulation:.2f} BST\n**Weekly Left:** {weekly_remaining:.1f} BST",
                inline=True
            )
            
            embed.set_footer(text="Earn BST by sending messages in counting channels!")
            
            # PUBLIC - SEND TO CHANNEL
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}")

async def setup(bot):
    await bot.add_cog(Economy(bot))
