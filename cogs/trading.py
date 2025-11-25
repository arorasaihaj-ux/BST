import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
from datetime import datetime, timedelta

TICKET_CATEGORY_ID = int(os.getenv('TICKET_CATEGORY_ID', 0))

class TradingPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(
        label="Create Trade Ticket",
        style=discord.ButtonStyle.success,
        custom_id="create_trade_ticket",
    )
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            guild = interaction.guild
            category = guild.get_channel(TICKET_CATEGORY_ID)
            
            if not category:
                embed = discord.Embed(
                    description=f"Trading system not configured!\n\nCategory ID `{TICKET_CATEGORY_ID}` not found.",
                    color=0xED4245
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Check for existing ticket
            existing_ticket = None
            for channel in category.text_channels:
                if str(interaction.user.id) in channel.name:
                    existing_ticket = channel
                    break
            
            if existing_ticket:
                embed = discord.Embed(
                    description=f"You already have an active ticket: {existing_ticket.mention}",
                    color=0xED4245
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Create permissions
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    attach_files=True,
                    embed_links=True
                ),
                guild.me: discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    manage_channels=True,
                    manage_messages=True
                )
            }
            
            # Add admin/moderator access
            for role in guild.roles:
                if role.permissions.administrator or role.permissions.manage_channels:
                    overwrites[role] = discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=True
                    )
            
            # Create ticket channel
            channel = await category.create_text_channel(
                name=f"trade-{interaction.user.name}".lower(),
                overwrites=overwrites,
                topic=f"Trade Ticket | Creator: {interaction.user.display_name} ({interaction.user.id})"
            )
            
            # Create trade in database
            trade_id = await interaction.client.db.create_trade(
                interaction.user.id,
                channel.id
            )
            
            # Welcome message
            embed = discord.Embed(
                title="Secure BST Trade",
                description=f"Welcome {interaction.user.mention}!\n\nYour secure trading ticket has been created.",
                color=0x57F287
            )
            
            embed.add_field(
                name="How to Trade",
                value=(
                    "**1.** Click 'Add Partner' to invite your trading partner\n"
                    "**2.** Discuss and agree on BST amount\n"
                    "**3.** Click 'Add to Escrow' to secure your BST\n"
                    "**4.** Trading partner provides Roblox items\n"
                    "**5.** Click 'Release BST' to complete the trade"
                ),
                inline=False
            )
            
            embed.add_field(
                name="Security Features",
                value=(
                    "• BST held safely in escrow\n"
                    "• Admins can monitor trade\n"
                    "• Refund available if needed\n"
                    "• Auto-closes after 30min inactivity"
                ),
                inline=False
            )
            
            embed.set_footer(text=f"Trade ID: {trade_id}")
            
            view = TradeControls()
            await channel.send(content=interaction.user.mention, embed=embed, view=view)
            
            # Response
            response_embed = discord.Embed(
                description=f"Trade ticket created: {channel.mention}",
                color=0x57F287
            )
            await interaction.response.send_message(embed=response_embed, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                description=f"Failed to create ticket: {str(e)}",
                color=0xED4245
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

class TradeControls(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(
        label="Add Partner",
        style=discord.ButtonStyle.primary,
        custom_id="add_trade_partner"
    )
    async def add_partner(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = PartnerModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(
        label="Add to Escrow",
        style=discord.ButtonStyle.success,
        custom_id="add_to_escrow"
    )
    async def add_escrow(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EscrowModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(
        label="Release BST",
        style=discord.ButtonStyle.danger,
        custom_id="release_escrow_bst"
    )
    async def release_bst(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            trade = await interaction.client.db.get_trade_by_channel(interaction.channel.id)
            
            if not trade:
                await interaction.response.send_message("Trade not found!", ephemeral=True)
                return
            
            if interaction.user.id != trade['creator_id']:
                embed = discord.Embed(
                    description="Only the trade creator can release BST!",
                    color=0xED4245
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            if trade['escrow_amount'] <= 0:
                embed = discord.Embed(
                    description="No BST in escrow!",
                    color=0xED4245
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            if not trade['partner_id']:
                embed = discord.Embed(
                    description="Add a trading partner first!",
                    color=0xED4245
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            view = ConfirmRelease(trade)
            embed = discord.Embed(
                title="Confirm BST Release",
                description=f"Release **{trade['escrow_amount']:.2f} BST** to <@{trade['partner_id']}>?",
                color=0xFEE75C
            )
            
            embed.add_field(
                name="Warning",
                value="This action cannot be undone! Only confirm if you received the Roblox items.",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)
    
    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.secondary,
        custom_id="close_trade_ticket"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            trade = await interaction.client.db.get_trade_by_channel(interaction.channel.id)
            
            is_creator = trade and interaction.user.id == trade['creator_id']
            is_admin = interaction.user.guild_permissions.administrator
            
            if not (is_creator or is_admin):
                embed = discord.Embed(
                    description="Only the creator or admins can close this ticket!",
                    color=0xED4245
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Check escrow
            if trade and trade['escrow_amount'] > 0:
                view = CloseOptions()
                embed = discord.Embed(
                    title="BST in Escrow",
                    description=f"There is **{trade['escrow_amount']:.2f} BST** in escrow!",
                    color=0xFEE75C
                )
                embed.add_field(
                    name="Options",
                    value="• **Refund BST** — Return BST to sender\n• **Force Close** — Close without refund (Admin only)",
                    inline=False
                )
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                return
            
            # Close ticket
            embed = discord.Embed(
                description="Closing ticket in 5 seconds...",
                color=0xED4245
            )
            await interaction.response.send_message(embed=embed)
            
            import asyncio
            await asyncio.sleep(5)
            await interaction.channel.delete(reason="Trade ticket closed")
            
        except Exception as e:
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)

class PartnerModal(discord.ui.Modal, title="Add Trading Partner"):
    user_id = discord.ui.TextInput(
        label="Partner's User ID",
        placeholder="123456789012345678",
        required=True,
        max_length=20
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            partner_id = int(self.user_id.value)
            partner = interaction.guild.get_member(partner_id)
            
            if not partner:
                embed = discord.Embed(
                    description="User not found in this server!",
                    color=0xED4245
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Add permissions
            await interaction.channel.set_permissions(
                partner,
                read_messages=True,
                send_messages=True,
                attach_files=True
            )
            
            # Update database
            trade = await interaction.client.db.get_trade_by_channel(interaction.channel.id)
            if trade:
                await interaction.client.db.update_trade(
                    trade['trade_id'],
                    partner_id=partner_id,
                    status='active'
                )
            
            embed = discord.Embed(
                title="Partner Added",
                description=f"{partner.mention} has been added to this trade!",
                color=0x57F287
            )
            await interaction.response.send_message(embed=embed)
            
        except ValueError:
            embed = discord.Embed(
                description="Invalid User ID format!",
                color=0xED4245
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)

class EscrowModal(discord.ui.Modal, title="Add BST to Escrow"):
    amount = discord.ui.TextInput(
        label="BST Amount",
        placeholder="1.50",
        required=True,
        max_length=10
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = float(self.amount.value)
            
            if amount <= 0:
                embed = discord.Embed(
                    description="Amount must be positive!",
                    color=0xED4245
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            balance = await interaction.client.db.get_balance(interaction.user.id)
            
            if balance < amount:
                embed = discord.Embed(
                    description=f"Insufficient BST! You have **{balance:.2f} BST**",
                    color=0xED4245
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Remove BST
            success = await interaction.client.db.remove_bst(interaction.user.id, amount)
            
            if not success:
                embed = discord.Embed(
                    description="Failed to add BST to escrow!",
                    color=0xED4245
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Update trade
            trade = await interaction.client.db.get_trade_by_channel(interaction.channel.id)
            if trade:
                new_escrow = trade['escrow_amount'] + amount
                await interaction.client.db.update_trade(
                    trade['trade_id'],
                    escrow_amount=new_escrow
                )
            
            new_balance = await interaction.client.db.get_balance(interaction.user.id)
            
            embed = discord.Embed(
                title="BST Added to Escrow",
                description=f"**{amount:.2f} BST** is now securely held in escrow",
                color=0x57F287
            )
            
            embed.add_field(
                name="Your New Balance",
                value=f"{new_balance:.2f} BST",
                inline=True
            )
            
            embed.add_field(
                name="Total in Escrow",
                value=f"{new_escrow:.2f} BST",
                inline=True
            )
            
            embed.set_footer(text="BST will be released when you confirm the trade")
            
            await interaction.response.send_message(embed=embed)
            
        except ValueError:
            embed = discord.Embed(
                description="Invalid amount format!",
                color=0xED4245
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)

class ConfirmRelease(discord.ui.View):
    def __init__(self, trade):
        super().__init__(timeout=60)
        self.trade = trade
    
    @discord.ui.button(label="Confirm Release", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Transfer BST
            await interaction.client.db.add_bst(self.trade['partner_id'], self.trade['escrow_amount'])
            
            # Update trade
            await interaction.client.db.update_trade(
                self.trade['trade_id'],
                escrow_amount=0.0
            )
            await interaction.client.db.complete_trade(self.trade['trade_id'])
            
            partner = interaction.guild.get_member(self.trade['partner_id'])
            
            embed = discord.Embed(
                title="BST Released",
                description=f"**{self.trade['escrow_amount']:.2f} BST** sent to {partner.mention}!",
                color=0x57F287
            )
            
            embed.add_field(
                name="Trade Complete",
                value="Thank you for using secure trading!\n\nTicket closing in 10 seconds...",
                inline=False
            )
            
            await interaction.response.edit_message(embed=embed, view=None)
            await interaction.channel.send(embed=embed)
            
            import asyncio
            await asyncio.sleep(10)
            await interaction.channel.delete(reason="Trade completed")
            
        except Exception as e:
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            description="Release cancelled.",
            color=0xED4245
        )
        await interaction.response.edit_message(embed=embed, view=None)

class CloseOptions(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
    
    @discord.ui.button(label="Refund BST", style=discord.ButtonStyle.success)
    async def refund(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            trade = await interaction.client.db.get_trade_by_channel(interaction.channel.id)
            
            # Refund
            await interaction.client.db.add_bst(trade['creator_id'], trade['escrow_amount'])
            await interaction.client.db.update_trade(trade['trade_id'], escrow_amount=0.0)
            
            embed = discord.Embed(
                title="BST Refunded",
                description=f"**{trade['escrow_amount']:.2f} BST** has been refunded!",
                color=0x57F287
            )
            
            await interaction.response.edit_message(embed=embed, view=None)
            
            import asyncio
            await asyncio.sleep(5)
            await interaction.channel.delete(reason="Refunded and closed")
            
        except Exception as e:
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)
    
    @discord.ui.button(label="Force Close (Admin)", style=discord.ButtonStyle.danger)
    async def force_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Admin only!", ephemeral=True)
            return
        
        embed = discord.Embed(
            description="Force closing ticket...",
            color=0xED4245
        )
        await interaction.response.edit_message(embed=embed, view=None)
        
        import asyncio
        await asyncio.sleep(2)
        await interaction.channel.delete(reason="Force closed by admin")

class Trading(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(TradingPanel())
        self.bot.add_view(TradeControls())

    @app_commands.command(name="tradepanel", description="Setup the trading panel")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def tradepanel(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Administrator permission required.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="Secure BST Trading",
            description="Trade BST safely with our secure escrow system!",
            color=0x57F287
        )
        
        embed.add_field(
            name="How It Works",
            value=(
                "**1.** Click 'Create Trade Ticket' below\n"
                "**2.** Private ticket channel is created\n"
                "**3.** Invite your trading partner\n"
                "**4.** Add BST to secure escrow\n"
                "**5.** Complete trade and release BST"
            ),
            inline=False
        )
        
        embed.add_field(
            name="Security Features",
            value=(
                "• BST held in secure escrow\n"
                "• Admin monitoring and oversight\n"
                "• Refund protection available\n"
                "• Activity tracking system"
            ),
            inline=False
        )
        
        embed.set_footer(text="Only trade with trusted partners!")
        
        await interaction.channel.send(embed=embed, view=TradingPanel())
        await interaction.response.send_message("Trading panel created successfully!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Trading(bot))
