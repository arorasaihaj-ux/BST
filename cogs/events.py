import discord
from discord.ext import commands, tasks
from discord import app_commands
import config
from database import db
from datetime import datetime, timedelta
import random

class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_events.start()

    @app_commands.command(name="events", description="View current events")
    async def view_events(self, interaction: discord.Interaction):
        """View current events"""
        try:
            async with db.pool.acquire() as conn:
                events = await conn.fetch("""
                    SELECT e.*,
                           ep.progress,
                           ep.completed,
                           ep.reward_claimed
                    FROM events e
                    LEFT JOIN event_participants ep ON e.event_id = ep.event_id 
                        AND ep.user_id = $1
                    WHERE e.status = 'active' AND e.end_time > NOW()
                    ORDER BY e.end_time ASC
                """, interaction.user.id)
            
            if not events:
                await interaction.response.send_message(
                    "No active events right now.",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(color=config.Colors.PRIMARY)
            
            header = config.Design.header("ACTIVE EVENTS", 28)
            embed.description = f"\n{header}\n"
            
            for event in events:
                time_left = event['end_time'] - datetime.utcnow()
                days_left = max(0, int(time_left.total_seconds() // 86400))
                hours_left = max(0, int((time_left.total_seconds() % 86400) // 3600))
                
                status = "✅ Completed" if event['completed'] else f"⏳ {event['progress'] or 0}%"
                
                embed.add_field(
                    name=f"🎪 {event['name']}",
                    value=(
                        f"{event['description']}\n"
                        f"Time left: {days_left}d {hours_left}h\n"
                        f"Your progress: {status}\n"
                        f"Reward: {event['reward_bst']} BST\n"
                        f"ID: `{event['event_id']}`"
                    ),
                    inline=False
                )
            
            view = discord.ui.View()
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label="Join Event",
                custom_id="join_event"
            ))
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.success,
                label="Check Progress",
                custom_id="check_event"
            ))
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="joinevent", description="Join an event")
    async def join_event(self, interaction: discord.Interaction, event_id: str):
        """Join an event"""
        try:
            async with db.pool.acquire() as conn:
                # Check if event exists and is active
                event = await conn.fetchrow("""
                    SELECT * FROM events 
                    WHERE event_id = $1 AND status = 'active' AND end_time > NOW()
                """, event_id)
                
                if not event:
                    await interaction.response.send_message(
                        "Event not found or ended.",
                        ephemeral=True
                    )
                    return
                
                # Check if already participating
                participant = await conn.fetchrow("""
                    SELECT * FROM event_participants 
                    WHERE event_id = $1 AND user_id = $2
                """, event_id, interaction.user.id)
                
                if participant:
                    await interaction.response.send_message(
                        "You are already participating in this event.",
                        ephemeral=True
                    )
                    return
                
                # Join event
                await conn.execute("""
                    INSERT INTO event_participants (event_id, user_id)
                    VALUES ($1, $2)
                """, event_id, interaction.user.id)
                
                embed = discord.Embed(
                    description=config.Design.small_caps(
                        f"joined event: {event['name']}"
                    ),
                    color=config.Colors.SUCCESS
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="eventprogress", description="Check your event progress")
    async def event_progress(self, interaction: discord.Interaction, event_id: str):
        """Check event progress"""
        try:
            async with db.pool.acquire() as conn:
                participant = await conn.fetchrow("""
                    SELECT ep.*, e.name as event_name, e.description, e.reward_bst
                    FROM event_participants ep
                    JOIN events e ON ep.event_id = e.event_id
                    WHERE ep.event_id = $1 AND ep.user_id = $2
                """, event_id, interaction.user.id)
                
                if not participant:
                    await interaction.response.send_message(
                        "You are not participating in this event.",
                        ephemeral=True
                    )
                    return
                
                event = await conn.fetchrow("SELECT * FROM events WHERE event_id = $1", event_id)
                time_left = event['end_time'] - datetime.utcnow()
                days_left = max(0, int(time_left.total_seconds() // 86400))
                
                embed = discord.Embed(color=config.Colors.PRIMARY)
                
                header = config.Design.header(f"EVENT: {event['name']}", 28)
                embed.description = f"\n{header}\n"
                
                content = (
                    f"\n{config.Design.field('Description', event['description'], 15)}\n"
                    f"{config.Design.field('Progress', f'{participant['progress']}%', 15)}\n"
                    f"{config.Design.field('Time Left', f'{days_left} days', 15)}\n"
                    f"{config.Design.field('Reward', f'{event['reward_bst']} BST', 15)}\n"
                    f"{config.Design.field('Completed', 'Yes' if participant['completed'] else 'No', 15)}\n"
                )
                
                embed.add_field(name="\u200b", value=content, inline=False)
                
                if participant['completed'] and not participant['reward_claimed']:
                    view = discord.ui.View()
                    view.add_item(discord.ui.Button(
                        style=discord.ButtonStyle.success,
                        label="Claim Reward",
                        custom_id=f"claim_event_{event_id}"
                    ))
                    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                else:
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="claimevent", description="Claim event reward")
    async def claim_event_reward(self, interaction: discord.Interaction, event_id: str):
        """Claim event reward"""
        try:
            async with db.pool.acquire() as conn:
                participant = await conn.fetchrow("""
                    SELECT ep.*, e.reward_bst, e.reward_item_id
                    FROM event_participants ep
                    JOIN events e ON ep.event_id = e.event_id
                    WHERE ep.event_id = $1 AND ep.user_id = $2
                """, event_id, interaction.user.id)
                
                if not participant:
                    await interaction.response.send_message(
                        "You are not participating in this event.",
                        ephemeral=True
                    )
                    return
                
                if not participant['completed']:
                    await interaction.response.send_message(
                        "Event not completed yet.",
                        ephemeral=True
                    )
                    return
                
                if participant['reward_claimed']:
                    await interaction.response.send_message(
                        "Reward already claimed.",
                        ephemeral=True
                    )
                    return
                
                # Award rewards
                if participant['reward_bst'] > 0:
                    await conn.execute("""
                        UPDATE users SET bst_balance = bst_balance + $1
                        WHERE user_id = $2
                    """, participant['reward_bst'], interaction.user.id)
                    
                    await conn.execute("""
                        INSERT INTO transactions (user_id, tx_type, amount_bst, metadata)
                        VALUES ($1, 'event_reward', $2, $3)
                    """, interaction.user.id, participant['reward_bst'], {
                        "event_id": event_id
                    })
                
                if participant['reward_item_id']:
                    await conn.execute("""
                        INSERT INTO user_items (user_id, item_id, obtained_from)
                        VALUES ($1, $2, 'event')
                        ON CONFLICT (user_id, item_id) DO UPDATE SET
                            quantity = user_items.quantity + 1
                    """, interaction.user.id, participant['reward_item_id'])
                
                # Mark reward as claimed
                await conn.execute("""
                    UPDATE event_participants SET reward_claimed = true
                    WHERE event_id = $1 AND user_id = $2
                """, event_id, interaction.user.id)
                
                # Get event name
                event = await conn.fetchrow("SELECT name FROM events WHERE event_id = $1", event_id)
                
                embed = discord.Embed(
                    description=config.Design.small_caps(
                        f"claimed reward for {event['name']} event"
                    ),
                    color=config.Colors.SUCCESS
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @tasks.loop(minutes=5)
    async def check_events(self):
        """Check and update events"""
        try:
            async with db.pool.acquire() as conn:
                # Check for ended events
                ended_events = await conn.fetch("""
                    SELECT * FROM events 
                    WHERE status = 'active' AND end_time <= NOW()
                """)
                
                for event in ended_events:
                    # Update event status
                    await conn.execute("""
                        UPDATE events SET status = 'ended'
                        WHERE event_id = $1
                    """, event['event_id'])
                    
                    # Award rewards to completed participants
                    completed_participants = await conn.fetch("""
                        SELECT * FROM event_participants 
                        WHERE event_id = $1 AND completed = true AND reward_claimed = false
                    """, event['event_id'])
                    
                    for participant in completed_participants:
                        if event['reward_bst'] > 0:
                            await conn.execute("""
                                UPDATE users SET bst_balance = bst_balance + $1
                                WHERE user_id = $2
                            """, event['reward_bst'], participant['user_id'])
                        
                        if event['reward_item_id']:
                            await conn.execute("""
                                INSERT INTO user_items (user_id, item_id, obtained_from)
                                VALUES ($1, $2, 'event')
                                ON CONFLICT (user_id, item_id) DO UPDATE SET
                                    quantity = user_items.quantity + 1
                            """, participant['user_id'], event['reward_item_id'])
                        
                        await conn.execute("""
                            UPDATE event_participants SET reward_claimed = true
                            WHERE event_id = $1 AND user_id = $2
                        """, event['event_id'], participant['user_id'])
                
        except Exception as e:
            print(f"Error in event check: {e}")

    async def update_event_progress(self, user_id: int, event_type: str, progress_amount: int = 1):
        """Update user's event progress"""
        try:
            async with db.pool.acquire() as conn:
                # Get active events of this type
                events = await conn.fetch("""
                    SELECT e.*, ep.progress
                    FROM events e
                    JOIN event_participants ep ON e.event_id = ep.event_id
                    WHERE e.status = 'active' AND e.end_time > NOW() 
                    AND ep.user_id = $1 AND e.event_type = $2
                """, user_id, event_type)
                
                for event in events:
                    new_progress = min(100, event['progress'] + progress_amount)
                    
                    await conn.execute("""
                        UPDATE event_participants 
                        SET progress = $1, completed = $2
                        WHERE event_id = $3 AND user_id = $4
                    """, new_progress, new_progress >= 100, event['event_id'], user_id)
                
        except Exception as e:
            print(f"Error updating event progress: {e}")

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Handle event button interactions"""
        if not interaction.data or 'custom_id' not in interaction.data:
            return
        
        custom_id = interaction.data['custom_id']
        
        if custom_id == "join_event":
            # Send modal for joining event
            class JoinEventModal(discord.ui.Modal, title="Join Event"):
                event_id = discord.ui.TextInput(
                    label="Event ID",
                    placeholder="Enter the event ID...",
                    max_length=100
                )
                
                async def on_submit(self, interaction: discord.Interaction):
                    await self.cog.join_event(interaction, self.event_id.value)
            
            JoinEventModal.cog = self
            await interaction.response.send_modal(JoinEventModal())
            
        elif custom_id == "check_event":
            # Send modal for checking event
            class CheckEventModal(discord.ui.Modal, title="Check Event Progress"):
                event_id = discord.ui.TextInput(
                    label="Event ID",
                    placeholder="Enter the event ID...",
                    max_length=100
                )
                
                async def on_submit(self, interaction: discord.Interaction):
                    await self.cog.event_progress(interaction, self.event_id.value)
            
            CheckEventModal.cog = self
            await interaction.response.send_modal(CheckEventModal())
            
        elif custom_id.startswith("claim_event_"):
            event_id = custom_id.replace("claim_event_", "")
            await self.claim_event_reward(interaction, event_id)

    def cog_unload(self):
        self.check_events.cancel()

async def setup(bot):
    await bot.add_cog(Events(bot))