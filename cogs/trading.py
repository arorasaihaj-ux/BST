import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import asyncio

TICKET_CATEGORY_ID = int(os.getenv('TICKET_CATEGORY_ID', 0))

class TradingPanel(discord.ui.View):
    """Main panel for creating trade tickets"""
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(
        label="Create Trade Ticket",
        style=discord.ButtonStyle.success,
        custom_id="create_trade_ticket_btn",
        emoji="🎫"
    )
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            guild = interaction.guild
            category = guild.get_channel(TICKET_CATEGORY_ID)
            
            if not category:
                await interaction.response.send_message(
                    "❌ Trading system not configured! Contact admin.",
                    ephemeral=True
                )
                return
            
            # FIXED: Check database for active trades instead of channel names
            # This prevents issues with deleted channels
            existing_trades = await interaction.client.db.get_user_active_trades(interaction.user.id)
            
            if existing_trades:
                # User has an active trade, check if channel still exists
                channel_still_exists = False
                for trade in existing_trades:
                    channel = guild.get_channel(trade['channel_id'])
                    if channel:
                        channel_still_exists = True
                        await interaction.response.send_message(
                            f"❌ You already have an active ticket: {channel.mention}",
                            ephemeral=True
                        )
                        return
                
                # If channel doesn't exist, cancel old trades
                if not channel_still_exists:
                    for trade in existing_trades:
                        await interaction.client.db.cancel_trade(trade['trade_id'], refund=True)
            
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
            
            # Add admin permissions
            for role in guild.roles:
                if role.permissions.administrator:
                    overwrites[role] = discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=True
                    )
            
            # Create channel
            channel = await category.create_text_channel(
                name=f"trade-{interaction.user.name}-{interaction.user.id}",
                overwrites=overwrites,
                topic=f"Secure BST Trade | Creator: {interaction.user.id}"
            )
            
            # Create trade in database
            trade_id = await interaction.client.db.create_trade(
                interaction.user.id,
                channel.id
            )
            
            # Welcome embed with ping
            welcome_embed = discord.Embed(
                title="💱 BST CURRENCY MIDDLEMAN",
                description=(
                    f"{interaction.user.mention}\n\n"
                    "Welcome to our automated BST currency middleman!\n\n"
                    "Your currency will be held by our bot during this deal for a secured trade!\n\n"
                    "**⚠️ Please notify support in case of any emergency or assistance.**"
                ),
                color=0x5865F2
            )
            
            await channel.send(content=interaction.user.mention, embed=welcome_embed)
            
            # Step 1: Add partner
            step1_embed = discord.Embed(
                title="🔒 Step 1: Add Trading Partner",
                description=(
                    "Please click the button below and **paste the User ID** of the person you want to trade with.\n\n"
                    "**How to get User ID:**\n"
                    "• Enable Developer Mode in Discord Settings\n"
                    "• Right-click their profile → Copy User ID\n\n"
                    "**⚠️ Contact support in case of emergency**"
                ),
                color=0x5865F2
            )
            
            await channel.send(embed=step1_embed, view=AddPartnerView())
            
            # Respond to interaction
            await interaction.response.send_message(
                f"✅ Trade ticket created: {channel.mention}",
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error creating ticket: {str(e)}",
                ephemeral=True
            )

