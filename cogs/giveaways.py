import discord
from discord.ext import commands, tasks
from discord import app_commands
import config
from database import db
from datetime import datetime, timedelta
import random
import asyncio

class Giveaways(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_giveaways.start()

    @app_commands.command(name="giveaway", description="Create a new giveaway")
    async def create_giveaway(self, interaction: discord.Interaction, prize: str, duration_hours: int, winners: int = 1):
        """Create a new giveaway"""
        try:
            if duration_hours < 1 or duration_hours > 168:  # Max 1 week
                await interaction.response.send_message(
                    "Duration must be between 1 and 168 hours.",
                    ephemeral=True
                )
                return
            
            if winners < 1 or winners > 10:
                await interaction.response.send_message(
                    "Winners must be between 1 and 10.",
                    ephemeral=True
                )
                return
            
            # Calculate end time
            end_time = datetime.utcnow() + timedelta(hours=duration_hours)
            
            # Create giveaway in database
            async with db.pool.acquire() as conn:
                giveaway = await conn.fetchrow("""
                    INSERT INTO giveaways (host_id, prize, winner_count, end_time)
                    VALUES ($1, $2, $3, $4)
                    RETURNING *
                """, interaction.user.id, prize, winners, end_time)
            
            # Create giveaway embed
            embed = discord.Embed(color=config.Colors.PRIMARY)
            
            header = config.Design.header("GIVEAWAY", 28)
            embed.description = f"\n{header}\n"
            
            content = (
                f"\n**Prize:** {prize}\n"
                f"**Host:** {interaction.user.mention}\n"
                f"**Winners:** {winners}\n"
                f"**Ends:** <t:{int(end_time.timestamp())}:R>\n"
                f"**Entries:** 0\n\n"
                f"Click the button below to enter!"
            )
            
            embed.add_field(name="\u200b", value=content, inline=False)
            
            # Create view with enter button
            view = discord.ui.View()
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label="🎁 Enter Giveaway",
                custom_id=f"enter_giveaway_{giveaway['giveaway_id']}"
            ))
            
            # Send to giveaway channel
            giveaway_channel = self.bot.get_channel(config.GIVEAWAY_CHANNEL_ID)
            if giveaway_channel:
                message = await giveaway_channel.send(embed=embed, view=view)
                
                # Update giveaway with message info
                async with db.pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE giveaways 
                        SET channel_id = $1, message_id = $2
                        WHERE giveaway_id = $3
                    """, giveaway_channel.id, message.id, giveaway['giveaway_id'])
            
            embed = discord.Embed(
                description=config.Design.small_caps(
                    f"giveaway created for {prize} with {winners} winner(s)"
                ),
                color=config.Colors.SUCCESS
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="giveawaylist", description="View active giveaways")
    async def giveaway_list(self, interaction: discord.Interaction):
        """View active giveaways"""
        try:
            async with db.pool.acquire() as conn:
                giveaways = await conn.fetch("""
                    SELECT g.*, u.discord_tag as host_name,
                           COUNT(ge.entry_id) as entry_count
                    FROM giveaways g
                    JOIN users u ON g.host_id = u.user_id
                    LEFT JOIN giveaway_entries ge ON g.giveaway_id = ge.giveaway_id
                    WHERE g.status = 'active' AND g.end_time > NOW()
                    GROUP BY g.giveaway_id, u.discord_tag
                    ORDER BY g.end_time ASC
                """)
            
            if not giveaways:
                await interaction.response.send_message(
                    "No active giveaways right now.",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(color=config.Colors.PRIMARY)
            
            header = config.Design.header("ACTIVE GIVEAWAYS", 28)
            embed.description = f"\n{header}\n"
            
            for giveaway in giveaways:
                time_left = giveaway['end_time'] - datetime.utcnow()
                hours_left = max(0, int(time_left.total_seconds() // 3600))
                
                # Check if user has entered
                user_entry = await conn.fetchrow("""
                    SELECT * FROM giveaway_entries 
                    WHERE giveaway_id = $1 AND user_id = $2
                """, giveaway['giveaway_id'], interaction.user.id)
                
                entry_status = "✅ Entered" if user_entry else "❌ Not Entered"
                
                embed.add_field(
                    name=f"🎁 {giveaway['prize']}",
                    value=(
                        f"Host: {giveaway['host_name']}\n"
                        f"Winners: {giveaway['winner_count']}\n"
                        f"Time left: {hours_left}h\n"
                        f"Entries: {giveaway['entry_count']}\n"
                        f"Your status: {entry_status}\n"
                        f"ID: `{giveaway['giveaway_id']}`"
                    ),
                    inline=False
                )
            
            view = discord.ui.View()
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label="Enter Giveaway",
                custom_id="enter_giveaway_modal"
            ))
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="giveawayend", description="End a giveaway early")
    async def end_giveaway(self, interaction: discord.Interaction, giveaway_id: str):
        """End a giveaway early"""
        try:
            async with db.pool.acquire() as conn:
                # Get giveaway
                giveaway = await conn.fetchrow("""
                    SELECT * FROM giveaways 
                    WHERE giveaway_id = $1 AND status = 'active'
                """, giveaway_id)
                
                if not giveaway:
                    await interaction.response.send_message(
                        "Giveaway not found or already ended.",
                        ephemeral=True
                    )
                    return
                
                # Check if user is host or has permission
                if giveaway['host_id'] != interaction.user.id and interaction.user.id != config.OWNER_ID:
                    await interaction.response.send_message(
                        "You can only end your own giveaways.",
                        ephemeral=True
                    )
                    return
                
                # End the giveaway
                await self.end_giveaway_process(giveaway_id)
                
                embed = discord.Embed(
                    description=config.Design.small_caps(
                        f"giveaway ended early"
                    ),
                    color=config.Colors.SUCCESS
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    async def end_giveaway_process(self, giveaway_id: str):
        """Process ending a giveaway"""
        try:
            async with db.pool.acquire() as conn:
                # Get giveaway and entries
                giveaway = await conn.fetchrow("""
                    SELECT * FROM giveaways 
                    WHERE giveaway_id = $1
                """, giveaway_id)
                
                entries = await conn.fetch("""
                    SELECT ge.*, u.discord_tag
                    FROM giveaway_entries ge
                    JOIN users u ON ge.user_id = u.user_id
                    WHERE ge.giveaway_id = $1
                """, giveaway_id)
                
                if not entries:
                    # No entries - just end it
                    await conn.execute("""
                        UPDATE giveaways SET status = 'ended'
                        WHERE giveaway_id = $1
                    """, giveaway_id)
                    return
                
                # Select winners
                winner_count = min(giveaway['winner_count'], len(entries))
                winners = random.sample(entries, winner_count)
                
                # Update giveaway status
                await conn.execute("""
                    UPDATE giveaways 
                    SET status = 'ended', ended_at = $1
                    WHERE giveaway_id = $2
                """, datetime.utcnow(), giveaway_id)
                
                # Update message in channel
                if giveaway['channel_id'] and giveaway['message_id']:
                    try:
                        channel = self.bot.get_channel(giveaway['channel_id'])
                        if channel:
                            message = await channel.fetch_message(giveaway['message_id'])
                            
                            # Update embed to show winners
                            embed = discord.Embed(color=config.Colors.PRIMARY)
                            
                            header = config.Design.header("GIVEAWAY ENDED", 28)
                            embed.description = f"\n{header}\n"
                            
                            winner_mentions = []
                            for winner in winners:
                                user = self.bot.get_user(winner['user_id'])
                                if user:
                                    winner_mentions.append(user.mention)
                                else:
                                    winner_mentions.append(winner['discord_tag'])
                            
                            content = (
                                f"\n**Prize:** {giveaway['prize']}\n"
                                f"**Host:** <@{giveaway['host_id']}>\n"
                                f"**Winners:** {', '.join(winner_mentions)}\n"
                                f"**Entries:** {len(entries)}\n\n"
                                f"🎉 Congratulations to the winners!"
                            )
                            
                            embed.add_field(name="\u200b", value=content, inline=False)
                            
                            await message.edit(embed=embed, view=None)
                    except Exception as e:
                        print(f"Error updating giveaway message: {e}")
                
                # Notify winners
                for winner in winners:
                    user = self.bot.get_user(winner['user_id'])
                    if user:
                        try:
                            embed = discord.Embed(
                                description=config.Design.small_caps(
                                    f"you won the giveaway for {giveaway['prize']}!"
                                ),
                                color=config.Colors.SUCCESS
                            )
                            await user.send(embed=embed)
                        except:
                            pass
                
        except Exception as e:
            print(f"Error ending giveaway: {e}")

    @tasks.loop(minutes=1)
    async def check_giveaways(self):
        """Check for ended giveaways"""
        try:
            async with db.pool.acquire() as conn:
                ended_giveaways = await conn.fetch("""
                    SELECT * FROM giveaways 
                    WHERE status = 'active' AND end_time <= NOW()
                """)
                
                for giveaway in ended_giveaways:
                    await self.end_giveaway_process(giveaway['giveaway_id'])
                
        except Exception as e:
            print(f"Error in giveaway check: {e}")

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Handle giveaway button interactions"""
        if not interaction.data or 'custom_id' not in interaction.data:
            return
        
        custom_id = interaction.data['custom_id']
        
        if custom_id.startswith("enter_giveaway_"):
            giveaway_id = custom_id.replace("enter_giveaway_", "")
            
            try:
                async with db.pool.acquire() as conn:
                    # Check if giveaway exists and is active
                    giveaway = await conn.fetchrow("""
                        SELECT * FROM giveaways 
                        WHERE giveaway_id = $1 AND status = 'active' AND end_time > NOW()
                    """, giveaway_id)
                    
                    if not giveaway:
                        await interaction.response.send_message(
                            "Giveaway not found or ended.",
                            ephemeral=True
                        )
                        return
                    
                    # Check if already entered
                    existing_entry = await conn.fetchrow("""
                        SELECT * FROM giveaway_entries 
                        WHERE giveaway_id = $1 AND user_id = $2
                    """, giveaway_id, interaction.user.id)
                    
                    if existing_entry:
                        await interaction.response.send_message(
                            "You have already entered this giveaway!",
                            ephemeral=True
                        )
                        return
                    
                    # Add entry
                    await conn.execute("""
                        INSERT INTO giveaway_entries (giveaway_id, user_id)
                        VALUES ($1, $2)
                    """, giveaway_id, interaction.user.id)
                    
                    # Update entry count in message
                    if giveaway['channel_id'] and giveaway['message_id']:
                        try:
                            channel = self.bot.get_channel(giveaway['channel_id'])
                            if channel:
                                message = await channel.fetch_message(giveaway['message_id'])
                                embed = message.embeds[0]
                                
                                # Update entry count in embed
                                new_description = embed.description.replace(
                                    f"**Entries:** {giveaway['entry_count']}",
                                    f"**Entries:** {giveaway['entry_count'] + 1}"
                                )
                                embed.description = new_description
                                
                                await message.edit(embed=embed)
                        except:
                            pass
                    
                    embed = discord.Embed(
                        description=config.Design.small_caps(
                            f"entered giveaway for {giveaway['prize']}"
                        ),
                        color=config.Colors.SUCCESS
                    )
                    
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    
            except Exception as e:
                await interaction.response.send_message(
                    f"Error: {str(e)}",
                    ephemeral=True
                )
        
        elif custom_id == "enter_giveaway_modal":
            # Send modal for entering giveaway
            class EnterGiveawayModal(discord.ui.Modal, title="Enter Giveaway"):
                giveaway_id = discord.ui.TextInput(
                    label="Giveaway ID",
                    placeholder="Enter the giveaway ID...",
                    max_length=100
                )
                
                async def on_submit(self, interaction: discord.Interaction):
                    # Reuse the enter giveaway logic
                    custom_id = f"enter_giveaway_{self.giveaway_id.value}"
                    interaction.data = {'custom_id': custom_id}
                    await self.cog.on_interaction(interaction)
            
            EnterGiveawayModal.cog = self
            await interaction.response.send_modal(EnterGiveawayModal())

    def cog_unload(self):
        self.check_giveaways.cancel()

async def setup(bot):
    await bot.add_cog(Giveaways(bot))