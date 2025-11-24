import discord
from discord.ext import commands
from datetime import datetime, timedelta
import config
from database import db

class Trading(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_trades = {}
    
    @commands.hybrid_command(name="trade", description="Start a trade with another user")
    async def trade(self, ctx, user: discord.Member):
        """Initiate trade"""
        if user.bot:
            embed = discord.Embed(
                description=config.Design.small_caps("cannot trade with bots"),
                color=config.Colors.ERROR
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        if user.id == ctx.author.id:
            embed = discord.Embed(
                description=config.Design.small_caps("cannot trade with yourself"),
                color=config.Colors.ERROR
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        # Create trade in database
        async with db.pool.acquire() as conn:
            trade_id = await conn.fetchval(
                """INSERT INTO trades (initiator, partner, initiator_offer, partner_offer, expires_at)
                   VALUES ($1, $2, $3, $4, $5)
                   RETURNING trade_id""",
                ctx.author.id, user.id, {}, {}, datetime.now() + timedelta(minutes=15)
            )
        
        # Create trade UI
        embed = discord.Embed(color=config.Colors.PRIMARY)
        header = config.Design.header("TRADE", 28)
        embed.description = f"```\n{header}\n```\n{config.Design.small_caps(f'trade with {user.display_name}')}"
        
        # Show empty offers
        initiator_offer = config.Design.field('your offer', 'empty', 20)
        partner_offer = config.Design.field('their offer', 'empty', 20)
        
        embed.add_field(name=ctx.author.display_name, value=initiator_offer, inline=True)
        embed.add_field(name=user.display_name, value=partner_offer, inline=True)
        
        # Create view with buttons
        view = TradeView(trade_id, ctx.author.id, user.id, self.bot)
        
        message = await ctx.send(embed=embed, view=view)
        self.active_trades[str(trade_id)] = {
            'message': message,
            'initiator': ctx.author.id,
            'partner': user.id
        }
        
        # Notify partner
        try:
            dm_embed = discord.Embed(
                description=f"{ctx.author.display_name} wants to trade with you!",
                color=config.Colors.INFO
            )
            await user.send(embed=dm_embed)
        except:
            pass

class TradeView(discord.ui.View):
    def __init__(self, trade_id, initiator_id, partner_id, bot):
        super().__init__(timeout=900)  # 15 minute timeout
        self.trade_id = str(trade_id)
        self.initiator_id = initiator_id
        self.partner_id = partner_id
        self.bot = bot
    
    @discord.ui.button(label="Add BST", style=discord.ButtonStyle.primary)
    async def add_bst(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Add BST to offer"""
        if interaction.user.id not in [self.initiator_id, self.partner_id]:
            await interaction.response.send_message(
                config.Design.small_caps("this is not your trade"),
                ephemeral=True
            )
            return
        
        # Show modal for BST amount
        modal = BSTModal(self.trade_id, interaction.user.id == self.initiator_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Add Items", style=discord.ButtonStyle.primary)
    async def add_items(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Add items to offer"""
        if interaction.user.id not in [self.initiator_id, self.partner_id]:
            await interaction.response.send_message(
                config.Design.small_caps("this is not your trade"),
                ephemeral=True
            )
            return
        
        await interaction.response.send_message(
            config.Design.small_caps("item trading coming soon"),
            ephemeral=True
        )
    
    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm trade"""
        if interaction.user.id not in [self.initiator_id, self.partner_id]:
            await interaction.response.send_message(
                config.Design.small_caps("this is not your trade"),
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        
        # Check if both parties confirmed
        async with db.pool.acquire() as conn:
            trade = await conn.fetchrow(
                "SELECT * FROM trades WHERE trade_id = $1",
                self.trade_id
            )
            
            if not trade or trade['status'] != 'pending':
                await interaction.followup.send(
                    config.Design.small_caps("trade no longer available"),
                    ephemeral=True
                )
                return
            
            # Mark as confirmed by this user
            is_initiator = interaction.user.id == self.initiator_id
            
            # Execute trade atomically
            async with conn.transaction():
                initiator_offer = trade['initiator_offer'] or {}
                partner_offer = trade['partner_offer'] or {}
                
                # Transfer BST if any
                if 'bst' in initiator_offer and initiator_offer['bst'] > 0:
                    await conn.execute(
                        "UPDATE users SET bst_balance = bst_balance - $1 WHERE user_id = $2",
                        initiator_offer['bst'], self.initiator_id
                    )
                    await conn.execute(
                        "UPDATE users SET bst_balance = bst_balance + $1 WHERE user_id = $2",
                        initiator_offer['bst'], self.partner_id
                    )
                
                if 'bst' in partner_offer and partner_offer['bst'] > 0:
                    await conn.execute(
                        "UPDATE users SET bst_balance = bst_balance - $1 WHERE user_id = $2",
                        partner_offer['bst'], self.partner_id
                    )
                    await conn.execute(
                        "UPDATE users SET bst_balance = bst_balance + $1 WHERE user_id = $2",
                        partner_offer['bst'], self.initiator_id
                    )
                
                # Mark trade complete
                await conn.execute(
                    "UPDATE trades SET status = 'completed' WHERE trade_id = $1",
                    self.trade_id
                )
                
                # Log transaction
                await conn.execute(
                    """INSERT INTO transactions (tx_type, from_user, to_user, amount_bst, item_data)
                       VALUES ('trade', $1, $2, $3, $4)""",
                    self.initiator_id, self.partner_id, 
                    initiator_offer.get('bst', 0),
                    {'trade_id': self.trade_id, 'offers': {'initiator': initiator_offer, 'partner': partner_offer}}
                )
        
        # Update message
        embed = discord.Embed(
            description=config.Design.small_caps("trade completed successfully"),
            color=config.Colors.SUCCESS
        )
        
        await interaction.message.edit(embed=embed, view=None)
        self.stop()
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel trade"""
        if interaction.user.id not in [self.initiator_id, self.partner_id]:
            await interaction.response.send_message(
                config.Design.small_caps("this is not your trade"),
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        
        async with db.pool.acquire() as conn:
            await conn.execute(
                "UPDATE trades SET status = 'cancelled' WHERE trade_id = $1",
                self.trade_id
            )
        
        embed = discord.Embed(
            description=config.Design.small_caps("trade cancelled"),
            color=config.Colors.ERROR
        )
        
        await interaction.message.edit(embed=embed, view=None)
        self.stop()

class BSTModal(discord.ui.Modal, title="Add BST to Trade"):
    def __init__(self, trade_id, is_initiator):
        super().__init__()
        self.trade_id = trade_id
        self.is_initiator = is_initiator
    
    amount = discord.ui.TextInput(
        label="BST Amount",
        placeholder="0.00",
        required=True,
        max_length=10
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            bst_amount = float(self.amount.value)
            if bst_amount <= 0:
                raise ValueError("Amount must be positive")
        except ValueError:
            await interaction.followup.send(
                config.Design.small_caps("invalid amount"),
                ephemeral=True
            )
            return
        
        # Check balance
        balance = await db.get_balance(interaction.user.id)
        if balance < bst_amount:
            await interaction.followup.send(
                config.Design.small_caps("insufficient balance"),
                ephemeral=True
            )
            return
        
        # Update trade offer
        async with db.pool.acquire() as conn:
            field = 'initiator_offer' if self.is_initiator else 'partner_offer'
            
            await conn.execute(
                f"""UPDATE trades 
                   SET {field} = jsonb_set(COALESCE({field}, '{{}}'::jsonb), '{{bst}}', to_jsonb($1::numeric))
                   WHERE trade_id = $2""",
                bst_amount, self.trade_id
            )
        
        await interaction.followup.send(
            f"{config.Design.small_caps('added')} {config.Design.bold(f'{bst_amount:.2f} BST')}",
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(Trading(bot))