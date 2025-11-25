import discord
from discord.ext import commands
from discord import app_commands
import config
from database import db
from utils.checks import is_owner, is_manager
from datetime import datetime, timedelta

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        """Track messages for BST rewards"""
        if message.author.bot:
            return
        
        # Check if message is in counting channel
        if message.channel.id not in config.COUNTING_CHANNELS:
            return

        try:
            # Record message and potentially award BST
            earned_bst = await db.record_message(
                message.author.id, 
                str(message.author), 
                message.channel.id
            )
            
            if earned_bst:
                # Send ephemeral success message
                embed = discord.Embed(
                    description=config.Design.small_caps(
                        f"earned {config.BST_PER_100_MESSAGES} bst for {config.MESSAGES_FOR_BST} messages"
                    ),
                    color=config.Colors.SUCCESS
                )
                await message.channel.send(
                    f"{message.author.mention}",
                    embed=embed,
                    delete_after=5
                )
                
        except Exception as e:
            print(f"Error in message counting: {e}")

    @app_commands.command(name="balance", description="Check your BST balance")
    async def balance(self, interaction: discord.Interaction, user: discord.Member = None):
        """Check BST balance"""
        target = user or interaction.user
        
        try:
            user_data = await db.get_user(target.id)
            
            embed = discord.Embed(color=config.Colors.PRIMARY)
            
            # Header
            header = config.Design.header("BALANCE", 28)
            embed.description = f"\n{header}\n"
            
            # Content
            content = (
                f"\n{config.Design.field('User', target.display_name, 12)}\n"
                f"{config.Design.field('Balance', f'{user_data['bst_balance']:.2f} BST', 12)}\n"
                f"{config.Design.field('Messages', f'{user_data['total_messages']:,}', 12)}\n"
                f"{config.Design.field('Weekly', f'{user_data['weekly_messages']:,}', 12)}\n"
            )
            
            embed.add_field(name="\u200b", value=content, inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}", 
                ephemeral=True
            )

    @app_commands.command(name="daily", description="Claim your daily BST reward")
    async def daily(self, interaction: discord.Interaction):
        """Claim daily reward"""
        try:
            user_data = await db.get_user(interaction.user.id)
            now = datetime.utcnow()
            
            # Check if already claimed today
            if user_data['last_daily_claim']:
                last_claim = user_data['last_daily_claim'].replace(tzinfo=None)
                if (now - last_claim).days < 1:
                    # Check if it's the same day
                    if now.date() == last_claim.date():
                        await interaction.response.send_message(
                            "You have already claimed your daily reward today!",
                            ephemeral=True
                        )
                        return
            
            # Calculate streak
            new_streak = 1
            if user_data['last_daily_claim']:
                last_claim = user_data['last_daily_claim'].replace(tzinfo=None)
                if (now - last_claim).days == 1:
                    new_streak = user_data['daily_streak'] + 1
            
            # Award BST
            reward = config.DAILY_REWARD
            if new_streak % 7 == 0:  # Weekly bonus
                reward *= 2
            
            success = await db.update_user_balance(interaction.user.id, reward)
            
            if success:
                # Update daily claim info
                async with db.pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE users 
                        SET last_daily_claim = $1, daily_streak = $2
                        WHERE user_id = $3
                    """, now, new_streak, interaction.user.id)
                
                # Record transaction
                await conn.execute("""
                    INSERT INTO transactions (user_id, tx_type, amount_bst, metadata)
                    VALUES ($1, 'daily_reward', $2, $3)
                """, interaction.user.id, reward, {"streak": new_streak})
                
                embed = discord.Embed(
                    description=config.Design.small_caps(
                        f"claimed {reward:.2f} bst daily reward (streak: {new_streak} days)"
                    ),
                    color=config.Colors.SUCCESS
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(
                    "Error claiming daily reward",
                    ephemeral=True
                )
                
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="messagecounter", description="Check your message statistics")
    async def message_counter(self, interaction: discord.Interaction):
        """Check message statistics"""
        try:
            user_data = await db.get_user(interaction.user.id)
            
            messages_to_next = config.MESSAGES_FOR_BST - (user_data['weekly_messages'] % config.MESSAGES_FOR_BST)
            if messages_to_next == config.MESSAGES_FOR_BST:
                messages_to_next = 0
            
            weekly_bst = await db.pool.fetchval("""
                SELECT COALESCE(SUM(amount_bst), 0) FROM transactions 
                WHERE user_id = $1 AND tx_type = 'message_reward' 
                AND created_at >= $2
            """, interaction.user.id, datetime.utcnow() - timedelta(days=7))
            
            embed = discord.Embed(color=config.Colors.PRIMARY)
            
            header = config.Design.header("MESSAGE STATS", 28)
            embed.description = f"\n{header}\n"
            
            content = (
                f"\n{config.Design.field('Total Messages', f'{user_data['total_messages']:,}', 18)}\n"
                f"{config.Design.field('Weekly Messages', f'{user_data['weekly_messages']:,}', 18)}\n"
                f"{config.Design.field('To Next BST', f'{messages_to_next}/{config.MESSAGES_FOR_BST}', 18)}\n"
                f"{config.Design.field('Weekly BST', f'{weekly_bst:.2f}/{config.WEEKLY_MESSAGE_CAP}', 18)}\n"
                f"{config.Design.field('Rate', f'{config.BST_PER_100_MESSAGES} BST per {config.MESSAGES_FOR_BST} msgs', 18)}\n"
            )
            
            embed.add_field(name="\u200b", value=content, inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="weeklystatus", description="Check your weekly progress")
    async def weekly_status(self, interaction: discord.Interaction):
        """Check weekly BST earning status"""
        try:
            weekly_bst = await db.pool.fetchval("""
                SELECT COALESCE(SUM(amount_bst), 0) FROM transactions 
                WHERE user_id = $1 AND tx_type = 'message_reward' 
                AND created_at >= $2
            """, interaction.user.id, datetime.utcnow() - timedelta(days=7))
            
            remaining = max(0, config.WEEKLY_MESSAGE_CAP - weekly_bst)
            percentage = (weekly_bst / config.WEEKLY_MESSAGE_CAP) * 100
            
            embed = discord.Embed(color=config.Colors.PRIMARY)
            
            header = config.Design.header("WEEKLY PROGRESS", 28)
            embed.description = f"\n{header}\n"
            
            content = (
                f"\n{config.Design.field('Earned This Week', f'{weekly_bst:.2f} BST', 20)}\n"
                f"{config.Design.field('Weekly Cap', f'{config.WEEKLY_MESSAGE_CAP} BST', 20)}\n"
                f"{config.Design.field('Remaining', f'{remaining:.2f} BST', 20)}\n"
                f"{config.Design.field('Progress', f'{percentage:.1f}%', 20)}\n"
            )
            
            embed.add_field(name="\u200b", value=content, inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Economy(bot))