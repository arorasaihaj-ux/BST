import discord
from discord.ext import commands
from discord import app_commands
import config
from database import db

class Bounties(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="bounties", description="View active bounties")
    async def view_bounties(self, interaction: discord.Interaction):
        """View active bounties"""
        try:
            async with db.pool.acquire() as conn:
                bounties = await conn.fetch("""
                    SELECT b.*, u.discord_tag as poster_name
                    FROM bounties b
                    JOIN users u ON b.poster_id = u.user_id
                    WHERE b.status = 'open'
                    ORDER BY b.reward_bst DESC
                """)
            
            if not bounties:
                await interaction.response.send_message(
                    "No active bounties right now.",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(color=config.Colors.PRIMARY)
            
            header = config.Design.header("ACTIVE BOUNTIES", 28)
            embed.description = f"\n{header}\n"
            
            for bounty in bounties:
                embed.add_field(
                    name=f"💰 {bounty['item_requested']}",
                    value=(
                        f"Reward: {bounty['reward_bst']} BST\n"
                        f"Posted by: {bounty['poster_name']}\n"
                        f"ID: `{bounty['bounty_id']}`"
                    ),
                    inline=False
                )
            
            view = discord.ui.View()
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label="Post New Bounty",
                custom_id="post_bounty"
            ))
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.success,
                label="Claim Bounty",
                custom_id="claim_bounty"
            ))
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="postbounty", description="Post a new bounty")
    async def post_bounty(self, interaction: discord.Interaction, item: str, reward: float):
        """Post a new bounty"""
        try:
            if reward <= 0:
                await interaction.response.send_message(
                    "Reward must be positive.",
                    ephemeral=True
                )
                return
            
            # Check user balance
            user_data = await db.get_user(interaction.user.id)
            if user_data['bst_balance'] < reward:
                await interaction.response.send_message(
                    "Insufficient BST for bounty reward.",
                    ephemeral=True
                )
                return
            
            # Create bounty
            async with db.pool.acquire() as conn:
                bounty = await conn.fetchrow("""
                    INSERT INTO bounties (poster_id, item_requested, reward_bst)
                    VALUES ($1, $2, $3)
                    RETURNING *
                """, interaction.user.id, item, reward)
                
                # Hold reward in escrow
                await conn.execute("""
                    UPDATE users SET bst_balance = bst_balance - $1
                    WHERE user_id = $2
                """, reward, interaction.user.id)
                
                # Record transaction
                await conn.execute("""
                    INSERT INTO transactions (user_id, tx_type, amount_bst, metadata)
                    VALUES ($1, 'bounty_posted', $2, $3)
                """, interaction.user.id, -reward, {"bounty_id": bounty['bounty_id'], "item": item})
            
            embed = discord.Embed(
                description=config.Design.small_caps(
                    f"posted bounty for {item} with {reward} bst reward"
                ),
                color=config.Colors.SUCCESS
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="claimbounty", description="Claim a bounty reward")
    async def claim_bounty(self, interaction: discord.Interaction, bounty_id: str):
        """Claim a bounty"""
        try:
            async with db.pool.acquire() as conn:
                # Get bounty
                bounty = await conn.fetchrow("""
                    SELECT * FROM bounties 
                    WHERE bounty_id = $1 AND status = 'open'
                """, bounty_id)
                
                if not bounty:
                    await interaction.response.send_message(
                        "Bounty not found or already claimed.",
                        ephemeral=True
                    )
                    return
                
                # Check if user has the required item
                user_items = await conn.fetch("""
                    SELECT i.name FROM user_items ui
                    JOIN items i ON ui.item_id = i.item_id
                    WHERE ui.user_id = $1 AND ui.quantity > 0
                """, interaction.user.id)
                
                user_item_names = [item['name'].lower() for item in user_items]
                requested_item = bounty['item_requested'].lower()
                
                if requested_item not in user_item_names:
                    await interaction.response.send_message(
                        f"You don't have {bounty['item_requested']} to claim this bounty.",
                        ephemeral=True
                    )
                    return
                
                # Claim bounty
                await conn.execute("""
                    UPDATE bounties 
                    SET status = 'claimed', claimed_by = $1, claimed_at = $2
                    WHERE bounty_id = $3
                """, interaction.user.id, discord.utils.utcnow(), bounty_id)
                
                # Award reward
                await conn.execute("""
                    UPDATE users SET bst_balance = bst_balance + $1
                    WHERE user_id = $2
                """, bounty['reward_bst'], interaction.user.id)
                
                # Remove item from user
                item_to_remove = await conn.fetchrow("""
                    SELECT item_id FROM items WHERE name = $1
                """, bounty['item_requested'])
                
                if item_to_remove:
                    await conn.execute("""
                        UPDATE user_items SET quantity = quantity - 1
                        WHERE user_id = $1 AND item_id = $2
                    """, interaction.user.id, item_to_remove['item_id'])
                
                # Record transactions
                await conn.execute("""
                    INSERT INTO transactions (user_id, tx_type, amount_bst, metadata)
                    VALUES ($1, 'bounty_claimed', $2, $3)
                """, interaction.user.id, bounty['reward_bst'], {"bounty_id": bounty_id, "item": bounty['item_requested']})
                
                # Notify bounty poster
                poster = self.bot.get_user(bounty['poster_id'])
                if poster:
                    try:
                        notify_embed = discord.Embed(
                            description=config.Design.small_caps(
                                f"your bounty for {bounty['item_requested']} has been claimed by {interaction.user.display_name}"
                            ),
                            color=config.Colors.INFO
                        )
                        await poster.send(embed=notify_embed)
                    except:
                        pass
            
            embed = discord.Embed(
                description=config.Design.small_caps(
                    f"claimed bounty for {bounty['item_requested']} and received {bounty['reward_bst']} bst"
                ),
                color=config.Colors.SUCCESS
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="mybounties", description="View your posted bounties")
    async def my_bounties(self, interaction: discord.Interaction):
        """View user's posted bounties"""
        try:
            async with db.pool.acquire() as conn:
                bounties = await conn.fetch("""
                    SELECT * FROM bounties 
                    WHERE poster_id = $1
                    ORDER BY created_at DESC
                """, interaction.user.id)
            
            if not bounties:
                await interaction.response.send_message(
                    "You haven't posted any bounties.",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(color=config.Colors.PRIMARY)
            
            header = config.Design.header("MY BOUNTIES", 28)
            embed.description = f"\n{header}\n"
            
            for bounty in bounties:
                status = "✅ Claimed" if bounty['status'] == 'claimed' else "⏳ Active"
                claimed_by = f" by {self.bot.get_user(bounty['claimed_by']).display_name}" if bounty['claimed_by'] else ""
                
                embed.add_field(
                    name=f"{bounty['item_requested']} - {bounty['reward_bst']} BST",
                    value=f"Status: {status}{claimed_by}",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Handle bounty button interactions"""
        if not interaction.data or 'custom_id' not in interaction.data:
            return
        
        custom_id = interaction.data['custom_id']
        
        if custom_id == "post_bounty":
            # Send modal for posting bounty
            class BountyModal(discord.ui.Modal, title="Post New Bounty"):
                item = discord.ui.TextInput(
                    label="Item Wanted",
                    placeholder="Enter the item name...",
                    max_length=100
                )
                reward = discord.ui.TextInput(
                    label="Reward BST",
                    placeholder="Enter BST reward amount...",
                    max_length=10
                )
                
                async def on_submit(self, interaction: discord.Interaction):
                    try:
                        reward_amount = float(self.reward.value)
                        await self.cog.post_bounty(interaction, self.item.value, reward_amount)
                    except ValueError:
                        await interaction.response.send_message(
                            "Invalid reward amount.",
                            ephemeral=True
                        )
            
            BountyModal.cog = self
            await interaction.response.send_modal(BountyModal())
            
        elif custom_id == "claim_bounty":
            # Send modal for claiming bounty
            class ClaimModal(discord.ui.Modal, title="Claim Bounty"):
                bounty_id = discord.ui.TextInput(
                    label="Bounty ID",
                    placeholder="Enter the bounty ID...",
                    max_length=100
                )
                
                async def on_submit(self, interaction: discord.Interaction):
                    await self.cog.claim_bounty(interaction, self.bounty_id.value)
            
            ClaimModal.cog = self
            await interaction.response.send_modal(ClaimModal())

async def setup(bot):
    await bot.add_cog(Bounties(bot))