import discord
from discord.ext import commands, tasks
from discord import app_commands
import config
from database import db
from datetime import datetime, timedelta

class Loyalty(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_loyalty.start()

    @app_commands.command(name="loyalty", description="View loyalty program")
    async def view_loyalty(self, interaction: discord.Interaction):
        """View loyalty program status"""
        try:
            async with db.pool.acquire() as conn:
                # Get loyalty tiers
                tiers = await conn.fetch("""
                    SELECT * FROM loyalty_tiers 
                    ORDER BY required_days ASC
                """)
                
                # Get user loyalty status
                user_loyalty = await conn.fetchrow("""
                    SELECT * FROM user_loyalty 
                    WHERE user_id = $1
                """, interaction.user.id)
                
                if not user_loyalty:
                    # Initialize user loyalty
                    user_loyalty = await conn.fetchrow("""
                        INSERT INTO user_loyalty (user_id)
                        VALUES ($1)
                        RETURNING *
                    """, interaction.user.id)
            
            embed = discord.Embed(color=config.Colors.PRIMARY)
            
            header = config.Design.header("LOYALTY PROGRAM", 28)
            embed.description = f"\n{header}\n"
            
            # User status
            current_tier = user_loyalty['current_tier']
            total_days = user_loyalty['total_days']
            current_streak = user_loyalty['current_streak']
            best_streak = user_loyalty['best_streak']
            
            content = (
                f"\n{config.Design.field('Current Tier', f'Tier {current_tier}', 15)}\n"
                f"{config.Design.field('Total Days', total_days, 15)}\n"
                f"{config.Design.field('Current Streak', f'{current_streak} days', 15)}\n"
                f"{config.Design.field('Best Streak', f'{best_streak} days', 15)}\n"
            )
            
            embed.add_field(name="Your Status", value=content, inline=False)
            
            # Loyalty tiers
            tiers_content = ""
            for tier in tiers:
                status = "✅" if total_days >= tier['required_days'] else "⏳"
                tiers_content += (
                    f"{status} **{tier['name']}** - {tier['required_days']} days\n"
                    f"Reward: {tier['reward_bst']} BST\n\n"
                )
            
            embed.add_field(name="Loyalty Tiers", value=tiers_content, inline=False)
            
            view = discord.ui.View()
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label="Claim Daily",
                custom_id="claim_daily"
            ))
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="claimdaily", description="Claim daily loyalty reward")
    async def claim_daily(self, interaction: discord.Interaction):
        """Claim daily loyalty reward"""
        try:
            async with db.pool.acquire() as conn:
                # Get user loyalty status
                user_loyalty = await conn.fetchrow("""
                    SELECT * FROM user_loyalty 
                    WHERE user_id = $1
                """, interaction.user.id)
                
                now = datetime.utcnow()
                
                # Check if already claimed today
                if user_loyalty['last_claim']:
                    last_claim = user_loyalty['last_claim'].replace(tzinfo=None)
                    if (now - last_claim).days < 1:
                        if now.date() == last_claim.date():
                            await interaction.response.send_message(
                                "You have already claimed your daily reward today!",
                                ephemeral=True
                            )
                            return
                
                # Calculate streak
                new_streak = 1
                if user_loyalty['last_claim']:
                    last_claim = user_loyalty['last_claim'].replace(tzinfo=None)
                    if (now - last_claim).days == 1:
                        new_streak = user_loyalty['current_streak'] + 1
                    elif (now - last_claim).days > 1:
                        new_streak = 1  # Streak broken
                
                # Update loyalty status
                total_days = user_loyalty['total_days'] + 1
                best_streak = max(user_loyalty['best_streak'], new_streak)
                
                # Determine current tier based on total days
                tiers = await conn.fetch("SELECT * FROM loyalty_tiers ORDER BY required_days ASC")
                current_tier = 1
                for tier in tiers:
                    if total_days >= tier['required_days']:
                        current_tier = tier['tier_id']
                    else:
                        break
                
                await conn.execute("""
                    UPDATE user_loyalty 
                    SET total_days = $1,
                        current_streak = $2,
                        best_streak = $3,
                        current_tier = $4,
                        last_claim = $5
                    WHERE user_id = $6
                """, total_days, new_streak, best_streak, current_tier, now, interaction.user.id)
                
                # Award daily BST
                daily_reward = 0.5  # Base daily reward
                streak_bonus = new_streak * 0.1  # 0.1 BST per streak day
                total_reward = daily_reward + streak_bonus
                
                await conn.execute("""
                    UPDATE users SET bst_balance = bst_balance + $1
                    WHERE user_id = $2
                """, total_reward, interaction.user.id)
                
                # Record transaction
                await conn.execute("""
                    INSERT INTO transactions (user_id, tx_type, amount_bst, metadata)
                    VALUES ($1, 'daily_loyalty', $2, $3)
                """, interaction.user.id, total_reward, {
                    "streak": new_streak,
                    "total_days": total_days,
                    "tier": current_tier
                })
                
                # Check for tier rewards
                tier_rewards = []
                for tier in tiers:
                    if total_days == tier['required_days']:
                        # Award tier reward
                        await conn.execute("""
                            UPDATE users SET bst_balance = bst_balance + $1
                            WHERE user_id = $2
                        """, tier['reward_bst'], interaction.user.id)
                        
                        if tier['reward_item_id']:
                            await conn.execute("""
                                INSERT INTO user_items (user_id, item_id, obtained_from)
                                VALUES ($1, $2, 'loyalty')
                                ON CONFLICT (user_id, item_id) DO UPDATE SET
                                    quantity = user_items.quantity + 1
                            """, interaction.user.id, tier['reward_item_id'])
                        
                        tier_rewards.append(f"{tier['reward_bst']} BST")
                        
                        # Record tier transaction
                        await conn.execute("""
                            INSERT INTO transactions (user_id, tx_type, amount_bst, metadata)
                            VALUES ($1, 'tier_reward', $2, $3)
                        """, interaction.user.id, tier['reward_bst'], {
                            "tier": tier['name'],
                            "days_required": tier['required_days']
                        })
                
                # Build response
                reward_text = f"claimed {total_reward:.2f} BST daily reward"
                if new_streak > 1:
                    reward_text += f" (streak: {new_streak} days)"
                
                if tier_rewards:
                    reward_text += f"\n🎉 Tier reward: {', '.join(tier_rewards)}"
                
                embed = discord.Embed(
                    description=config.Design.small_caps(reward_text),
                    color=config.Colors.SUCCESS
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="loyaltyleaderboard", description="View loyalty leaderboard")
    async def loyalty_leaderboard(self, interaction: discord.Interaction):
        """View loyalty leaderboard"""
        try:
            async with db.pool.acquire() as conn:
                leaderboard = await conn.fetch("""
                    SELECT ul.*, u.discord_tag
                    FROM user_loyalty ul
                    JOIN users u ON ul.user_id = u.user_id
                    ORDER BY ul.total_days DESC, ul.best_streak DESC
                    LIMIT 10
                """)
            
            embed = discord.Embed(color=config.Colors.PRIMARY)
            
            header = config.Design.header("LOYALTY LEADERBOARD", 28)
            embed.description = f"\n{header}\n"
            
            if not leaderboard:
                embed.add_field(
                    name="No Data",
                    value="No loyalty data available yet.",
                    inline=False
                )
            else:
                leaderboard_text = ""
                for i, user in enumerate(leaderboard, 1):
                    medal = ""
                    if i == 1: medal = "🥇"
                    elif i == 2: medal = "🥈" 
                    elif i == 3: medal = "🥉"
                    else: medal = f"{i}."
                    
                    leaderboard_text += (
                        f"{medal} **{user['discord_tag']}**\n"
                        f"Days: {user['total_days']} | Streak: {user['current_streak']}\n\n"
                    )
                
                embed.add_field(name="\u200b", value=leaderboard_text, inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @tasks.loop(hours=24)
    async def check_loyalty(self):
        """Check for broken streaks"""
        try:
            async with db.pool.acquire() as conn:
                # Get users who haven't claimed in over 2 days (broken streak)
                broken_streaks = await conn.fetch("""
                    SELECT * FROM user_loyalty 
                    WHERE last_claim < $1 AND current_streak > 0
                """, datetime.utcnow() - timedelta(days=2))
                
                for user in broken_streaks:
                    # Reset current streak but keep best streak
                    await conn.execute("""
                        UPDATE user_loyalty 
                        SET current_streak = 0
                        WHERE user_id = $1
                    """, user['user_id'])
                    
                    # Notify user
                    discord_user = self.bot.get_user(user['user_id'])
                    if discord_user:
                        try:
                            embed = discord.Embed(
                                description=config.Design.small_caps(
                                    f"your {user['current_streak']} day streak has been broken! claim daily to start a new one"
                                ),
                                color=config.Colors.WARNING
                            )
                            await discord_user.send(embed=embed)
                        except:
                            pass
                
        except Exception as e:
            print(f"Error in loyalty check: {e}")

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Handle loyalty button interactions"""
        if not interaction.data or 'custom_id' not in interaction.data:
            return
        
        if interaction.data['custom_id'] == "claim_daily":
            await self.claim_daily(interaction)

    def cog_unload(self):
        self.check_loyalty.cancel()

async def setup(bot):
    await bot.add_cog(Loyalty(bot))