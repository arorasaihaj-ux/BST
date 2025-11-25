import discord
from discord.ext import commands
from discord import app_commands
import config
from database import db

class Gifts(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="gift", description="Gift BST to another user")
    async def gift_bst(self, interaction: discord.Interaction, user: discord.Member, amount: float):
        """Gift BST to another user"""
        try:
            if user.bot:
                await interaction.response.send_message(
                    "You cannot gift to bots.",
                    ephemeral=True
                )
                return
            
            if user.id == interaction.user.id:
                await interaction.response.send_message(
                    "You cannot gift to yourself.",
                    ephemeral=True
                )
                return
            
            if amount <= 0:
                await interaction.response.send_message(
                    "Amount must be positive.",
                    ephemeral=True
                )
                return
            
            # Send gift
            success = await db.send_gift(interaction.user.id, user.id, amount=amount)
            
            if success:
                embed = discord.Embed(
                    description=config.Design.small_caps(
                        f"gifted {amount:.2f} bst to {user.display_name}"
                    ),
                    color=config.Colors.SUCCESS
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
                # Notify recipient
                recipient_embed = discord.Embed(
                    description=config.Design.small_caps(
                        f"received {amount:.2f} bst gift from {interaction.user.display_name}"
                    ),
                    color=config.Colors.SUCCESS
                )
                
                try:
                    await user.send(embed=recipient_embed)
                except:
                    pass  # Can't DM, that's okay
            else:
                await interaction.response.send_message(
                    "Insufficient BST or error sending gift.",
                    ephemeral=True
                )
                
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="giftitem", description="Gift an item to another user")
    async def gift_item(self, interaction: discord.Interaction, user: discord.Member, item_name: str):
        """Gift an item to another user"""
        try:
            if user.bot:
                await interaction.response.send_message(
                    "You cannot gift to bots.",
                    ephemeral=True
                )
                return
            
            if user.id == interaction.user.id:
                await interaction.response.send_message(
                    "You cannot gift to yourself.",
                    ephemeral=True
                )
                return
            
            # Get item ID from name
            async with db.pool.acquire() as conn:
                item = await conn.fetchrow("""
                    SELECT item_id FROM items WHERE name = $1
                """, item_name)
                
                if not item:
                    await interaction.response.send_message(
                        "Item not found.",
                        ephemeral=True
                    )
                    return
            
            # Send gift
            success = await db.send_gift(interaction.user.id, user.id, item_id=item['item_id'])
            
            if success:
                embed = discord.Embed(
                    description=config.Design.small_caps(
                        f"gifted {item_name} to {user.display_name}"
                    ),
                    color=config.Colors.SUCCESS
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
                # Notify recipient
                recipient_embed = discord.Embed(
                    description=config.Design.small_caps(
                        f"received {item_name} gift from {interaction.user.display_name}"
                    ),
                    color=config.Colors.SUCCESS
                )
                
                try:
                    await user.send(embed=recipient_embed)
                except:
                    pass  # Can't DM, that's okay
            else:
                await interaction.response.send_message(
                    "You don't have this item or error sending gift.",
                    ephemeral=True
                )
                
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="gifthistory", description="View your gift history")
    async def gift_history(self, interaction: discord.Interaction):
        """View gift history"""
        try:
            async with db.pool.acquire() as conn:
                sent_gifts = await conn.fetch("""
                    SELECT * FROM gifts 
                    WHERE from_user_id = $1 
                    ORDER BY created_at DESC 
                    LIMIT 10
                """, interaction.user.id)
                
                received_gifts = await conn.fetch("""
                    SELECT * FROM gifts 
                    WHERE to_user_id = $1 
                    ORDER BY created_at DESC 
                    LIMIT 10
                """, interaction.user.id)
            
            embed = discord.Embed(color=config.Colors.PRIMARY)
            
            header = config.Design.header("GIFT HISTORY", 28)
            embed.description = f"\n{header}\n"
            
            # Sent gifts
            sent_content = ""
            for gift in sent_gifts:
                recipient = self.bot.get_user(gift['to_user_id'])
                recipient_name = recipient.display_name if recipient else f"User {gift['to_user_id']}"
                
                if gift['amount_bst'] > 0:
                    sent_content += f"To {recipient_name}: {gift['amount_bst']:.2f} BST\n"
                elif gift['item_id']:
                    item = await conn.fetchrow("SELECT name FROM items WHERE item_id = $1", gift['item_id'])
                    item_name = item['name'] if item else "Unknown Item"
                    sent_content += f"To {recipient_name}: {item_name}\n"
            
            # Received gifts
            received_content = ""
            for gift in received_gifts:
                sender = self.bot.get_user(gift['from_user_id'])
                sender_name = sender.display_name if sender else f"User {gift['from_user_id']}"
                
                if gift['amount_bst'] > 0:
                    received_content += f"From {sender_name}: {gift['amount_bst']:.2f} BST\n"
                elif gift['item_id']:
                    item = await conn.fetchrow("SELECT name FROM items WHERE item_id = $1", gift['item_id'])
                    item_name = item['name'] if item else "Unknown Item"
                    received_content += f"From {sender_name}: {item_name}\n"
            
            if sent_content:
                embed.add_field(name="Sent Gifts", value=sent_content or "None", inline=False)
            if received_content:
                embed.add_field(name="Received Gifts", value=received_content or "None", inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Gifts(bot))