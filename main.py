import discord
from discord.ext import commands
import asyncio
import config
from database import db
from aiohttp import web
import sys
import traceback

# Bot setup with both slash and prefix commands
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(
    command_prefix=config.PREFIX,
    intents=intents,
    help_command=None
)

# ==================== STARTUP & SHUTDOWN ====================

@bot.event
async def on_ready():
    print(f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓")
    print(f"┃ {config.Design.bold('BST ECONOMY BOT')}        ┃")
    print(f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛")
    print(f"Logged in as: {bot.user.name}")
    print(f"Bot ID: {bot.user.id}")
    print(f"Guilds: {len(bot.guilds)}")
    print(f"Prefix: {config.PREFIX}")
    print(f"Owner: {config.OWNER_ID}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    # Connect to database
    await db.connect()
    
    # Load cogs
    await load_cogs()
    
    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"✓ Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"✗ Failed to sync commands: {e}")
    
    # Start background tasks
    bot.loop.create_task(weekly_reset_task())
    bot.loop.create_task(cleanup_task())
    
    # Start web server for Render
    bot.loop.create_task(start_web_server())
    
    print(f"✓ Bot ready")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

async def load_cogs():
    """Load all cog files"""
    cogs = [
        'cogs.tickets',
        'cogs.giveaways',
        'cogs.shop',
        'cogs.commands',
        'cogs.boxes',
        'cogs.economy',
        'cogs.trading',
        'cogs.marketplace',
        'cogs.admin'
    ]
    
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            print(f"✓ Loaded {cog}")
        except Exception as e:
            print(f"✗ Failed to load {cog}: {e}")
            traceback.print_exc()

@bot.event
async def on_disconnect():
    await db.close()

# ==================== MESSAGE COUNTING ====================

@bot.event
async def on_message(message):
    # Ignore bots
    if message.author.bot:
        return
    
    # Ignore DMs
    if not message.guild:
        return
    
    # Check if in counting channel
    if config.COUNTING_CHANNELS and message.channel.id in config.COUNTING_CHANNELS:
        # Filter spam messages
        if len(message.content) >= 5:
            # Check if it's a command
            ctx = await bot.get_context(message)
            if not ctx.valid:
                # Award BST for messages
                try:
                    awarded = await db.increment_messages(message.author.id)
                    if awarded > 0:
                        # Send subtle notification
                        embed = discord.Embed(
                            description=f"{config.Design.field('earned', f'{awarded} BST', 15)}",
                            color=config.Colors.SUCCESS
                        )
                        try:
                            await message.author.send(embed=embed)
                        except:
                            pass  # User has DMs disabled
                except Exception as e:
                    print(f"Error in message counting: {e}")
    
    await bot.process_commands(message)

# ==================== BACKGROUND TASKS ====================

async def weekly_reset_task():
    """Reset weekly BST caps every week"""
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            await db.reset_weekly_caps()
            print("✓ Weekly caps reset")
        except Exception as e:
            print(f"Error in weekly reset: {e}")
        
        # Run every 24 hours
        await asyncio.sleep(86400)

async def cleanup_task():
    """Clean up expired data"""
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            async with db.pool.acquire() as conn:
                # Clean expired market listings
                await conn.execute(
                    """UPDATE market_listings 
                       SET status = 'expired' 
                       WHERE expires_at < NOW() AND status = 'active'"""
                )
                
                # Clean expired trades
                await conn.execute(
                    """UPDATE trades 
                       SET status = 'expired' 
                       WHERE expires_at < NOW() AND status = 'pending'"""
                )
                
                # Clean ended giveaways
                await conn.execute(
                    """UPDATE giveaways 
                       SET status = 'ended' 
                       WHERE ends_at < NOW() AND status = 'active'"""
                )
        except Exception as e:
            print(f"Error in cleanup: {e}")
        
        # Run every hour
        await asyncio.sleep(3600)

# ==================== WEB SERVER (for Render) ====================

async def start_web_server():
    """Start a simple web server to keep Render awake"""
    app = web.Application()
    
    async def health_check(request):
        return web.Response(text="BST Economy Bot is running")
    
    async def stats(request):
        stats_data = {
            'bot': bot.user.name,
            'guilds': len(bot.guilds),
            'users': len(bot.users),
            'latency': f"{bot.latency * 1000:.0f}ms"
        }
        return web.json_response(stats_data)
    
    app.router.add_get('/', health_check)
    app.router.add_get('/stats', stats)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("✓ Web server started on port 8080")

# ==================== ERROR HANDLING ====================

@bot.event
async def on_command_error(ctx, error):
    """Global error handler"""
    if isinstance(error, commands.CommandNotFound):
        return
    
    if isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(
            description=config.Design.small_caps("insufficient permissions"),
            color=config.Colors.ERROR
        )
        await ctx.send(embed=embed, ephemeral=True)
        return
    
    if isinstance(error, commands.CommandOnCooldown):
        embed = discord.Embed(
            description=f"{config.Design.small_caps('cooldown')} {config.Design.bold(f'{error.retry_after:.1f}s')}",
            color=config.Colors.WARNING
        )
        await ctx.send(embed=embed, ephemeral=True)
        return
    
    # Log unexpected errors
    print(f"Error in {ctx.command}: {error}")
    traceback.print_exception(type(error), error, error.__traceback__)
    
    embed = discord.Embed(
        description=config.Design.small_caps("an error occurred"),
        color=config.Colors.ERROR
    )
    await ctx.send(embed=embed, ephemeral=True)

# ==================== BASIC COMMANDS ====================

@bot.hybrid_command(name="help", description="Show all commands")
async def help_command(ctx):
    """Display help menu"""
    embed = discord.Embed(color=config.Colors.PRIMARY)
    
    header = config.Design.header("HELP", 28)
    embed.description = f"```\n{header}\n```"
    
    # Economy
    economy = (
        f"\n{config.Design.section('ECONOMY')}\n"
        f"{config.Design.item('"bal [@user]', 'check balance')}\n"
        f"{config.Design.item('"inv [@user]', 'view inventory')}\n"
        f"{config.Design.item('"transfer @user amount', 'send BST')}\n"
    )
    embed.add_field(name="\u200b", value=economy, inline=False)
    
    # Boxes
    boxes = (
        f"\n{config.Design.section('BOXES')}\n"
        f"{config.Design.item('"shop', 'buy mystery boxes')}\n"
        f"{config.Design.item('"open', 'open a box')}\n"
        f"{config.Design.item('"sell', 'sell boxes')}\n"
    )
    embed.add_field(name="\u200b", value=boxes, inline=False)
    
    # Trading & Market
    trading = (
        f"\n{config.Design.section('TRADING')}\n"
        f"{config.Design.item('"trade @user', 'start trade')}\n"
        f"{config.Design.item('"market', 'browse listings')}\n"
    )
    embed.add_field(name="\u200b", value=trading, inline=False)
    
    # Giveaways
    giveaways = (
        f"\n{config.Design.section('GIVEAWAYS')}\n"
        f"{config.Design.item('/giveaway', 'create giveaway')}\n"
        f"{config.Design.item('/gend', 'end giveaway')}\n"
    )
    embed.add_field(name="\u200b", value=giveaways, inline=False)
    
    # Admin
    if ctx.author.id == config.OWNER_ID or any(role.id in config.MANAGER_ROLES for role in ctx.author.roles):
        admin = (
            f"\n{config.Design.section('ADMIN')}\n"
            f"{config.Design.item('/listitem', 'add shop item')}\n"
            f"{config.Design.item('"admin', 'admin panel')}\n"
        )
        embed.add_field(name="\u200b", value=admin, inline=False)
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="transfer", description="Transfer BST to another user")
async def transfer(ctx, user: discord.Member, amount: float):
    """Transfer BST"""
    if amount <= 0:
        embed = discord.Embed(
            description=config.Design.small_caps("amount must be positive"),
            color=config.Colors.ERROR
        )
        await ctx.send(embed=embed, ephemeral=True)
        return
    
    if user.bot:
        embed = discord.Embed(
            description=config.Design.small_caps("cannot transfer to bots"),
            color=config.Colors.ERROR
        )
        await ctx.send(embed=embed, ephemeral=True)
        return
    
    if user.id == ctx.author.id:
        embed = discord.Embed(
            description=config.Design.small_caps("cannot transfer to yourself"),
            color=config.Colors.ERROR
        )
        await ctx.send(embed=embed, ephemeral=True)
        return
    
    sender_balance = await db.get_balance(ctx.author.id)
    
    if sender_balance < amount:
        embed = discord.Embed(
            description=config.Design.small_caps("insufficient balance"),
            color=config.Colors.ERROR
        )
        await ctx.send(embed=embed, ephemeral=True)
        return
    
    # Perform transfer
    await db.update_balance(ctx.author.id, amount, 'subtract')
    await db.update_balance(user.id, amount, 'add')
    await db.log_transaction('transfer', ctx.author.id, user.id, amount, {})
    
    embed = discord.Embed(color=config.Colors.SUCCESS)
    
    header = config.Design.header("TRANSFER", 28)
    embed.description = f"```\n{header}\n```"
    
    content = (
        f"\n{config.Design.field('to', user.display_name, 20)}\n"
        f"{config.Design.field('amount', f'{amount:.2f} BST', 20)}\n"
        f"{config.Design.field('new balance', f'{sender_balance - amount:.2f} BST', 20)}\n"
    )
    
    embed.add_field(name="Success", value=content, inline=False)
    
    await ctx.send(embed=embed)

# ==================== RUN BOT ====================

if __name__ == "__main__":
    try:
        bot.run(config.DISCORD_TOKEN)
    except KeyboardInterrupt:
        print("\n✓ Bot stopped by user")
    except Exception as e:
        print(f"✗ Fatal error: {e}")
        traceback.print_exc()