class AddPartnerView(discord.ui.View):
    """View for adding trading partner"""
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(
        label="Add Trading Partner",
        style=discord.ButtonStyle.primary,
        custom_id="add_partner_modal_btn",
        emoji="👥"
    )
    async def add_partner(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AddPartnerModal()
        await interaction.response.send_modal(modal)

class AddPartnerModal(discord.ui.Modal, title="Add Trading Partner"):
    user_id_input = discord.ui.TextInput(
        label="Partner's User ID",
        placeholder="123456789012345678",
        required=True,
        max_length=20
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            partner_id = int(self.user_id_input.value)
            guild = interaction.guild
            
            # Get partner
            partner = guild.get_member(partner_id)
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
                send_messages=True,
                attach_files=True,
                embed_links=True
            )
            
            # Update database
            trade = await interaction.client.db.get_trade_by_channel(interaction.channel.id)
            if trade:
                await interaction.client.db.update_trade_partner(trade['trade_id'], partner_id)
            
            # Confirmation
            confirm_embed = discord.Embed(
                title="✅ Partner Added",
                description=f"{partner.mention} has been added to this trade ticket!",
                color=0x57F287
            )
            
            await interaction.response.send_message(embed=confirm_embed)
            
            # Step 2: Role selection
            await asyncio.sleep(1)
            
            role_embed = discord.Embed(
                title="📋 Step 2: Role Assignment",
                description=(
                    "Please select the option corresponding to your role in this deal.\n\n"
                    "**Once selected, both users must confirm to proceed.**\n\n"
                    "**Roles:**\n"
                    "• **Sending BST** → You will send BST currency\n"
                    "• **Receiving BST** → You will receive BST currency\n\n"
                    "**⚠️ Selecting the wrong role will result in getting scammed!**\n"
                    "**⚠️ Contact support in case of emergency**"
                ),
                color=0x5865F2
            )
            
            await interaction.channel.send(embed=role_embed, view=RoleSelectionView())
            
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid User ID format!",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )

class RoleSelectionView(discord.ui.View):
    """View for selecting sender/receiver roles"""
    def __init__(self):
        super().__init__(timeout=None)
        self.sender_id = None
        self.receiver_id = None
    
    @discord.ui.button(
        label="Sending BST",
        style=discord.ButtonStyle.success,
        custom_id="role_sender_btn",
        emoji="💸"
    )
    async def sender_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.sender_id:
            await interaction.response.send_message(
                "❌ Sender role already taken!",
                ephemeral=True
            )
            return
        
        self.sender_id = interaction.user.id
        
        await interaction.response.send_message(
            f"✅ {interaction.user.mention} selected **Sending BST** role",
            ephemeral=False
        )
        
        # Check if both roles selected
        if self.sender_id and self.receiver_id:
            await self.show_confirmation(interaction.channel, interaction.client.db)
    
    @discord.ui.button(
        label="Receiving BST",
        style=discord.ButtonStyle.primary,
        custom_id="role_receiver_btn",
        emoji="💰"
    )
    async def receiver_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.receiver_id:
            await interaction.response.send_message(
                "❌ Receiver role already taken!",
                ephemeral=True
            )
            return
        
        self.receiver_id = interaction.user.id
        
        await interaction.response.send_message(
            f"✅ {interaction.user.mention} selected **Receiving BST** role",
            ephemeral=False
        )
        
        # Check if both roles selected
        if self.sender_id and self.receiver_id:
            await self.show_confirmation(interaction.channel, interaction.client.db)
    
    @discord.ui.button(
        label="Reset",
        style=discord.ButtonStyle.danger,
        custom_id="role_reset_btn",
        emoji="🔄"
    )
    async def reset_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.sender_id = None
        self.receiver_id = None
        
        await interaction.response.send_message(
            "🔄 Roles have been reset. Please select again.",
            ephemeral=False
        )
    
    async def show_confirmation(self, channel, db):
        """Show role confirmation panel"""
        trade = await db.get_trade_by_channel(channel.id)
        if not trade:
            return
        
        # Update trade with roles
        await db.set_trade_roles(trade['trade_id'], self.sender_id, self.receiver_id)
        
        confirm_embed = discord.Embed(
            title="✅ Confirm Roles",
            description=(
                f"**Sender:** <@{self.sender_id}>\n"
                f"**Receiver:** <@{self.receiver_id}>\n\n"
                "**⚠️ Selecting the wrong role will result in getting scammed!**\n\n"
                "Both users must click **Correct** to proceed.\n"
                "**⚠️ Contact support in case of emergency**"
            ),
            color=0xFEE75C
        )
        
        await channel.send(embed=confirm_embed, view=ConfirmRolesView(self.sender_id, self.receiver_id))

class ConfirmRolesView(discord.ui.View):
    """View for confirming roles"""
    def __init__(self, sender_id, receiver_id):
        super().__init__(timeout=None)
        self.sender_id = sender_id
        self.receiver_id = receiver_id
        self.confirmed_users = set()
    
    @discord.ui.button(
        label="Correct",
        style=discord.ButtonStyle.success,
        custom_id="confirm_roles_correct_btn",
        emoji="✅"
    )
    async def correct(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        
        if user_id not in [self.sender_id, self.receiver_id]:
            await interaction.response.send_message(
                "❌ You are not part of this trade!",
                ephemeral=True
            )
            return
        
        if user_id in self.confirmed_users:
            await interaction.response.send_message(
                "✅ You already confirmed!",
                ephemeral=True
            )
            return
        
        self.confirmed_users.add(user_id)
        
        await interaction.response.send_message(
            f"✅ {interaction.user.mention} confirmed the roles",
            ephemeral=False
        )
        
        # Check if both confirmed
        if len(self.confirmed_users) == 2:
            # Update database
            trade = await interaction.client.db.get_trade_by_channel(interaction.channel.id)
            if trade:
                await interaction.client.db.confirm_role(trade['trade_id'], self.sender_id, True)
                await interaction.client.db.confirm_role(trade['trade_id'], self.receiver_id, False)
            
            # Move to amount step
            await asyncio.sleep(1)
            
            amount_embed = discord.Embed(
                title="💰 Step 3: Deal Amount",
                description=(
                    f"<@{self.sender_id}>\n\n"
                    "Please state the amount the bot is expected to receive in USD (e.g. 100.59)\n\n"
                    "**Click the button below to enter the BST amount.**\n\n"
                    "**⚠️ Contact support in case of emergency**"
                ),
                color=0x5865F2
            )
            
            await interaction.channel.send(embed=amount_embed, view=AmountInputView(self.sender_id, self.receiver_id))
    
    @discord.ui.button(
        label="Incorrect",
        style=discord.ButtonStyle.danger,
        custom_id="confirm_roles_incorrect_btn",
        emoji="❌"
    )
    async def incorrect(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "❌ Roles rejected. Please select roles again using the buttons above.",
            ephemeral=False
        )

class AmountInputView(discord.ui.View):
    """View for inputting BST amount"""
    def __init__(self, sender_id, receiver_id):
        super().__init__(timeout=None)
        self.sender_id = sender_id
        self.receiver_id = receiver_id
    
    @discord.ui.button(
        label="Enter BST Amount",
        style=discord.ButtonStyle.primary,
        custom_id="enter_amount_modal_btn",
        emoji="💵"
    )
    async def enter_amount(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.sender_id:
            await interaction.response.send_message(
                "❌ Only the sender can enter the amount!",
                ephemeral=True
            )
            return
        
        modal = AmountModal(self.sender_id, self.receiver_id)
        await interaction.response.send_modal(modal)

class AmountModal(discord.ui.Modal, title="Enter BST Amount"):
    def __init__(self, sender_id, receiver_id):
        super().__init__()
        self.sender_id = sender_id
        self.receiver_id = receiver_id
    
    amount_input = discord.ui.TextInput(
        label="BST Amount (e.g. 1.50)",
        placeholder="1.50",
        required=True,
        max_length=10
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = float(self.amount_input.value)
            
            if amount <= 0:
                await interaction.response.send_message(
                    "❌ Amount must be positive!",
                    ephemeral=True
                )
                return
            
            # Check sender balance
            balance = await interaction.client.db.get_balance(self.sender_id)
            
            if balance < amount:
                await interaction.response.send_message(
                    f"❌ Insufficient BST! <@{self.sender_id}> has **{balance:.2f} BST** but needs **{amount:.2f} BST**",
                    ephemeral=True
                )
                return
            
            # Update trade
            trade = await interaction.client.db.get_trade_by_channel(interaction.channel.id)
            if trade:
                await interaction.client.db.set_trade_amount(trade['trade_id'], amount)
            
            # Show amount
            amount_display = discord.Embed(
                title="💵 Amount Set",
                description=f"**Deal Amount: {amount:.2f} BST** (${amount:.2f} USD)",
                color=0x57F287
            )
            
            await interaction.response.send_message(embed=amount_display)
            
            # Confirmation panel
            await asyncio.sleep(1)
            
            confirm_amount_embed = discord.Embed(
                title="✅ Confirm Amount",
                description=(
                    f"<@{self.sender_id}> <@{self.receiver_id}>\n\n"
                    f"**Deal Amount: {amount:.2f} BST**\n\n"
                    "Both users must confirm this is the correct amount.\n\n"
                    "**⚠️ Contact support in case of emergency**"
                ),
                color=0xFEE75C
            )
            
            await interaction.channel.send(embed=confirm_amount_embed, view=ConfirmAmountView(self.sender_id, self.receiver_id, amount))
            
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid amount format!",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )

class ConfirmAmountView(discord.ui.View):
    """View for confirming amount"""
    def __init__(self, sender_id, receiver_id, amount):
        super().__init__(timeout=None)
        self.sender_id = sender_id
        self.receiver_id = receiver_id
        self.amount = amount
        self.confirmed_users = set()
    
    @discord.ui.button(
        label="Correct",
        style=discord.ButtonStyle.success,
        custom_id="confirm_amount_correct_btn",
        emoji="✅"
    )
    async def correct(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        
        if user_id not in [self.sender_id, self.receiver_id]:
            await interaction.response.send_message(
                "❌ You are not part of this trade!",
                ephemeral=True
            )
            return
        
        if user_id in self.confirmed_users:
            await interaction.response.send_message(
                "✅ You already confirmed!",
                ephemeral=True
            )
            return
        
        self.confirmed_users.add(user_id)
        
        await interaction.response.send_message(
            f"✅ {interaction.user.mention} confirmed the amount",
            ephemeral=False
        )
        
        # Check if both confirmed
        if len(self.confirmed_users) == 2:
            # Hold BST from sender
            trade = await interaction.client.db.get_trade_by_channel(interaction.channel.id)
            if not trade:
                await interaction.channel.send("❌ Trade not found!")
                return
            
            success = await interaction.client.db.hold_bst_in_escrow(
                trade['trade_id'],
                self.sender_id,
                self.amount
            )
            
            if not success:
                await interaction.channel.send("❌ Failed to hold BST! Insufficient balance.")
                return
            
            # Success message
            await asyncio.sleep(1)
            
            held_embed = discord.Embed(
                title="🛡️ BST Secured in Escrow",
                description=(
                    f"**{self.amount:.2f} BST** has been removed from <@{self.sender_id}>'s balance and is now held securely by the bot.\n\n"
                    f"<@{self.receiver_id}>, you may now proceed with the deal.\n\n"
                    f"**You may now provide <@{self.sender_id}> with the goods.**\n\n"
                    "**⚠️ Contact support in case of emergency**"
                ),
                color=0x57F287
            )
            
            await interaction.channel.send(embed=held_embed)
            
            # Release panel
            await asyncio.sleep(2)
            
            release_embed = discord.Embed(
                title="📦 Complete the Deal",
                description=(
                    f"<@{self.receiver_id}>, please provide the goods to <@{self.sender_id}>.\n\n"
                    f"Once the deal is complete, <@{self.sender_id}> must click the **'Release'** button below to release the funds to <@{self.receiver_id}>.\n\n"
                    "**⚠️ Contact support in case of emergency**"
                ),
                color=0x5865F2
            )
            
            await interaction.channel.send(embed=release_embed, view=ReleaseView(self.sender_id, self.receiver_id, self.amount))
    
    @discord.ui.button(
        label="Incorrect",
        style=discord.ButtonStyle.danger,
        custom_id="confirm_amount_incorrect_btn",
        emoji="❌"
    )
    async def incorrect(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "❌ Amount rejected. Sender can re-enter the amount above.",
            ephemeral=False
        )

class ReleaseView(discord.ui.View):
    """View for releasing BST"""
    def __init__(self, sender_id, receiver_id, amount):
        super().__init__(timeout=None)
        self.sender_id = sender_id
        self.receiver_id = receiver_id
        self.amount = amount
    
    @discord.ui.button(
        label="Release",
        style=discord.ButtonStyle.success,
        custom_id="release_bst_final_btn",
        emoji="✅"
    )
    async def release(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.sender_id:
            await interaction.response.send_message(
                "❌ Only the sender can release the BST!",
                ephemeral=True
            )
            return
        
        try:
            # Release BST
            trade = await interaction.client.db.get_trade_by_channel(interaction.channel.id)
            if not trade:
                await interaction.response.send_message(
                    "❌ Trade not found!",
                    ephemeral=True
                )
                return
            
            success = await interaction.client.db.release_bst(
                trade['trade_id'],
                self.receiver_id,
                self.amount
            )
            
            if not success:
                await interaction.response.send_message(
                    "❌ Failed to release BST!",
                    ephemeral=True
                )
                return
            
            # Success
            success_embed = discord.Embed(
                title="✅ BST Released!",
                description=(
                    f"**{self.amount:.2f} BST** has been successfully sent to <@{self.receiver_id}>!\n\n"
                    "**Trade completed successfully!**\n\n"
                    "Thank you for using our secure trading system.\n\n"
                    "This ticket will close in 10 seconds..."
                ),
                color=0x57F287
            )
            
            await interaction.response.send_message(embed=success_embed)
            
            # Close ticket
            await asyncio.sleep(10)
            await interaction.channel.delete(reason="Trade completed")
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )
    
    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="cancel_release_btn",
        emoji="❌"
    )
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Trade still in progress. Contact an admin if you need to cancel.",
            ephemeral=True
        )

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
        self.bot.add_view(ConfirmRolesView(0, 0))
        self.bot.add_view(AmountInputView(0, 0))
        self.bot.add_view(ConfirmAmountView(0, 0, 0))
        self.bot.add_view(ReleaseView(0, 0, 0))
        print("✅ Trading cog loaded with persistent views")

    @app_commands.command(name="tradepanel", description="Setup the trading panel (Admin)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def tradepanel(self, interaction: discord.Interaction):
        """Setup trading panel"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Administrator permission required!",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="💱 Secure BST Trading",
            description=(
                "Trade BST safely with our automated escrow system!\n\n"
                "**How It Works:**\n"
                "1️⃣ Create a trade ticket\n"
                "2️⃣ Add your trading partner\n"
                "3️⃣ Select roles (Sender/Receiver)\n"
                "4️⃣ Confirm BST amount\n"
                "5️⃣ Bot holds BST in escrow\n"
                "6️⃣ Complete your Roblox trade\n"
                "7️⃣ Sender releases BST to receiver\n\n"
                "**Security Features:**\n"
                "✅ Bot holds BST during trade\n"
                "✅ Admin monitoring available\n"
                "✅ Automatic refund if cancelled\n"
                "✅ 30-minute inactivity timeout\n\n"
                "**Click the button below to start trading!**"
            ),
            color=0x5865F2
        )
        
        embed.set_footer(text="Trade safely with automated escrow protection!")
        
        await interaction.channel.send(embed=embed, view=TradingPanel())
        
        await interaction.response.send_message(
            "✅ Trading panel created successfully!",
            ephemeral=True
        )

    @tasks.loop(minutes=5)
    async def cleanup_inactive(self):
        """Auto-close inactive trades after 30 minutes"""
        try:
            inactive_trades = await self.bot.db.get_inactive_trades(30)
            
            for trade in inactive_trades:
                try:
                    channel = self.bot.get_channel(trade['channel_id'])
                    if not channel:
                        await self.bot.db.cancel_trade(trade['trade_id'], refund=True)
                        continue
                    
                    # Check if BST is held
                    if trade['stage'] == 'bst_held' and trade['bst_amount'] > 0:
                        # Refund
                        await self.bot.db.cancel_trade(trade['trade_id'], refund=True)
                        
                        embed = discord.Embed(
                            title="⏰ Ticket Auto-Closed - BST Refunded",
                            description=(
                                f"This ticket was inactive for 30 minutes.\n\n"
                                f"**{trade['bst_amount']:.2f} BST** has been refunded to <@{trade['sender_id']}>.\n\n"
                                "Closing in 10 seconds..."
                            ),
                            color=0xFEE75C
                        )
                    else:
                        # Just close
                        await self.bot.db.cancel_trade(trade['trade_id'], refund=False)
                        
                        embed = discord.Embed(
                            title="⏰ Ticket Auto-Closed",
                            description="This ticket was inactive for 30 minutes.\n\nClosing in 10 seconds...",
                            color=0xFEE75C
                        )
                    
                    await channel.send(embed=embed)
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
