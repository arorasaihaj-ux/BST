import discord
from discord.ext import commands
from discord import app_commands
import config
from database import db

class Achievements(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="achievements", description="View achievements")
    async def view_achievements(self, interaction: discord.Interaction):
        """View all achievements"""
        try:
            async with db.pool.acquire() as conn:
                achievements = await conn.fetch("""
                    SELECT a.*, 
                           ua.completed,
                           ua.completed_at,
                           ua.progress
                    FROM achievements a
                    LEFT JOIN user_achievements ua ON a.achievement_id = ua.achievement_id 
                        AND ua.user_id = $1
                    ORDER BY a.achievement_id
                """, interaction.user.id)
            
            if not achievements:
                await interaction.response.send_message(
                    "No achievements available.",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(color=config.Colors.PRIMARY)
            
            header = config.Design.header("ACHIEVEMENTS", 28)
            embed.description = f"\n{header}\n"
            
            completed_count = sum(1 for a in achievements if a['completed'])
            total_count = len(achievements)
            completion_rate = (completed_count / total_count) * 100
            
            embed.add_field(
                name="Progress",
                value=f"**{completed_count}/{total_count}** achievements completed ({completion_rate:.1f}%)",
                inline=False
            )
            
            for achievement in achievements:
                status = "✅" if achievement['completed'] else "⏳"
                progress = ""
                
                if not achievement['completed'] and achievement['progress'] > 0:
                    # Parse requirement to get target
                    if "messages:" in achievement['requirement']:
                        target = int(achievement['requirement'].split(":")[1])
                        progress = f" ({achievement['progress']}/{target})"
                    elif "balance:" in achievement['requirement']:
                        target = int(achievement['requirement'].split(":")[1])
                        progress = f" ({achievement['progress']}/{target})"
                    elif "boxes_opened:" in achievement['requirement']:
                        target = int(achievement['requirement'].split(":")[1])
                        progress = f" ({achievement['progress']}/{target})"
                    elif "trades:" in achievement['requirement']:
                        target = int(achievement['requirement'].split(":")[1])
                        progress = f" ({achievement['progress']}/{target})"
                
                reward_text = f"Reward: {achievement['reward_bst']} BST" if achievement['reward_bst'] > 0 else ""
                
                embed.add_field(
                    name=f"{status} {achievement['name']}{progress}",
                    value=f"{achievement['description']}\n{reward_text}",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="claimachievement", description="Claim achievement rewards")
    async def claim_achievement(self, interaction: discord.Interaction, achievement_id: str):
        """Claim achievement reward"""
        try:
            async with db.pool.acquire() as conn:
                # Check if user has completed the achievement
                user_achievement = await conn.fetchrow("""
                    SELECT ua.*, a.reward_bst, a.reward_item_id
                    FROM user_achievements ua
                    JOIN achievements a ON ua.achievement_id = a.achievement_id
                    WHERE ua.user_id = $1 AND ua.achievement_id = $2 AND ua.completed = true
                """, interaction.user.id, achievement_id)
                
                if not user_achievement:
                    await interaction.response.send_message(
                        "Achievement not found or not completed.",
                        ephemeral=True
                    )
                    return
                
                if user_achievement['reward_claimed']:
                    await interaction.response.send_message(
                        "Reward already claimed.",
                        ephemeral=True
                    )
                    return
                
                # Award rewards
                if user_achievement['reward_bst'] > 0:
                    await conn.execute("""
                        UPDATE users SET bst_balance = bst_balance + $1
                        WHERE user_id = $2
                    """, user_achievement['reward_bst'], interaction.user.id)
                    
                    await conn.execute("""
                        INSERT INTO transactions (user_id, tx_type, amount_bst, metadata)
                        VALUES ($1, 'achievement_reward', $2, $3)
                    """, interaction.user.id, user_achievement['reward_bst'], {
                        "achievement_id": achievement_id
                    })
                
                if user_achievement['reward_item_id']:
                    await conn.execute("""
                        INSERT INTO user_items (user_id, item_id, obtained_from)
                        VALUES ($1, $2, 'achievement')
                        ON CONFLICT (user_id, item_id) DO UPDATE SET
                            quantity = user_items.quantity + 1
                    """, interaction.user.id, user_achievement['reward_item_id'])
                
                # Mark as claimed
                await conn.execute("""
                    UPDATE user_achievements SET reward_claimed = true
                    WHERE user_id = $1 AND achievement_id = $2
                """, interaction.user.id, achievement_id)
                
                # Get achievement name
                achievement = await conn.fetchrow("""
                    SELECT name FROM achievements WHERE achievement_id = $1
                """, achievement_id)
                
                embed = discord.Embed(
                    description=config.Design.small_caps(
                        f"claimed reward for {achievement['name']}"
                    ),
                    color=config.Colors.SUCCESS
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    async def check_achievement_progress(self, user_id: int, achievement_type: str, progress_amount: int = 1):
        """Check and update achievement progress"""
        try:
            async with db.pool.acquire() as conn:
                # Get relevant achievements
                achievements = await conn.fetch("""
                    SELECT * FROM achievements 
                    WHERE requirement LIKE $1
                """, f"{achievement_type}%")
                
                for achievement in achievements:
                    # Parse requirement
                    target = int(achievement['requirement'].split(":")[1])
                    
                    # Get current progress
                    user_achievement = await conn.fetchrow("""
                        SELECT * FROM user_achievements 
                        WHERE user_id = $1 AND achievement_id = $2
                    """, user_id, achievement['achievement_id'])
                    
                    if user_achievement and user_achievement['completed']:
                        continue  # Already completed
                    
                    new_progress = progress_amount
                    if user_achievement:
                        new_progress = user_achievement['progress'] + progress_amount
                    
                    # Update progress
                    if user_achievement:
                        await conn.execute("""
                            UPDATE user_achievements 
                            SET progress = $1
                            WHERE user_id = $2 AND achievement_id = $3
                        """, new_progress, user_id, achievement['achievement_id'])
                    else:
                        await conn.execute("""
                            INSERT INTO user_achievements (user_id, achievement_id, progress)
                            VALUES ($1, $2, $3)
                        """, user_id, achievement['achievement_id'], new_progress)
                    
                    # Check if completed
                    if new_progress >= target:
                        await conn.execute("""
                            UPDATE user_achievements 
                            SET completed = true, completed_at = $1
                            WHERE user_id = $2 AND achievement_id = $3
                        """, discord.utils.utcnow(), user_id, achievement['achievement_id'])
                        
                        # Notify user
                        user = self.bot.get_user(user_id)
                        if user:
                            try:
                                embed = discord.Embed(
                                    description=config.Design.small_caps(
                                        f"achievement unlocked: {achievement['name']}"
                                    ),
                                    color=config.Colors.SUCCESS
                                )
                                await user.send(embed=embed)
                            except:
                                pass
                
        except Exception as e:
            print(f"Error checking achievement progress: {e}")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Track messages for achievements"""
        if message.author.bot:
            return
        
        # Check message achievements
        await self.check_achievement_progress(message.author.id, "messages", 1)

    @commands.Cog.listener()
    async def on_user_balance_update(self, user_id: int, new_balance: float):
        """Track balance for achievements"""
        await self.check_achievement_progress(user_id, "balance", int(new_balance))

    @commands.Cog.listener() 
    async def on_box_opened(self, user_id: int):
        """Track box openings for achievements"""
        await self.check_achievement_progress(user_id, "boxes_opened", 1)

    @commands.Cog.listener()
    async def on_trade_completed(self, user_id: int):
        """Track trades for achievements"""
        await self.check_achievement_progress(user_id, "trades", 1)

async def setup(bot):
    await bot.add_cog(Achievements(bot))