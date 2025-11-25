import discord
from discord.ext import commands
import os
import asyncio
from dotenv import load_dotenv
from aiohttp import web
from database import Database

load_dotenv()

class CleanEconomyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        super().__init__(
            command_prefix='!',
            intents=intents,
            help_command=None
        )
        
        self.db = None
        self.initialized = False
        
        # Role IDs from .env
        self.owner_role_id = int(os.getenv('OWNER_ROLE_ID'))
        self.manager_role_id = int(os.getenv('MANAGER_ROLE_ID'))
        self.guild_id = int(os.getenv('GUILD_ID'))

    async def setup_hook(self):
        """Load cogs and clear old commands"""
        # First, clear ALL existing commands globally
        self.tree.clear_commands(guild=None)
        print("🗑️ Cleared global commands")
        
        # Clear guild-specific commands
        guild = discord.Object(id=self.guild_id)
        self.tree.clear_commands(guild=guild)
        print("🗑️ Cleared guild commands")
        
        # Now load only the cogs we want
        cogs = [
            'cogs.economy',
            'cogs.boxes', 
            'cogs.inventory',
            'cogs.trading',
            'cogs.admin'
        ]
        
        for cog in cogs:
            try:
                await self.load_extension(cog)
                print(f"✅ Loaded {cog}")
            except Exception as e:
                print(f"❌ Failed to load {cog}: {e}")

    async def on_ready(self):
        print(f'✅ {self.user} is online!')
        print(f'📊 Guild ID: {self.guild_id}')
        
        if not self.initialized:
            # Connect database
            self.db = Database()
            await self.db.connect()
            
            # SYNC ONLY TO SPECIFIC GUILD - This prevents global command pollution
            guild = discord.Object(id=self.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            
            self.initialized = True
            print("✅ Commands synced to guild only")
            print("🔄 OLD COMMANDS WILL BE REMOVED AUTOMATICALLY")

    async def start_web_server(self):
        """Health check for Render"""
        async def health(request):
            return web.Response(text="Bot running")
        
        app = web.Application()
        app.router.add_get('/', health)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', int(os.getenv('PORT', 8080)))
        await site.start()
        print("✅ Web server started")

async def main():
    bot = CleanEconomyBot()
    
    # Start health check server
    await bot.start_web_server()
    
    # Start bot
    await bot.start(os.getenv('DISCORD_TOKEN'))

if __name__ == "__main__":
    asyncio.run(main())
