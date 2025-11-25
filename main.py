import discord
from discord.ext import commands, tasks
import os
import asyncio
from dotenv import load_dotenv
from aiohttp import web
from database import db

load_dotenv()

class BSTEconomyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        super().__init__(
            command_prefix='"',
            intents=intents,
            help_command=None
        )
        
        self.initialized = False

    async def setup_hook(self):
        """Initialize bot - runs BEFORE on_ready"""
        # STEP 1: Connect to database FIRST!
        try:
            await db.connect()
            print("✓ Database connected successfully")
        except Exception as e:
            print(f"✗ CRITICAL: Database connection failed: {e}")
            print("Bot cannot function without database!")
            return
        
        # STEP 2: Load all cogs
        cogs = [
            'cogs.economy',          # Economy & messages
            'cogs.boxes',            # Mystery boxes
            'cogs.shop',             # Shop system
            'cogs.secure_trading',   # Trading system
            'cogs.gifts',            # Gift system
            'cogs.bounties',         # Bounty board
            'cogs.auctions',         # Auction house
            'cogs.rentals',          # Rental system
            'cogs.achievements',     # Achievements
            'cogs.collections',      # Collections
            'cogs.events',           # Events
            'cogs.loyalty',          # Loyalty program
            'cogs.giveaways',        # Giveaways
            'cogs.admin'             # Admin commands
        ]
        
        loaded = 0
        failed = 0
        
        for cog in cogs:
            try:
                await self.load_extension(cog)
                print(f"✓ Loaded {cog}")
                loaded += 1
            except Exception as e:
                print(f"✗ Failed to load {cog}: {e}")
                failed += 1
        
        print(f"\n📊 Cog Loading Summary: {loaded} loaded, {failed} failed")
        
        # STEP 3: Start background tasks
        if not self.background_tasks.is_running():
            self.background_tasks.start()
            print("✓ Background tasks started")

    async def on_ready(self):
        """Called when bot is ready"""
        print(f'\n{"="*50}')
        print(f'✓ Bot: {self.user} (ID: {self.user.id})')
        print(f'✓ Guilds: {len(self.guilds)}')
        print(f'✓ Users: {len(self.users)}')
        print(f'{"="*50}\n')
        
        # Sync slash commands (only once)
        if not self.initialized:
            try:
                synced = await self.tree.sync()
                print(f"✓ Synced {len(synced)} slash commands")
                self.initialized = True
            except Exception as e:
                print(f"✗ Failed to sync commands: {e}")

    async def close(self):
        """Cleanup on shutdown"""
        print("\n🛑 Shutting down bot...")
        
        # Stop background tasks
        if self.background_tasks.is_running():
            self.background_tasks.cancel()
        
        # Close database connection
        await db.close()
        
        # Close bot
        await super().close()
        print("✓ Bot shutdown complete")

    @tasks.loop(minutes=5)
    async def background_tasks(self):
        """Background maintenance tasks"""
        try:
            # You can add periodic tasks here
            # Example: Clean up old trades, reset daily rewards, etc.
            pass
        except Exception as e:
            print(f"Background task error: {e}")

    @background_tasks.before_loop
    async def before_background_tasks(self):
        """Wait for bot to be ready before starting tasks"""
        await self.wait_until_ready()

    async def start_web_server(self):
        """Web server for Render/Railway health checks"""
        async def health_check(request):
            return web.Response(
                text=f"Bot Status: {'Online' if self.is_ready() else 'Starting...'}\n"
                     f"Guilds: {len(self.guilds)}\n"
                     f"Users: {len(self.users)}"
            )
        
        app = web.Application()
        app.router.add_get('/', health_check)
        app.router.add_get('/health', health_check)
        
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(runner, '0.0.0.0', int(os.getenv('PORT', 8080)))
        await site.start()
        print(f"✓ Web server started on port {os.getenv('PORT', 8080)}")

async def main():
    """Main entry point"""
    bot = BSTEconomyBot()
    
    try:
        # Start web server for hosting platforms
        await bot.start_web_server()
        
        # Start the bot
        token = os.getenv('DISCORD_TOKEN')
        if not token:
            print("✗ ERROR: DISCORD_TOKEN not found in .env file!")
            return
        
        await bot.start(token)
        
    except KeyboardInterrupt:
        print("\n⚠️  Bot stopped by user")
    except Exception as e:
        print(f"✗ FATAL ERROR: {e}")
    finally:
        if not bot.is_closed():
            await bot.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
