import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
from datetime import datetime, timedelta
import decimal

COUNTING_CHANNELS = [int(x.strip()) for x in os.getenv('COUNTING_CHANNELS', '').split(',') if x.strip()]
MESSAGES_PER_BST = 800

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.weekly_reset.start()
        self.last_reset_check = None

    def cog_unload(self):
        self.weekly_reset.cancel()

    def convert_decimals(self, data):
        """Convert decimals to float"""
        if isinstance(data, dict):
            return {k: float(v) if isinstance(v, decimal.Decimal) else v for k, v in data.items()}
        elif isinstance(data, list):
            return [float(item) if isinstance(item, decimal.Decimal) else item for item in data]
        elif isinstance(data, decimal.Decimal):
            return float(data)
        return data

    @tasks.loop(hours=24)
    async def weekly_reset(self):
        """Reset weekly pool every Monday"""
        now = datetime.now()
        
        # Only reset on Monday (0 = Monday)
        if now.weekday() == 0:
            # Check if we already reset today
            if self.last_reset_check and self.last_reset_check.date() == now.date():
                return
            
            try:
                # Get current weekly pool
                old_weekly = await self.bot.db.get_weekly_pool()
                
                # Transfer remaining to main pool
                transferred = await self.bot.db.transfer_weekly_to_main()
                
                # Reset to 10 BST (or whatever default you want)
                await self.bot.db.reset_weekly_pool(10.0)
                
                # Log the reset
                week_start = now - timedelta(days=now.weekday())
                await self.bot.db.log_weekly_reset(
                    week_start=week_start,
                    initial=10.0,
                    final=old_weekly,
                    distributed=10.0 - old_weekly
                )
                
                self.last_reset_check = now
                
                print(f"✅ Weekly pool reset!")
                print(f"   Transferred: {transferred:.2f} BST to main pool")
                print(f"   New weekly pool: 10.0 BST")
                
            except Exception as e:
                print(f"❌ Weekly reset error: {e}")

    @weekly_reset.before_loop
    async def before_weekly_reset(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        
        # Check if we should count messages in this channel
        if COUNTING_CHANNELS and message.channel.id not in COUNTING_CHANNELS:
            return

        try:
            new_count = await self.bot.db.increment_messages(message.author.id)
            
            # Check if reached 800 messages
            if new_count % MESSAGES_PER_BST == 0:
                # Check WEEKLY POOL
                weekly_pool = await self.bot.db.get_weekly_pool()
                weekly_pool = self.convert_decimals(weekly_pool)
                
                if weekly_pool >= 1.0:
                    # Award 1 BST from weekly pool
                    success = await self.bot.db.add_bst_from_weekly(message.author.id, 1.0)
                    
                    if success:
                        await self.bot.db.reset_messages(message.author.id)
                        
                        balance = await self.bot.db.get_balance(message.author.id)
                        balance = self.convert_decimals(balance)
                        
                        new_weekly_pool = await self.bot.db.get_weekly_pool()
                        new_weekly_pool = self.convert_decimals(new_weekly_pool)
                        
                        embed = discord.Embed(
                            title="💰 BST EARNED!",
                            description=(
                                f"{message.author.mention}\n\n"
                                f"**You reached 800 messages!**\n"
                                f"**Awarded: 1 BST**\n\n"
                                f"💵 Your Balance: **{balance:.2f} BST**\n"
                                f"📅 Weekly Pool: **{new_weekly_pool:.2f} BST remaining**\n\n"
                                f"*Pool resets every Monday*"
                            ),
                            color=0x57F287
                        )
                        embed.set_footer(text="Keep chatting to earn more BST!")
                        
                        await message.channel.send(embed=embed, delete_after=20)
                    else:
                        # Failed to award (race condition or error)
                        embed = discord.Embed(
                            title="⚠️ BST Award Failed",
                            description=(
                                f"{message.author.mention}\n\n"
                                f"You reached 800 messages, but there was an error awarding BST.\n"
                                f"Please contact an admin if this persists."
                            ),
                            color=0xFEE75C
                        )
                        await message.channel.send(embed=embed, delete_after=15)
                else:
                    # Weekly pool depleted
                    embed = discord.Embed(
                        title="❌ WEEKLY POOL EMPTY",
                        description=(
                            f"{message.author.mention}\n\n"
                            f"**You reached 800 messages!**\n\n"
                            f"However, the **weekly pool is empty** ({weekly_pool:.2f} BST remaining)\n\n"
                            f"**Weekly pool resets every Monday**\n"
                            f"Come back then to earn more BST!"
                        ),
                        color=0xED4245
                    )
                    embed.set_footer(text="Contact admins if you think this is an error")
                    
                    await message.channel.send(embed=embed, delete_after=15)
                    
        except Exception as e:
            print(f"Message tracking error: {e}")

    @app_commands.command(name="balance", description="Check your BST balance and progress")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def balance(self, interaction: discord.Interaction, user: discord.Member = None):
        target = user or interaction.user
        
        try:
            balance = await self.bot.db.get_balance(target.id)
            balance = self.convert_decimals(balance) or 0.0
            
            msg_count = await self.bot.db.get_message_count(target.id)
            msg_count = self.convert_decimals(msg_count) or 0
            
            weekly_pool = await self.bot.db.get_weekly_pool()
            weekly_pool = self.convert_decimals(weekly_pool)
            
            # Progress
            progress_to_next = msg_count % MESSAGES_PER_BST
            remaining_messages = MESSAGES_PER_BST - progress_to_next
            progress_percent = (progress_to_next / MESSAGES_PER_BST) * 100
            
            filled = int(progress_percent / 5)
            bar = "█" * filled + "░" * (20 - filled)
            
            embed = discord.Embed(
                title=f"💰 {target.display_name}'s Balance",
                color=0x2B2D31
            )
            
            embed.add_field(
                name="💵 BST Balance",
                value=f"**{balance:.2f} BST**",
                inline=False
            )
            
            embed.add_field(
                name="📊 Progress to Next BST",
                value=f"`{bar}` {progress_percent:.1f}%\n**{progress_to_next}/{MESSAGES_PER_BST}** messages (**{remaining_messages}** remaining)",
                inline=False
            )
            
            # Weekly pool status with color coding
            pool_emoji = "🟢" if weekly_pool >= 5.0 else "🟡" if weekly_pool >= 1.0 else "🔴"
            embed.add_field(
                name=f"{pool_emoji} Weekly Pool Status",
                value=f"**{weekly_pool:.2f} BST** remaining in server pool\n*Resets every Monday*",
                inline=False
            )
            
            if weekly_pool < 1.0:
                embed.add_field(
                    name="⚠️ Pool Empty",
                    value="Weekly pool is depleted! Wait for Monday reset.",
                    inline=False
                )
            
            embed.set_footer(text="800 messages = 1 BST • Earn from weekly pool")
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            print(f"Balance error: {e}")
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

    @app_commands.command(name="messages", description="Check your message progress")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def messages(self, interaction: discord.Interaction):
        try:
            msg_count = await self.bot.db.get_message_count(interaction.user.id)
            msg_count = self.convert_decimals(msg_count) or 0
            
            weekly_pool = await self.bot.db.get_weekly_pool()
            weekly_pool = self.convert_decimals(weekly_pool)
            
            progress_to_next = msg_count % MESSAGES_PER_BST
            remaining_messages = MESSAGES_PER_BST - progress_to_next
            progress_percent = (progress_to_next / MESSAGES_PER_BST) * 100
            
            filled = int(progress_percent / 2.5)
            bar = "▓" * filled + "░" * (40 - filled)
            
            embed = discord.Embed(
                title="📨 Message Progress",
                color=0x2B2D31
            )
            
            embed.add_field(
                name="Progress Bar",
                value=f"```{bar}```",
                inline=False
            )
            
            embed.add_field(
                name="📊 Stats",
                value=f"**{progress_to_next}/{MESSAGES_PER_BST}** messages ({progress_percent:.1f}%)",
                inline=True
            )
            
            embed.add_field(
                name="⏳ Remaining",
                value=f"**{remaining_messages}** messages until next BST",
                inline=True
            )
            
            # Calculate estimated time (assuming 10 messages per hour)
            estimated_hours = remaining_messages / 10
            if estimated_hours < 1:
                time_estimate = f"{int(estimated_hours * 60)} minutes"
            elif estimated_hours < 24:
                time_estimate = f"{estimated_hours:.1f} hours"
            else:
                time_estimate = f"{estimated_hours / 24:.1f} days"
            
            embed.add_field(
                name="⏰ Estimated Time",
                value=f"~{time_estimate} (at 10 msg/hr)",
                inline=False
            )
            
            # Weekly pool status
            pool_emoji = "🟢" if weekly_pool >= 5.0 else "🟡" if weekly_pool >= 1.0 else "🔴"
            embed.add_field(
                name=f"{pool_emoji} Weekly Pool Status",
                value=f"**{weekly_pool:.2f} BST** remaining in server pool\n*Resets every Monday*",
                inline=False
            )
            
            if weekly_pool < 1.0:
                embed.add_field(
                    name="⚠️ Pool Nearly Empty",
                    value="Weekly pool is running low! Resets Monday.",
                    inline=False
                )
            
            embed.set_footer(text="Keep chatting to earn BST from the weekly pool!")
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            print(f"Messages error: {e}")
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

    @app_commands.command(name="leaderboard", description="View BST leaderboard")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def leaderboard(self, interaction: discord.Interaction):
        try:
            balances_data = await self.bot.db.get_all_balances()
            balances = []
            for user_id, balance in balances_data:
                balances.append((user_id, self.convert_decimals(balance)))
            
            main_pool = await self.bot.db.get_pool_balance()
            main_pool = self.convert_decimals(main_pool) or 0.0
            
            weekly_pool = await self.bot.db.get_weekly_pool()
            weekly_pool = self.convert_decimals(weekly_pool) or 0.0
            
            total_circulation = await self.bot.db.get_total_bst_in_circulation()
            total_circulation = self.convert_decimals(total_circulation) or 0.0
            
            if not balances:
                await interaction.response.send_message("No one has BST yet! Start chatting to earn BST.")
                return
            
            embed = discord.Embed(
                title="🏆 BST Leaderboard",
                description="Top BST holders in the server",
                color=0xFEE75C
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
                value=leaderboard_text if leaderboard_text else "*No users yet*",
                inline=False
            )
            
            # Economy status with color coding
            pool_emoji = "🟢" if weekly_pool >= 5.0 else "🟡" if weekly_pool >= 1.0 else "🔴"
            
            embed.add_field(
                name="📊 Economy Status",
                value=(
                    f"**💰 Main Pool:** {main_pool:.2f} BST\n"
                    f"**{pool_emoji} Weekly Pool:** {weekly_pool:.2f} BST\n"
                    f"**💵 In Circulation:** {total_circulation:.2f} BST\n"
                    f"**🌍 Total Supply:** {main_pool + total_circulation:.2f} BST"
                ),
                inline=False
            )
            
            embed.set_footer(text="Earn BST by chatting • 800 msgs = 1 BST from weekly pool")
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            print(f"Leaderboard error: {e}")
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

    @app_commands.command(name="poolstatus", description="Check weekly pool status (Public)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def poolstatus(self, interaction: discord.Interaction):
        """Public command to check weekly pool status"""
        try:
            weekly_pool = await self.bot.db.get_weekly_pool()
            weekly_pool = self.convert_decimals(weekly_pool)
            
            main_pool = await self.bot.db.get_pool_balance()
            main_pool = self.convert_decimals(main_pool)
            
            # Calculate next Monday
            now = datetime.now()
            days_until_monday = (7 - now.weekday()) % 7
            if days_until_monday == 0:
                days_until_monday = 7
            next_reset = now + timedelta(days=days_until_monday)
            
            pool_emoji = "🟢" if weekly_pool >= 5.0 else "🟡" if weekly_pool >= 1.0 else "🔴"
            
            embed = discord.Embed(
                title=f"{pool_emoji} Weekly Pool Status",
                color=0x57F287 if weekly_pool >= 5.0 else 0xFEE75C if weekly_pool >= 1.0 else 0xED4245
            )
            
            embed.add_field(
                name="📅 Weekly Pool",
                value=f"**{weekly_pool:.2f} BST** available",
                inline=True
            )
            
            embed.add_field(
                name="💰 Main Pool",
                value=f"**{main_pool:.2f} BST**",
                inline=True
            )
            
            embed.add_field(
                name="⏰ Next Reset",
                value=f"<t:{int(next_reset.timestamp())}:R>",
                inline=False
            )
            
            if weekly_pool >= 1.0:
                embed.add_field(
                    name="✅ Status",
                    value=f"Weekly pool has **{int(weekly_pool)} BST** ready to be earned!",
                    inline=False
                )
            else:
                embed.add_field(
                    name="⚠️ Status",
                    value="Weekly pool is nearly empty! Wait for Monday reset.",
                    inline=False
                )
            
            embed.set_footer(text="Send 800 messages to earn 1 BST from weekly pool")
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            print(f"Pool status error: {e}")
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Economy(bot))
