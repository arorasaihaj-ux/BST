\import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
from datetime import datetime, timedelta

TICKET_CATEGORY_ID = int(os.getenv('TICKET_CATEGORY_ID', 0))

class TradingPanel(discord.ui.View):
    """Persistent view for starting trades"""
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(
        label="Start Secure Trade",
        style=discord.ButtonStyle.success,
        custom_id="start_trade_button",
        emoji="🛡️"
    )
    async def start_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Create a new trade ticket"""
        try:
            guild = interaction.guild
            category = guild.get_channel(TICKET_CATEGORY_ID)
            
            if not category:
                await interaction.response.send_message(
                    "❌ Trading system not configured!",
                    ephemeral=True
                )
                return
            
            # Check if user already has an active ticket
            for channel in category.text_channels:
                if str(interaction.user.id) in channel.name:
                    await interaction.response.send_message(
                        f"❌ You already have an active trade ticket: {channel.mention}",
                        ephemeral=True
                    )
                    return
            
            # Create ticket channel
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True
                ),
                guild.me: discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    manage_channels=True
                )
            }
            
            # Add admin access
            for role in guild.roles:
                if role.permissions.administrator:
                    overwrites[role] = discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=True
                    )
            
            channel = await category.create_text_channel(
                name=f"trade-{interaction.user.name}-{interaction.user.id}",
                overwrites=overwrites,
                topic=f"Secure BST Trade - Creator: {interaction.user.display_name}"
            )
            
            # Create trade in database
            trade_id = await interaction.client.db.create_trade(
                interaction.user.id,
                channel.id
            )
            
            # Send welcome message
            embed = discord.Embed(
                title="🛡️ Secure BST Trade",
                description=f"Welcome {interaction.user.mention}!\n\nThis is your secure trading ticket.",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="📋 How It Works",
                value=(
                    "**Step 1:** Invite your trading partner\n"
                    "**Step 2:** Agree on BST amount\n"
                    "**Step 3:** Sender adds BST to escrow\n"
                    "**Step 4:** Receiver provides Roblox items\n"
                    "**Step 5:** Sender confirms & releases BST\n"
                ),
                inline=False
            )
            
            embed.add_field(
                name="⚠️ Important",
                value=(
                    "• Admins can see this channel\n"
                    "• Ticket auto-closes after 30 min of inactivity\n"
                    "• Use buttons below to manage trade\n"
                ),
                inline=False
            )
            
            embed.set_footer(text=f"Trade ID: {trade_id}")
            
            view = TradeControlView()
            await channel.send(embed=embed, view=view)
            
            await interaction.response.send_message(
                f"✅ Trade ticket created: {channel.mention}",
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )

class TradeControlView(discord.ui.View):
    """Control panel for managing trades"""
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(
        label="Add Partner",
        style=discord.ButtonStyle.primary,
        custom_id="add_partner_button",
        emoji="👥"
    )
    async def add_partner(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Add trading partner to ticket"""
        modal = AddPartnerModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(
        label="Add BST to Escrow",
        style=discord.ButtonStyle.success,
        custom_id="add_escrow_button",
        emoji="💰"
    )
    async def add_escrow(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Add BST to secure escrow"""
        modal = AddEscrowModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(
        label="Release BST",
        style=discord.ButtonStyle.danger,
        custom_id="release_bst_button",
        emoji="✅"
    )
    async def release_bst(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Release BST from escrow"""
        try:
            # Get trade info
            trade = await interaction.client.db.get_trade_by_channel(interaction.channel.id)
            
            if not trade:
                await interaction.response.send_message(
                    "❌ Trade not found!",
                    ephemeral=True
                )
                return
            
            # Check if user is creator
            if interaction.user.id != trade['creator_id']:
                await interaction.response.send_message(
                    "❌ Only the trade creator can release BST!",
                    ephemeral=True
                )
                return
            
            # Check if there's BST in escrow
            if trade['escrow_amount'] <= 0:
                await interaction.response.send_message(
                    "❌ No BST in escrow!",
                    ephemeral=True
                )
                return
            
            # Check if partner exists
            if not trade['partner_id']:
                await interaction.response.send_message(
                    "❌ Add a trading partner first!",
                    ephemeral=True
                )
                return
            
            # Confirmation modal
            view = ConfirmReleaseView(trade)
            
            embed = discord.Embed(
                title="⚠️ Confirm BST Release",
                description=f"Are you sure you want to release **{trade['escrow_amount']:.2f} BST** to <@{trade['partner_id']}>?",
                color=discord.Color.orange()
            )
            
            embed.add_field(
                name="⚠️ Warning",
                value="**This action cannot be undone!**\n\nOnly confirm if you have received the Roblox items.",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )
    
    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.secondary,
        custom_id="close_ticket_button",
        emoji="🔒"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Close the trade ticket"""
        try:
            # Get trade info
            trade = await interaction.client.db.get_trade_by_channel(interaction.channel.id)
            
            # Check if user is creator or admin
            is_creator = trade and interaction.user.id == trade['creator_id']
            is_admin = interaction.user.guild_permissions.administrator
            
            if not (is_creator or is_admin):
                await interaction.response.send_message(
                    "❌ Only the trade creator or admins can close this ticket!",
                    ephemeral=True
                )
                return
            
            # Check if there's BST in escrow
            if trade and trade['escrow_amount'] > 0:
                view = ForceCloseView()
                
                embed = discord.Embed(
                    title="⚠️ BST in Escrow!",
                    description=f"There is **{trade['escrow_amount']:.2f} BST** in escrow!",
                    color=discord.Color.red()
                )
                
                embed.add_field(
                    name="Options",
                    value="**Refund BST** - Return BST to sender\n**Force Close** - Close without refund (Admin only)",
                    inline=False
                )
                
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                return
            
            # Close ticket
            embed = discord.Embed(
                title="🔒 Closing Ticket",
                description="This channel will be deleted in 5 seconds...",
                color=discord.Color.red()
            )
            
            await interaction.response.send_message(embed=embed)
            
            import asyncio
            await asyncio.sleep(5)
            await interaction.channel.delete()
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )

class AddPartnerModal(discord.ui.Modal, title="Add Trading Partner"):
    partner_id = discord.ui.TextInput(
        label="Partner's User ID",
        placeholder="123456789012345678",
        required=True,
        max_length=20
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            partner_id = int(self.partner_id.value)
            
            # Get user
            partner = interaction.guild.get_member(partner_id)
            if not partner:
                await interaction.response.send_message(
                    "❌ User not found in this server!",
                    ephemeral=True
                )
                return
            
            # Add to channel
            await interaction.channel.set_permissions(
                partner,
                read_messages=True,
                send_messages=True
            )
            
            # Update trade
            trade = await interaction.client.db.get_trade_by_channel(interaction.channel.id)
            if trade:
                await interaction.client.db.update_trade(
                    trade['trade_id'],
                    partner_id=partner_id,
                    status='active'
                )
            
            embed = discord.Embed(
                title="✅ Partner Added",
                description=f"{partner.mention} has been added to the trade!",
                color=discord.Color.green()
            )
            
            await interaction.response.send_message(embed=embed)
            
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid User ID!",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )

class AddEscrowModal(discord.ui.Modal, title="Add BST to Escrow"):
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
                await interaction.response.send_message(
                    "❌ Amount must be positive!",
                    ephemeral=True
                )
                return
            
            # Check balance
            balance = await interaction.client.db.get_balance(interaction.user.id)
            
            if balance < amount:
                await interaction.response.send_message(
                    f"❌ Insufficient BST! You have **{balance:.2f} BST**",
                    ephemeral=True
                )
                return
            
            # Remove BST from user
            success = await interaction.client.db.remove_bst(interaction.user.id, amount)
            
            if not success:
                await interaction.response.send_message(
                    "❌ Failed to add BST to escrow!",
                    ephemeral=True
                )
                return
            
            # Update trade
            trade = await interaction.client.db.get_trade_by_channel(interaction.channel.id)
            if trade:
                new_escrow = trade['escrow_amount'] + amount
                await interaction.client.db.update_trade(
                    trade['trade_id'],
                    escrow_amount=new_escrow
                )
            
            # Get new balance
            new_balance = await interaction.client.db.get_balance(interaction.user.id)
            
            embed = discord.Embed(
                title="✅ BST Added to Escrow",
                description=f"**{amount:.2f} BST** is now held securely in escrow!",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="💰 Your New Balance",
                value=f"**{new_balance:.2f} BST**",
                inline=True
            )
            
            embed.add_field(
                name="🛡️ Total in Escrow",
                value=f"**{new_escrow:.2f} BST**",
                inline=True
            )
            
            embed.set_footer(text="BST will be released when you confirm the trade")
            
            await interaction.response.send_message(embed=embed)
            
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid amount!",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )

class ConfirmReleaseView(discord.ui.View):
    def __init__(self, trade):
        super().__init__(timeout=60)
        self.trade = trade
    
    @discord.ui.button(label="Confirm Release", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Transfer BST to partner
            await interaction.client.db.add_bst(self.trade['partner_id'], self.trade['escrow_amount'])
            
            # Update trade
            await interaction.client.db.update_trade(
                self.trade['trade_id'],
                escrow_amount=0.0
            )
            await interaction.client.db.complete_trade(self.trade['trade_id'])
            
            # Send confirmation
            partner = interaction.guild.get_member(self.trade['partner_id'])
            
            embed = discord.Embed(
                title="✅ BST Released!",
                description=f"**{self.trade['escrow_amount']:.2f} BST** has been sent to {partner.mention}!",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="🎉 Trade Complete",
                value="Thank you for using Secure Trading!\n\nThis ticket will close in 10 seconds.",
                inline=False
            )
            
            await interaction.response.edit_message(embed=embed, view=None)
            await interaction.channel.send(embed=embed)
            
            # Auto-close
            import asyncio
            await asyncio.sleep(10)
            await interaction.channel.delete()
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Release cancelled.", embed=None, view=None)

class ForceCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
    
    @discord.ui.button(label="Refund BST", style=discord.ButtonStyle.success, emoji="💰")
    async def refund(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            trade = await interaction.client.db.get_trade_by_channel(interaction.channel.id)
            
            # Refund BST
            await interaction.client.db.add_bst(trade['creator_id'], trade['escrow_amount'])
            
            # Update trade
            await interaction.client.db.update_trade(trade['trade_id'], escrow_amount=0.0)
            
            embed = discord.Embed(
                title="💰 BST Refunded",
                description=f"**{trade['escrow_amount']:.2f} BST** has been refunded!",
                color=discord.Color.green()
            )
            
            await interaction.response.edit_message(embed=embed, view=None)
            
            # Close ticket
            import asyncio
            await asyncio.sleep(5)
            await interaction.channel.delete()
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )
    
    @discord.ui.button(label="Force Close (Admin)", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def force_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Admin only!",
                ephemeral=True
            )
            return
        
        await interaction.response.edit_message(content="🔒 Closing...", embed=None, view=None)
        
        import asyncio
        await asyncio.sleep(2)
        await interaction.channel.delete()

class Trading(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cleanup_inactive.start()

    def cog_unload(self):
        self.cleanup_inactive.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        """Register persistent views"""
        self.bot.add_view(TradingPanel())
        self.bot.add_view(AddPartnerView())
        self.bot.add_view(RoleSelectionView())
        self.bot.add_view(ConfirmRolesView())
        self.bot.add_view(AmountInputView())
        self.bot.add_view(ConfirmAmountView())
        self.bot.add_view(ReleaseView())

    @app_commands.command(name="tradepanel", description="Setup trading panel (Admin)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def tradepanel(self, interaction: discord.Interaction):
        """Setup trading panel"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need Administrator permissions!",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="💱 BST CURRENCY MIDDLEMAN",
            description=(
                "Welcome to our automated BST currency middleman!\n\n"
                "Your currency will be held by our bot during this deal for a secured trade!\n\n"
                "**How It Works:**\n"
                "1️⃣ Click 'Create Trade Ticket'\n"
                "2️⃣ Add your trading partner\n"
                "3️⃣ Select roles (Sender/Receiver)\n"
                "4️⃣ Set BST amount\n"
                "5️⃣ Bot holds BST in escrow\n"
                "6️⃣ Complete external trade\n"
                "7️⃣ Sender releases BST\n\n"
                "**⚠️ Please notify support in case of any emergency or assistance.**"
            ),
            color=0x5865F2
        )
        
        embed.set_footer(text="Trade safely with automated escrow protection!")
        
        await interaction.channel.send(embed=embed, view=TradingPanel())
        
        await interaction.response.send_message(
            "✅ Trading panel created!",
            ephemeral=True
        )

    @tasks.loop(minutes=5)
    async def cleanup_inactive(self):
        """Close inactive trade tickets after 30 minutes"""
        try:
            inactive_trades = await self.bot.db.get_inactive_trades(30)
            
            for trade in inactive_trades:
                try:
                    channel = self.bot.get_channel(trade['channel_id'])
                    if not channel:
                        continue
                    
                    # Refund if BST held
                    if trade['escrow_amount'] > 0:
                        await self.bot.db.cancel_trade(trade['trade_id'], refund=True)
                        
                        sender = self.bot.get_user(trade['sender_id'])
                        
                        embed = discord.Embed(
                            title="⏰ Trade Ticket Auto-Closed",
                            description=(
                                "This ticket has been inactive for 30 minutes.\n\n"
                                f"**{trade['escrow_amount']:.2f} BST** has been refunded to {sender.mention if sender else 'sender'}.\n\n"
                                "Closing in 10 seconds..."
                            ),
                            color=0xFEE75C
                        )
                        await channel.send(embed=embed)
                    else:
                        await self.bot.db.cancel_trade(trade['trade_id'], refund=False)
                        
                        embed = discord.Embed(
                            description="⏰ This ticket has been inactive for 30 minutes and will now close.",
                            color=0xFEE75C
                        )
                        await channel.send(embed=embed)
                    
                    import asyncio
                    await asyncio.sleep(10)
                    await channel.delete(reason="Inactive for 30 minutes")
                    
                except Exception as e:
                    print(f"Error closing inactive trade {trade['trade_id']}: {e}")
                    
        except Exception as e:
            print(f"Error in cleanup_inactive: {e}")

    @cleanup_inactive.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Trading(bot))
