import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime, timedelta
import random
import config
from database import db

class Giveaways(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_giveaways = {}
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Resume active giveaways on bot start"""
        await self.resume_giveaways()
    
    async def resume_giveaways(self):
        """Resume any active giveaways"""
        async with db.pool.acquire() as conn:
            active = await conn.fetch(
                """SELECT * FROM giveaways 
                   WHERE status = 'active' AND ends_at > NOW()"""
            )
            
            for giveaway in active:
                self.bot.loop.create_task(
                    self.giveaway_timer(
                        str(giveaway['giveaway_id']),
                        giveaway['ends_at']
                    )
                )
    
    @app_commands.command(name="giveaway", description="Create a giveaway")
    @app_commands.describe(
        prize_type="Type of prize (bst/item/box)",
        prize_amount="Amount of BST or quantity",
        prize_name="Name of item/box (if applicable)",
        winners="Number of winners",
        duration="Duration in minutes",
        required_role="Required role to enter (optional)"
    )
    async def create_giveaway(
        self,
        interaction: discord.Interaction,
        prize_type: str,
        prize_amount: float,
        prize_name: str = None,
        winners: int = 1,
        duration: int = 60,
        required_role: discord.Role = None
    ):
        """Create a giveaway (ANY user can create)"""
        await interaction.response.defer()
        
        # Validate inputs
        if prize_type.lower() not in ['bst', 'item', 'box']:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=config.Design.small_caps("prize type must be: bst, item, or box"),
                    color=config.Colors.ERROR
                ),
                ephemeral=True
            )
            return
        
        if prize_amount <= 0 or winners <= 0 or duration <= 0:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=config.Design.small_caps("all values must be positive"),
                    color=config.Colors.ERROR
                ),
                ephemeral=True
            )
            return
        
        # If BST giveaway, check and deduct balance
        if prize_type.lower() == 'bst':
            balance = await db.get_balance(interaction.user.id)
            total_cost = prize_amount * winners
            
            if balance < total_cost:
                await interaction.followup.send(
                    embed=discord.Embed(
                        description=config.Design.small_caps(f"need {total_cost:.2f} BST total"),
                        color=config.Colors.ERROR
                    ),
                    ephemeral=True
                )
                return
        
        # Create giveaway in database
        giveaway_id = await db.create_giveaway(
            host_id=interaction.user.id,
            prize_type=prize_type.lower(),
            prize_amount=prize_amount,
            prize_item_name=prize_name or "BST",
            winners_count=winners,
            duration_minutes=duration,
            channel_id=interaction.channel_id,
            required_role=required_role.id if required_role else None
        )
        
        if not giveaway_id:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=config.Design.small_caps("failed to create giveaway"),
                    color=config.Colors.ERROR
                ),
                ephemeral=True
            )
            return
        
        # Calculate end time
        ends_at = datetime.now() + timedelta(minutes=duration)
        
        # Create giveaway panel
        embed = self.create_giveaway_embed(
            host=interaction.user,
            prize_type=prize_type.lower(),
            prize_amount=prize_amount,
            prize_name=prize_name,
            winners=winners,
            ends_at=ends_at,
            required_role=required_role,
            entries=0
        )
        
        # Create view with join button
        view = GiveawayView(giveaway_id, required_role.id if required_role else None)
        
        # Send panel
        panel_message = await interaction.channel.send(embed=embed, view=view)
        
        # Update database with message ID
        async with db.pool.acquire() as conn:
            await conn.execute(
                "UPDATE giveaways SET panel_message_id = $1 WHERE giveaway_id = $2",
                panel_message.id, giveaway_id
            )
        
        # Store in memory
        self.active_giveaways[giveaway_id] = {
            'message': panel_message,
            'view': view
        }
        
        # Start timer
        self.bot.loop.create_task(self.giveaway_timer(giveaway_id, ends_at))
        
        # Confirm to creator
        await interaction.followup.send(
            embed=discord.Embed(
                description=config.Design.small_caps(f"giveaway created • id: {giveaway_id[:8]}"),
                color=config.Colors.SUCCESS
            ),
            ephemeral=True
        )
    
    def create_giveaway_embed(self, host, prize_type, prize_amount, prize_name, 
                             winners, ends_at, required_role, entries):
        """Create giveaway embed"""
        embed = discord.Embed(color=config.Colors.PRIMARY)
        
        header = config.Design.header("GIVEAWAY", 28)
        embed.description = f"```\n{header}\n```"
        
        # Prize info
        if prize_type == 'bst':
            prize_text = f"{prize_amount:.2f} BST"
        else:
            prize_text = f"{prize_name} × {int(prize_amount)}"
        
        content = (
            f"\n{config.Design.field('prize', prize_text, 20)}\n"
            f"{config.Design.field('winners', str(winners), 20)}\n"
            f"{config.Design.field('host', host.display_name, 20)}\n"
            f"{config.Design.field('entries', str(entries), 20)}\n"
            f"{config.Design.field('ends', f'<t:{int(ends_at.timestamp())}:R>', 20)}\n"
        )
        
        if required_role:
            content += f"{config.Design.field('requirement', required_role.name, 20)}\n"
        
        embed.add_field(name="\u200b", value=content, inline=False)
        
        return embed
    
    async def giveaway_timer(self, giveaway_id: str, ends_at: datetime):
        """Timer for giveaway"""
        # Wait until end time
        wait_seconds = (ends_at - datetime.now()).total_seconds()
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
        
        # End giveaway
        await self.end_giveaway(giveaway_id)
    
    async def end_giveaway(self, giveaway_id: str):
        """End giveaway and pick winners"""
        async with db.pool.acquire() as conn:
            # Get giveaway details
            giveaway = await conn.fetchrow(
                "SELECT * FROM giveaways WHERE giveaway_id = $1",
                giveaway_id
            )
            
            if not giveaway or giveaway['status'] != 'active':
                return
            
            # Get entries
            entries = await conn.fetch(
                """SELECT user_id FROM giveaway_entries 
                   WHERE giveaway_id = $1""",
                giveaway_id
            )
            
            if not entries:
                # No entries
                await conn.execute(
                    "UPDATE giveaways SET status = 'ended', ended_at = NOW() WHERE giveaway_id = $1",
                    giveaway_id
                )
                
                # Update panel
                if giveaway_id in self.active_giveaways:
                    try:
                        message = self.active_giveaways[giveaway_id]['message']
                        embed = discord.Embed(
                            description=config.Design.small_caps("giveaway ended • no entries"),
                            color=config.Colors.ERROR
                        )
                        await message.edit(embed=embed, view=None)
                    except:
                        pass
                
                return
            
            # Pick winners
            winner_count = min(giveaway['winners_count'], len(entries))
            winners = random.sample([e['user_id'] for e in entries], winner_count)
            
            # Distribute prizes
            for winner_id in winners:
                if giveaway['prize_type'] == 'bst':
                    await db.update_balance(winner_id, float(giveaway['prize_amount']), 'add')
                    await db.log_transaction(
                        'giveaway_win', giveaway['host_id'], winner_id,
                        float(giveaway['prize_amount']), 
                        {'giveaway_id': giveaway_id}
                    )
            
            # Mark as ended
            await conn.execute(
                "UPDATE giveaways SET status = 'ended', ended_at = NOW() WHERE giveaway_id = $1",
                giveaway_id
            )
        
        # Update panel with winners
        if giveaway_id in self.active_giveaways:
            try:
                message = self.active_giveaways[giveaway_id]['message']
                
                embed = discord.Embed(color=config.Colors.SUCCESS)
                header = config.Design.header("ENDED", 28)
                embed.description = f"```\n{header}\n```"
                
                winner_text = "\n"
                for winner_id in winners:
                    winner_text += f"{config.Design.item(f'<@{winner_id}>')}\n"
                
                embed.add_field(name="Winners", value=winner_text, inline=False)
                
                await message.edit(embed=embed, view=None)
                
                # Announce winners
                winner_mentions = ' '.join([f'<@{w}>' for w in winners])
                await message.channel.send(
                    f"🎉 Giveaway winners: {winner_mentions}"
                )
            except:
                pass
        
        # Clean up
        if giveaway_id in self.active_giveaways:
            del self.active_giveaways[giveaway_id]
    
    @app_commands.command(name="gend", description="End a giveaway early")
    @app_commands.describe(giveaway_id="Giveaway ID to end")
    async def end_giveaway_command(self, interaction: discord.Interaction, giveaway_id: str):
        """End giveaway early (host or admin only)"""
        await interaction.response.defer(ephemeral=True)
        
        async with db.pool.acquire() as conn:
            giveaway = await conn.fetchrow(
                "SELECT * FROM giveaways WHERE giveaway_id = $1",
                giveaway_id
            )
            
            if not giveaway:
                await interaction.followup.send(
                    embed=discord.Embed(
                        description=config.Design.small_caps("giveaway not found"),
                        color=config.Colors.ERROR
                    ),
                    ephemeral=True
                )
                return
            
            # Check if user is host or owner
            if interaction.user.id != giveaway['host_id'] and interaction.user.id != config.OWNER_ID:
                await interaction.followup.send(
                    embed=discord.Embed(
                        description=config.Design.small_caps("only host or owner can end"),
                        color=config.Colors.ERROR
                    ),
                    ephemeral=True
                )
                return
            
            if giveaway['status'] != 'active':
                await interaction.followup.send(
                    embed=discord.Embed(
                        description=config.Design.small_caps("giveaway already ended"),
                        color=config.Colors.ERROR
                    ),
                    ephemeral=True
                )
                return
        
        # End it
        await self.end_giveaway(giveaway_id)
        
        await interaction.followup.send(
            embed=discord.Embed(
                description=config.Design.small_caps("giveaway ended"),
                color=config.Colors.SUCCESS
            ),
            ephemeral=True
        )

class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id: str, required_role: int = None):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
        self.required_role = required_role
    
    @discord.ui.button(label="🎉 Enter Giveaway", style=discord.ButtonStyle.green, custom_id="enter_giveaway")
    async def enter_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Enter the giveaway"""
        await interaction.response.defer(ephemeral=True)
        
        # Check role requirement
        if self.required_role:
            if not any(role.id == self.required_role for role in interaction.user.roles):
                await interaction.followup.send(
                    embed=discord.Embed(
                        description=config.Design.small_caps("you don't have the required role"),
                        color=config.Colors.ERROR
                    ),
                    ephemeral=True
                )
                return
        
        # Enter giveaway
        success = await db.enter_giveaway(self.giveaway_id, interaction.user.id)
        
        if success:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=config.Design.small_caps("entered successfully"),
                    color=config.Colors.SUCCESS
                ),
                ephemeral=True
            )
            
            # Update entry count in panel
            async with db.pool.acquire() as conn:
                entry_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id = $1",
                    self.giveaway_id
                )
                
                # Update embed (if possible)
                try:
                    embed = interaction.message.embeds[0]
                    # Update entries field in embed
                    await interaction.message.edit(embed=embed)
                except:
                    pass
        else:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=config.Design.small_caps("already entered"),
                    color=config.Colors.WARNING
                ),
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Giveaways(bot))