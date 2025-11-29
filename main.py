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
        
        # MULTIPLE OWNER SUPPORT
        owner_ids_str = os.getenv('OWNER_USER_IDS', '')
        self.owner_user_ids = [int(uid.strip()) for uid in owner_ids_str.split(',') if uid.strip()]
        
        # Manager roles
        manager_roles_str = os.getenv('MANAGER_ROLE_ID', '')
        self.manager_role_ids = [int(role_id.strip()) for role_id in manager_roles_str.split(',') if role_id.strip()]
        
        self.guild_id = int(os.getenv('GUILD_ID'))
        
        print(f"🔧 Configured {len(self.owner_user_ids)} owner(s)")
        print(f"🔧 Configured {len(self.manager_role_ids)} manager role(s)")

    async def setup_hook(self):
        """Load cogs"""
        self.tree.clear_commands(guild=None)
        print("🗑️ Cleared global commands")
        
        guild = discord.Object(id=self.guild_id)
        self.tree.clear_commands(guild=guild)
        print("🗑️ Cleared guild commands")
        
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
        print(f'👤 Owner User IDs: {self.owner_user_ids}')
        print(f'👥 Manager Role IDs: {self.manager_role_ids}')
        
        if not self.initialized:
            self.db = Database()
            await self.db.connect()
            
            guild = discord.Object(id=self.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            
            self.initialized = True
            print("✅ Commands synced to guild")
            
            # Display pool status on startup
            try:
                pools = await self.db.get_both_pools()
                circulation = await self.db.get_total_bst_in_circulation()
                print(f"\n💰 ECONOMY STATUS:")
                print(f"   Main Pool: {pools['main_pool']:.2f} BST")
                print(f"   Weekly Pool: {pools['weekly_pool']:.2f} BST")
                print(f"   Circulation: {circulation:.2f} BST")
                print(f"   Total Supply: {pools['main_pool'] + circulation:.2f} BST\n")
            except Exception as e:
                print(f"⚠️ Could not fetch economy status: {e}")

    async def on_command_error(self, ctx, error):
        """Global error handler"""
        if isinstance(error, commands.CommandNotFound):
            return
        print(f"Command error: {error}")

    async def start_web_server(self):
        """Health check for Render"""
        async def health(request):
            return web.Response(text="Bot running")
        
        async def status(request):
            """Status endpoint showing bot info"""
            if self.is_ready():
                pools = await self.db.get_both_pools()
                circulation = await self.db.get_total_bst_in_circulation()
                
                status_text = f"""
Bot Status: Online
Guild: {self.guild_id}
Owners: {len(self.owner_user_ids)}
Managers: {len(self.manager_role_ids)}

Economy:
  Main Pool: {pools['main_pool']:.2f} BST
  Weekly Pool: {pools['weekly_pool']:.2f} BST
  Circulation: {circulation:.2f} BST
  Total Supply: {pools['main_pool'] + circulation:.2f} BST
                """
                return web.Response(text=status_text)
            else:
                return web.Response(text="Bot starting...", status=503)
        
        app = web.Application()
        app.router.add_get('/', health)
        app.router.add_get('/status', status)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', int(os.getenv('PORT', 8080)))
        await site.start()
        print("✅ Web server started on port", os.getenv('PORT', 8080))

async def main():
    bot = CleanEconomyBot()
    
    # Start health check server
    await bot.start_web_server()
    
    # Start bot
    try:
        await bot.start(os.getenv('DISCORD_TOKEN'))
    except KeyboardInterrupt:
        print("\n⚠️ Shutting down...")
        await bot.close()
    except Exception as e:
        print(f"❌ Error: {e}")
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())
