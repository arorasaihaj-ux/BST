import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
from datetime import datetime, timedelta

COUNTING_CHANNELS = [int(x.strip()) for x in os.getenv('COUNTING_CHANNELS', '').split(',') if x.strip()]
MESSAGES_PER_BST = 800
WEEKLY_CAP_PER_USER = 10.0

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.weekly_reset.start()

    def cog_unload(self):
        self.weekly_reset.cancel()

    @tasks.loop(hours=24)
    async def weekly_reset(self):
        """Reset ALL users' weekly cap every Monday"""
        if datetime.now().weekday() == 0:  # Monday
            await self.bot.db.reset_all_weekly_earnings()
            print("✅ Weekly cap reset for ALL users!")

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
                # Check user's personal weekly cap
                weekly_remaining = await self.bot.db.get_user_weekly_remaining(message.author.id)
                
                if weekly_remaining >= 1.0:
                    # User has room in their weekly cap
                    # Add BST directly to user (doesn't touch main pool)
                    await self.bot.db.add_bst_direct(message.author.id, 1.0)
                    
                    # Increment user's weekly earnings
                    await self.bot.db.increment_user_weekly_earnings(message.author.id, 1.0)
                    
                    # Reset message count
                    await self.bot.db.reset_messages(message.author.id)
                    
                    balance = await self.bot.db.get_balance(message.author.id)
                    new_weekly_remaining = await self.bot.db.get_user_weekly_remaining(message.author.id)
                    
                    embed = discord.Embed(
                        title="🎉 BST Earned!",
                        description=f"{message.author.mention} earned **1 BST** from messages!",
                        color=discord.Color.gold()
                    )
                    embed.add_field(name="💰 Your Balance", value=f"**{balance:.2f} BST**", inline=True)
                    embed.add_field(name="📅 Weekly Remaining", value=f"**{new_weekly_remaining:.1f}/{WEEKLY_CAP_PER_USER} BST**", inline=True)
                    embed.add_field(name="💬 Total Messages", value=f"**{new_count}** messages sent", inline=False)
                    embed.set_footer(text="Your BST is saved! Spend it on boxes or trade it.")
                    
                    await message.channel.send(embed=embed, delete_after=15)
                else:
                    # User hit their personal weekly cap
                    embed = discord.Embed(
                        title="📅 Weekly Cap Reached",
                        description=f"{message.author.mention} reached 800 messages but you've earned your **{WEEKLY_CAP_PER_USER} BST limit** this week!",
                        color=discord.Color.orange()
                    )
                    embed.add_field(
                        name="⏰ Reset",
                        value="Your weekly cap resets every **Monday**",
                        inline=False
                    )
                    embed.set_footer(text="Come back next week to earn more BST!")
                    
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
            weekly_remaining = await self.bot.db.get_user_weekly_remaining(target.id)
            
            # Get weekly earnings
            weekly_data = await self.bot.db.get_user_weekly_earnings(target.id)
            weekly_earned = weekly_data['bst_earned'] if weekly_data else 0.0
            
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
                name="📅 This Week",
                value=f"**Earned:** {weekly_earned:.1f} BST\n**Remaining:** {weekly_remaining:.1f}/{WEEKLY_CAP_PER_USER} BST",
                inline=False
            )
            
            embed.set_footer(text="Send 800 messages = 1 BST • 10 BST max per week • Resets Monday")
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}")

    @app_commands.command(name="messages", description="Check your message progress")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def messages(self, interaction: discord.Interaction):
        """PUBLIC message progress"""
        try:
            msg_count = await self.bot.db.get_message_count(interaction.user.id)
            weekly_remaining = await self.bot.db.get_user_weekly_remaining(interaction.user.id)
            
            # Get weekly earnings
            weekly_data = await self.bot.db.get_user_weekly_earnings(interaction.user.id)
            weekly_earned = weekly_data['bst_earned'] if weekly_data else 0.0
            
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
                name="📅 Weekly Status",
                value=f"**Earned:** {weekly_earned:.1f} BST\n**Can Earn:** {weekly_remaining:.1f} more BST this week",
                inline=False
            )
            
            if weekly_remaining == 0:
                embed.add_field(
                    name="⚠️ Weekly Cap Reached",
                    value="You've hit your 10 BST limit! Resets Monday.",
                    inline=False
                )
            
            embed.set_footer(text="Keep chatting to earn BST! 800 messages = 1 BST • Max 10 BST/week")
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}")

    @app_commands.command(name="leaderboard", description="View BST leaderboard")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def leaderboard(self, interaction: discord.Interaction):
        """PUBLIC leaderboard"""
        try:
            balances = await self.bot.db.get_all_balances()
            pool_balance = await self.bot.db.get_pool_balance()
            total_circulation = await self.bot.db.get_total_bst_in_circulation()
            
            # Get total weekly distributed across all users
            week_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = week_start - timedelta(days=week_start.weekday())
            
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
                value=f"**Main Pool:** {pool_balance:.2f} BST\n**In Circulation:** {total_circulation:.2f} BST",
                inline=True
            )
            
            embed.set_footer(text="Earn BST by sending messages! 800 msgs = 1 BST • Max 10/week")
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}")

async def setup(bot):
    await bot.add_cog(Economy(bot))
