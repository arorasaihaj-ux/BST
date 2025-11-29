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
        
        if now.weekday() == 0:
            if self.last_reset_check and self.last_reset_check.date() == now.date():
                return
            
            try:
                old_weekly = await self.bot.db.get_weekly_pool()
                transferred = await self.bot.db.transfer_weekly_to_main()
                await self.bot.db.reset_weekly_pool(10.0)
                
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
        
        if COUNTING_CHANNELS and message.channel.id not in COUNTING_CHANNELS:
            return

        try:
            new_count = await self.bot.db.increment_messages(message.author.id)
            
            if new_count % MESSAGES_PER_BST == 0:
                weekly_pool = await self.bot.db.get_weekly_pool()
                weekly_pool = self.convert_decimals(weekly_pool)
                
                if weekly_pool >= 1.0:
                    success = await self.bot.db.add_bst_from_weekly(message.author.id, 1.0)
                    
                    if success:
                        await self.bot.db.reset_messages(message.author.id)
                        
                        balance = await self.bot.db.get_balance(message.author.id)
                        balance = self.convert_decimals(balance)
                        
                        new_weekly_pool = await self.bot.db.get_weekly_pool()
                        new_weekly_pool = self.convert_decimals(new_weekly_pool)
                        
                        embed = discord.Embed(
                            title="BST EARNED",
                            description=(
                                f"{message.author.mention}\n\n"
                                f"**Awarded:** 1 BST\n"
                                f"**Your Balance:** {balance:.2f} BST\n"
                                f"**Weekly Pool:** {new_weekly_pool:.2f} BST remaining\n\n"
                                f"*Pool resets every Monday*"
                            ),
                            color=0x57F287
                        )
                        
                        await message.channel.send(embed=embed, delete_after=20)
                    else:
                        embed = discord.Embed(
                            title="BST Award Failed",
                            description=(
                                f"{message.author.mention}\n\n"
                                f"Error awarding BST. Contact admin if this persists."
                            ),
                            color=0xFEE75C
                        )
                        await message.channel.send(embed=embed, delete_after=15)
                else:
                    embed = discord.Embed(
                        title="WEEKLY POOL EMPTY",
                        description=(
                            f"{message.author.mention}\n\n"
                            f"You reached 800 messages, but the weekly pool is empty.\n\n"
                            f"**Weekly pool resets every Monday**"
                        ),
                        color=0xED4245
                    )
                    
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
            
            # Progress calculation
            progress_to_next = msg_count % MESSAGES_PER_BST
            remaining_messages = MESSAGES_PER_BST - progress_to_next
            progress_percent = (progress_to_next / MESSAGES_PER_BST) * 100
            
            # Premium progress bar
            filled = int(progress_percent / 5)
            bar = "▰" * filled + "▱" * (20 - filled)
            
            embed = discord.Embed(
                title=f"━━━━━ 𝐁𝐀𝐋𝐀𝐍𝐂𝐄 ━━━━━",
                description=f"**{target.display_name}**",
                color=0x2B2D31
            )
            
            embed.add_field(
                name="╭─────────────────╮",
                value=f"**𝐁𝐒𝐓 𝐁𝐚𝐥𝐚𝐧𝐜𝐞**\n```fix\n{balance:.2f} BST\n```\n╰─────────────────╯",
                inline=False
            )
            
            embed.add_field(
                name="╭─────────────────╮",
                value=f"**𝐏𝐫𝐨𝐠𝐫𝐞𝐬𝐬 𝐭𝐨 𝐍𝐞𝐱𝐭 𝐁𝐒𝐓**\n`{bar}` **{progress_percent:.1f}%**\n**{progress_to_next}** / **{MESSAGES_PER_BST}** (**{remaining_messages}** remaining)\n╰─────────────────╯",
                inline=False
            )
            
            # Pool status
            pool_status = "𝐀𝐯𝐚𝐢𝐥𝐚𝐛𝐥𝐞" if weekly_pool >= 5.0 else "𝐋𝐨𝐰" if weekly_pool >= 1.0 else "𝐄𝐦𝐩𝐭𝐲"
            embed.add_field(
                name="╭─────────────────╮",
                value=f"**𝐖𝐞𝐞𝐤𝐥𝐲 𝐏𝐨𝐨𝐥**\n**{weekly_pool:.2f} BST** • {pool_status}\n*Resets every Monday*\n╰─────────────────╯",
                inline=False
            )
            
            embed.set_footer(text="━━━━━━━━━━━━━━━━━━━━━━━━━\n800 messages = 1 BST")
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            print(f"Balance error: {e}")
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)

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
            
            # Premium wider progress bar
            filled = int(progress_percent / 2.5)
            bar = "▰" * filled + "▱" * (40 - filled)
            
            embed = discord.Embed(
                title="━━━━━ 𝐌𝐄𝐒𝐒𝐀𝐆𝐄 𝐏𝐑𝐎𝐆𝐑𝐄𝐒𝐒 ━━━━━",
                color=0x2B2D31
            )
            
            embed.add_field(
                name="╭──────────────────────────────────────────────╮",
                value=f"```{bar}```\n╰──────────────────────────────────────────────╯",
                inline=False
            )
            
            embed.add_field(
                name="**𝐂𝐮𝐫𝐫𝐞𝐧𝐭 𝐏𝐫𝐨𝐠𝐫𝐞𝐬𝐬**",
                value=f"**{progress_to_next}** / **{MESSAGES_PER_BST}** (**{progress_percent:.1f}%**)",
                inline=True
            )
            
            embed.add_field(
                name="**𝐑𝐞𝐦𝐚𝐢𝐧𝐢𝐧𝐠**",
                value=f"**{remaining_messages}** messages",
                inline=True
            )
            
            # Pool status
            pool_status = "𝐀𝐯𝐚𝐢𝐥𝐚𝐛𝐥𝐞" if weekly_pool >= 5.0 else "𝐋𝐨𝐰" if weekly_pool >= 1.0 else "𝐄𝐦𝐩𝐭𝐲"
            embed.add_field(
                name="╭─────────────────╮",
                value=f"**𝐖𝐞𝐞𝐤𝐥𝐲 𝐏𝐨𝐨𝐥**\n**{weekly_pool:.2f} BST** • {pool_status}\n*Resets every Monday*\n╰─────────────────╯",
                inline=False
            )
            
            embed.set_footer(text="━━━━━━━━━━━━━━━━━━━━━━━━━\nKeep chatting to earn BST")
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            print(f"Messages error: {e}")
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)

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
                await interaction.response.send_message("No one has BST yet. Start chatting to earn BST.")
                return
            
            embed = discord.Embed(
                title="━━━━━ 𝐁𝐒𝐓 𝐋𝐄𝐀𝐃𝐄𝐑𝐁𝐎𝐀𝐑𝐃 ━━━━━",
                description="**Top BST holders in the server**",
                color=0xFEE75C
            )
            
            # Premium ranking with special fonts
            leaderboard_text = ""
            rank_symbols = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"]
            
            for i, (user_id, balance) in enumerate(balances[:10], 0):
                member = interaction.guild.get_member(user_id)
                if not member:
                    continue
                
                rank = rank_symbols[i] if i < 10 else f"⓫"
                
                # Top 3 get special formatting
                if i == 0:
                    leaderboard_text += f"╔═══════════════════════╗\n"
                    leaderboard_text += f"║ {rank} **{member.display_name}** — **{balance:.2f} BST** ║\n"
                    leaderboard_text += f"╚═══════════════════════╝\n"
                elif i == 1:
                    leaderboard_text += f"╔═══════════════════════╗\n"
                    leaderboard_text += f"║ {rank} **{member.display_name}** — **{balance:.2f} BST** ║\n"
                    leaderboard_text += f"╚═══════════════════════╝\n"
                elif i == 2:
                    leaderboard_text += f"╔═══════════════════════╗\n"
                    leaderboard_text += f"║ {rank} **{member.display_name}** — **{balance:.2f} BST** ║\n"
                    leaderboard_text += f"╚═══════════════════════╝\n"
                else:
                    leaderboard_text += f"{rank} **{member.display_name}** — {balance:.2f} BST\n"
            
            embed.add_field(
                name="╭───────────────────────────╮",
                value=f"{leaderboard_text}╰───────────────────────────╯",
                inline=False
            )
            
            # Pool status
            pool_status = "𝐀𝐯𝐚𝐢𝐥𝐚𝐛𝐥𝐞" if weekly_pool >= 5.0 else "𝐋𝐨𝐰" if weekly_pool >= 1.0 else "𝐄𝐦𝐩𝐭𝐲"
            
            embed.add_field(
                name="╭─────────────────╮",
                value=(
                    f"**𝐄𝐜𝐨𝐧𝐨𝐦𝐲 𝐒𝐭𝐚𝐭𝐮𝐬**\n"
                    f"**Main Pool:** {main_pool:.2f} BST\n"
                    f"**Weekly Pool:** {weekly_pool:.2f} BST • {pool_status}\n"
                    f"**In Circulation:** {total_circulation:.2f} BST\n"
                    f"**Total Supply:** {main_pool + total_circulation:.2f} BST\n"
                    f"╰─────────────────╯"
                ),
                inline=False
            )
            
            embed.set_footer(text="━━━━━━━━━━━━━━━━━━━━━━━━━\n800 messages = 1 BST")
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            print(f"Leaderboard error: {e}")
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)

    @app_commands.command(name="poolstatus", description="Check weekly pool status")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def poolstatus(self, interaction: discord.Interaction):
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
            
            pool_status = "𝐀𝐯𝐚𝐢𝐥𝐚𝐛𝐥𝐞" if weekly_pool >= 5.0 else "𝐋𝐨𝐰" if weekly_pool >= 1.0 else "𝐄𝐦𝐩𝐭𝐲"
            color = 0x57F287 if weekly_pool >= 5.0 else 0xFEE75C if weekly_pool >= 1.0 else 0xED4245
            
            embed = discord.Embed(
                title="━━━━━ 𝐏𝐎𝐎𝐋 𝐒𝐓𝐀𝐓𝐔𝐒 ━━━━━",
                color=color
            )
            
            embed.add_field(
                name="╭─────────────────╮",
                value=f"**𝐖𝐞𝐞𝐤𝐥𝐲 𝐏𝐨𝐨𝐥**\n```fix\n{weekly_pool:.2f} BST\n```\n╰─────────────────╯",
                inline=True
            )
            
            embed.add_field(
                name="╭─────────────────╮",
                value=f"**𝐌𝐚𝐢𝐧 𝐏𝐨𝐨𝐥**\n```fix\n{main_pool:.2f} BST\n```\n╰─────────────────╯",
                inline=True
            )
            
            embed.add_field(
                name="╭─────────────────╮",
                value=f"**𝐒𝐭𝐚𝐭𝐮𝐬**\n```{pool_status}```\n╰─────────────────╯",
                inline=True
            )
            
            embed.add_field(
                name="╭─────────────────╮",
                value=f"**𝐍𝐞𝐱𝐭 𝐑𝐞𝐬𝐞𝐭**\n<t:{int(next_reset.timestamp())}:R>\n╰─────────────────╯",
                inline=False
            )
            
            if weekly_pool >= 1.0:
                embed.add_field(
                    name="╭─────────────────╮",
                    value=f"**𝐈𝐧𝐟𝐨**\nWeekly pool has **{int(weekly_pool)} BST** ready to be earned\n╰─────────────────╯",
                    inline=False
                )
            else:
                embed.add_field(
                    name="╭─────────────────╮",
                    value=f"**𝐈𝐧𝐟𝐨**\nWeekly pool is empty. Wait for Monday reset.\n╰─────────────────╯",
                    inline=False
                )
            
            embed.set_footer(text="━━━━━━━━━━━━━━━━━━━━━━━━━\n800 messages = 1 BST from weekly pool")
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            print(f"Pool status error: {e}")
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Economy(bot))
