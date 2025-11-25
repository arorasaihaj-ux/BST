import discord
from discord.ext import commands, tasks
import os
import asyncio
from dotenv import load_dotenv
from aiohttp import web
import sys
import traceback

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
        # Load all cogs - CORRECTED LIST (14 cogs)
        cogs = [
            'cogs.economy',          # Economy & messages
            'cogs.boxes',            # Mystery boxes & panels
            'cogs.shop',             # Shop system
            'cogs.secure_trading',   # Premium trading system
            'cogs.gifts',            # Gift system
            'cogs.bounties',         # Bounty board
            'cogs.auctions',         # Auction house
            'cogs.rentals',          # Rental system
            'cogs.achievements',     # Achievements
            'cogs.collections',      # Collections
            'cogs.events',           # Events system
            'cogs.loyalty',          # Loyalty program
            'cogs.giveaways',        # Giveaway system
            'cogs.admin'             # Admin commands
        ]
        
        for cog in cogs:
            try:
                await self.load_extension(cog)
                print(f"✓ Loaded {cog}")
            except Exception as e:
                print(f"✗ Failed to load {cog}: {e}")

        # Start background tasks
        self.background_tasks.start()

    async def on_ready(self):
        print(f'✓ {self.user} is online!')
        print(f'✓ Guild: {len(self.guilds)}')
        
        if not self.initialized:
            await self.tree.sync()
            self.initialized = True
            print("✓ Slash commands synced")

    async def on_message(self, message):
        if message.author.bot:
            return
        
        # Process commands
        await self.process_commands(message)

    @tasks.loop(minutes=5)
    async def background_tasks(self):
        """Background tasks for economy maintenance"""
        try:
            # Background tasks handled by individual cogs
            pass
        except Exception as e:
            print(f"Background task error: {e}")

    async def start_web_server(self):
        """Web server for Render health checks"""
        async def health_check(request):
            return web.Response(text="Bot is running")
        
        app = web.Application()
        app.router.add_get('/', health_check)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 8080)
        await site.start()

async def main():
    bot = BSTEconomyBot()
    
    # Start web server for Render
    await bot.start_web_server()
    
    # Start the bot
    await bot.start(os.getenv('DISCORD_TOKEN'))

if __name__ == "__main__":
    asyncio.run(main())
