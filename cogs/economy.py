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
        if isinstance(data, dict):
            return {k: float(v) if isinstance(v, decimal.Decimal) else v for k, v in data.items()}
        elif isinstance(data, list):
            return [float(item) if isinstance(item, decimal.Decimal) else item for item in data]
        elif isinstance(data, decimal.Decimal):
            return float(data)
        return data

    @tasks.loop(hours=24)
    async def weekly_reset(self):
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
                print(f"Weekly pool reset: {transferred:.2f} BST transferred")
                
            except Exception as e:
                print(f"Weekly reset error: {e}")

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
                            title="𝐁𝐒𝐓 𝐄𝐀𝐑𝐍𝐄𝐃",
                            description=f"{message.author.mention}\n**𝐀𝐰𝐚𝐫𝐝𝐞𝐝:** 1 𝐁𝐒𝐓\n**𝐁𝐚𝐥𝐚𝐧𝐜𝐞:** {balance:.2f} 𝐁𝐒𝐓\n**𝐖𝐞𝐞𝐤𝐥𝐲 𝐏𝐨𝐨𝐥:** {new_weekly_pool:.2f} 𝐁𝐒𝐓",
                            color=0x2B2D31
                        )
                        
                        await message.channel.send(embed=embed, delete_after=20)
                else:
                    embed = discord.Embed(
                        title="𝐏𝐎𝐎𝐋 𝐄𝐌𝐏𝐓𝐘",
                        description=f"{message.author.mention}\n**800 𝐦𝐞𝐬𝐬𝐚𝐠𝐞𝐬 𝐫𝐞𝐚𝐜𝐡𝐞𝐝**\n𝐖𝐞𝐞𝐤𝐥𝐲 𝐩𝐨𝐨𝐥 𝐢𝐬 𝐞𝐦𝐩𝐭𝐲\n𝐑𝐞𝐬𝐞𝐭𝐬 𝐌𝐨𝐧𝐝𝐚𝐲",
                        color=0x2B2D31
                    )
                    
                    await message.channel.send(embed=embed, delete_after=15)
                    
        except Exception as e:
            print(f"Message tracking error: {e}")

    @app_commands.command(name="balance", description="Check BST balance")
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
            
            progress_to_next = msg_count % MESSAGES_PER_BST
            remaining_messages = MESSAGES_PER_BST - progress_to_next
            progress_percent = (progress_to_next / MESSAGES_PER_BST) * 100
            
            filled = int(progress_percent / 5)
            bar = "▰" * filled + "▱" * (20 - filled)
            
            embed = discord.Embed(
                title="𝐁𝐀𝐋𝐀𝐍𝐂𝐄",
                description=f"**{target.display_name}**\n**𝐁𝐒𝐓:** {balance:.2f}\n**𝐏𝐫𝐨𝐠𝐫𝐞𝐬𝐬:** {bar} {progress_percent:.0f}%\n**𝐌𝐞𝐬𝐬𝐚𝐠𝐞𝐬:** {progress_to_next}/{MESSAGES_PER_BST}\n**𝐑𝐞𝐦𝐚𝐢𝐧𝐢𝐧𝐠:** {remaining_messages}\n**𝐖𝐞𝐞𝐤𝐥𝐲 𝐏𝐨𝐨𝐥:** {weekly_pool:.2f} 𝐁𝐒𝐓",
                color=0x2B2D31
            )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            print(f"Balance error: {e}")
            await interaction.response.send_message(f"**𝐄𝐑𝐑𝐎𝐑**\n{e}", ephemeral=True)

    @app_commands.command(name="messages", description="Check message progress")
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
            bar = "▰" * filled + "▱" * (40 - filled)
            
            embed = discord.Embed(
                title="𝐌𝐄𝐒𝐒𝐀𝐆𝐄 𝐏𝐑𝐎𝐆𝐑𝐄𝐒𝐒",
                description=f"{bar}\n**𝐏𝐫𝐨𝐠𝐫𝐞𝐬𝐬:** {progress_percent:.0f}%\n**𝐌𝐞𝐬𝐬𝐚𝐠𝐞𝐬:** {progress_to_next}/{MESSAGES_PER_BST}\n**𝐑𝐞𝐦𝐚𝐢𝐧𝐢𝐧𝐠:** {remaining_messages}\n**𝐖𝐞𝐞𝐤𝐥𝐲 𝐏𝐨𝐨𝐥:** {weekly_pool:.2f} 𝐁𝐒𝐓",
                color=0x2B2D31
            )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            print(f"Messages error: {e}")
            await interaction.response.send_message(f"**𝐄𝐑𝐑𝐎𝐑**\n{e}", ephemeral=True)

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
                await interaction.response.send_message("**𝐍𝐎 𝐔𝐒𝐄𝐑𝐒**", ephemeral=True)
                return
            
            leaderboard_text = ""
            
            for i, (user_id, balance) in enumerate(balances[:10], 1):
                member = interaction.guild.get_member(user_id)
                if not member:
                    continue
                
                # NON-PING MENTION (clickable but no notification)
                leaderboard_text += f"**{i}.** <@{user_id}> {balance:.2f} 𝐁𝐒𝐓\n"
            
            embed = discord.Embed(
                title="𝐋𝐄𝐀𝐃𝐄𝐑𝐁𝐎𝐀𝐑𝐃",
                description=f"{leaderboard_text}\n**𝐌𝐚𝐢𝐧 𝐏𝐨𝐨𝐥:** {main_pool:.2f} 𝐁𝐒𝐓\n**𝐖𝐞𝐞𝐤𝐥𝐲 𝐏𝐨𝐨𝐥:** {weekly_pool:.2f} 𝐁𝐒𝐓\n**𝐂𝐢𝐫𝐜𝐮𝐥𝐚𝐭𝐢𝐨𝐧:** {total_circulation:.2f} 𝐁𝐒𝐓",
                color=0x2B2D31
            )
            
            # Suppress mentions in the message
            await interaction.response.send_message(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            
        except Exception as e:
            print(f"Leaderboard error: {e}")
            await interaction.response.send_message(f"**𝐄𝐑𝐑𝐎𝐑**\n{e}", ephemeral=True)

    @app_commands.command(name="poolstatus", description="Check weekly pool")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def poolstatus(self, interaction: discord.Interaction):
        try:
            weekly_pool = await self.bot.db.get_weekly_pool()
            weekly_pool = self.convert_decimals(weekly_pool)
            
            main_pool = await self.bot.db.get_pool_balance()
            main_pool = self.convert_decimals(main_pool)
            
            now = datetime.now()
            days_until_monday = (7 - now.weekday()) % 7
            if days_until_monday == 0:
                days_until_monday = 7
            next_reset = now + timedelta(days=days_until_monday)
            
            embed = discord.Embed(
                title="𝐏𝐎𝐎𝐋 𝐒𝐓𝐀𝐓𝐔𝐒",
                description=f"**𝐖𝐞𝐞𝐤𝐥𝐲 𝐏𝐨𝐨𝐥:** {weekly_pool:.2f} 𝐁𝐒𝐓\n**𝐌𝐚𝐢𝐧 𝐏𝐨𝐨𝐥:** {main_pool:.2f} 𝐁𝐒𝐓\n**𝐍𝐞𝐱𝐭 𝐑𝐞𝐬𝐞𝐭:** <t:{int(next_reset.timestamp())}:R>",
                color=0x2B2D31
            )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            print(f"Pool status error: {e}")
            await interaction.response.send_message(f"**𝐄𝐑𝐑𝐎𝐑**\n{e}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Economy(bot))
