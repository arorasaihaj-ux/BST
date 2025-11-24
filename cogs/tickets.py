import discord
from discord.ext import commands
import config
from database import db

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.escrow = {}  # ticket_number: {'user1_id': amount, 'confirmed': False}
    
    @commands.hybrid_command(name="setup_ticket_panel", description="Setup ticket panel (Admin only)")
    async def setup_ticket_panel(self, ctx):
        """Create the ticket panel"""
        if ctx.author.id != config.OWNER_ID:
            return
        
        embed = discord.Embed(color=config.Colors.PRIMARY)
        
        header = config.Design.header("TRADE DEALS", 28)
        
        content = (
            f"```\n{header}\n```\n"
            f"Create a secure trade ticket.\n"
            f"Trade BST points and items safely.\n\n"
            f"{config.Design.divider(28)}\n\n"
            f"{config.Design.small_caps('how it works')}\n\n"
            f"{config.Design.item('Click Start a Deal')}\n"
            f"{config.Design.item('Invite trade partner')}\n"
            f"{config.Design.item('Make offers')}\n"
            f"{config.Design.item('Both confirm')}\n"
            f"{config.Design.item('Release when done')}\n"
        )
        
        embed.description = content
        
        view = discord.ui.View(timeout=None)
        button = discord.ui.Button(
            label="🎫 Start a Deal",
            style=discord.ButtonStyle.green,
            custom_id="create_ticket"
        )
        
        async def button_callback(interaction: discord.Interaction):
            await self.create_ticket(interaction)
        
        button.callback = button_callback
        view.add_item(button)
        
        await ctx.send(embed=embed, view=view)
    
    async def create_ticket(self, interaction: discord.Interaction):
        """Create a new ticket channel"""
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        category = guild.get_channel(config.TICKET_CATEGORY_ID)
        
        if not category:
            await interaction.followup.send("Ticket category not found!", ephemeral=True)
            return
        
        # Create ticket in database
        ticket_number = await db.create_ticket(interaction.user.id, 0)
        
        # Create private channel
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        channel = await guild.create_text_channel(
            name=f"ticket-{ticket_number}",
            category=category,
            overwrites=overwrites
        )
        
        # Update ticket with channel ID
        async with db.pool.acquire() as conn:
            await conn.execute(
                "UPDATE tickets SET channel_id = $1 WHERE ticket_number = $2",
                channel.id, ticket_number
            )
        
        # Send initial ticket message
        embed = discord.Embed(color=config.Colors.YELLOW)
        
        header = config.Design.header(f"TICKET #{ticket_number}", 28)
        
        content = (
            f"```\n{header}\n```\n"
            f"{config.Design.field('creator', 'User 1', 20)}\n"
            f"{config.Design.field('status', 'waiting for partner', 20)}\n\n"
            f"{config.Design.divider(28)}\n\n"
            f"Type @username to invite your trade partner.\n"
        )
        
        embed.description = content
        
        view = discord.ui.View(timeout=None)
        cancel_btn = discord.ui.Button(
            label="❌ Cancel Ticket",
            style=discord.ButtonStyle.red,
            custom_id=f"cancel_{ticket_number}"
        )
        
        async def cancel_callback(inter: discord.Interaction):
            await channel.delete()
        
        cancel_btn.callback = cancel_callback
        view.add_item(cancel_btn)
        
        await channel.send(f"{interaction.user.mention}", embed=embed, view=view)
        await interaction.followup.send(f"Ticket created: {channel.mention}", ephemeral=True)
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for partner mentions in tickets"""
        if message.author.bot:
            return
        
        # Check if in ticket channel
        if not message.channel.name.startswith('ticket-'):
            return
        
        ticket = await db.get_ticket_by_channel(message.channel.id)
        if not ticket or ticket['status'] != 'pending':
            return
        
        # Check if mentioning a user
        if len(message.mentions) != 1:
            return
        
        partner = message.mentions[0]
        if partner.bot or partner.id == message.author.id:
            await message.channel.send("Invalid user!")
            return
        
        # Add partner to ticket
        await db.add_partner_to_ticket(ticket['ticket_number'], partner.id)
        
        # Give partner access
        await message.channel.set_permissions(partner, read_messages=True, send_messages=True)
        
        # Send deal summary
        embed = discord.Embed(color=config.Colors.INFO)
        
        header = config.Design.header("DEAL SUMMARY", 28)
        
        content = (
            f"```\n{header}\n```\n"
            f"{config.Design.small_caps('participants')}\n\n"
            f"{config.Design.item('User 1')}\n"
            f"{config.Design.item('User 2')}\n\n"
            f"{config.Design.divider(28)}\n\n"
            f"{config.Design.bold('USER 1 OFFERS')}\n"
            f"{config.Design.field('bst points', '0.00', 20)}\n\n"
            f"{config.Design.bold('USER 2 OFFERS')}\n"
            f"{config.Design.field('bst points', '0.00', 20)}\n"
        )
        
        embed.description = content
        
        view = TicketControlView(ticket['ticket_number'], self)
        
        await message.channel.send(f"{partner.mention}", embed=embed, view=view)

class TicketControlView(discord.ui.View):
    def __init__(self, ticket_number: int, cog):
        super().__init__(timeout=None)
        self.ticket_number = ticket_number
        self.cog = cog
        self.offers = {'user1': 0, 'user2': 0}
        self.confirmed = {'user1': False, 'user2': False}
    
    @discord.ui.button(label="💰 Add BST", style=discord.ButtonStyle.primary)
    async def add_bst(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Add BST to offer"""
        modal = BSTModal(self.ticket_number)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.green)
    async def confirm_deal(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm role in deal"""
        await interaction.response.defer()
        
        # Show role selection
        embed = discord.Embed(color=config.Colors.WARNING)
        
        header = config.Design.header("CONFIRM ROLES", 28)
        
        content = (
            f"```\n{header}\n```\n"
            f"{config.Design.field('sender', 'User 1', 20)}\n"
            f"{config.Design.field('receiver', 'User 2', 20)}\n\n"
            f"Select your role in this deal.\n"
        )
        
        embed.description = content
        
        view = RoleConfirmView(self.ticket_number, self.cog)
        
        await interaction.followup.send(embed=embed, view=view)
    
    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
    async def cancel_deal(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel the deal"""
        await interaction.response.defer()
        await interaction.channel.delete()

class BSTModal(discord.ui.Modal, title="Add BST to Offer"):
    def __init__(self, ticket_number: int):
        super().__init__()
        self.ticket_number = ticket_number
    
    amount = discord.ui.TextInput(
        label="BST Amount",
        placeholder="Enter amount",
        required=True,
        max_length=10
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            bst_amount = float(self.amount.value)
            if bst_amount <= 0:
                raise ValueError()
        except:
            await interaction.response.send_message("Invalid amount!", ephemeral=True)
            return
        
        balance = await db.get_balance(interaction.user.id)
        if balance < bst_amount:
            await interaction.response.send_message("Insufficient balance!", ephemeral=True)
            return
        
        await interaction.response.send_message(f"Added {bst_amount:.2f} BST to your offer!", ephemeral=True)

class RoleConfirmView(discord.ui.View):
    def __init__(self, ticket_number: int, cog):
        super().__init__(timeout=30)
        self.ticket_number = ticket_number
        self.cog = cog
    
    @discord.ui.button(label="Sending", style=discord.ButtonStyle.primary)
    async def sending(self, interaction: discord.Interaction, button: discord.ui.Button):
        """User is sending BST"""
        await interaction.response.send_message("You are the sender!", ephemeral=True)
        self.stop()
    
    @discord.ui.button(label="Receiving", style=discord.ButtonStyle.primary)
    async def receiving(self, interaction: discord.Interaction, button: discord.ui.Button):
        """User is receiving BST"""
        await interaction.response.send_message("You are the receiver!", ephemeral=True)
        self.stop()

async def setup(bot):
    await bot.add_cog(Tickets(bot))