import discord
from discord.ext import commands
from discord import app_commands
import os

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.owner_role_id = int(os.getenv('OWNER_ROLE_ID'))
        
        # Parse multiple manager role IDs
        manager_roles_str = os.getenv('MANAGER_ROLE_ID', '')
        self.manager_role_ids = [int(role_id.strip()) for role_id in manager_roles_str.split(',') if role_id.strip()]

    def has_owner_role(self, interaction: discord.Interaction) -> bool:
        """Check if user has owner role"""
        return any(role.id == self.owner_role_id for role in interaction.user.roles)

    def has_manager_role(self, interaction: discord.Interaction) -> bool:
        """Check if user has any manager role"""
        return any(role.id in self.manager_role_ids for role in interaction.user.roles)

    # ==================== OWNER COMMANDS ====================

    @app_commands.command(name="mint", description="Mint BST into economy pool (Owner Only)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def mint(self, interaction: discord.Interaction, amount: float):
        if not self.has_owner_role(interaction):
            await interaction.response.send_message("❌ Owner role required!", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be positive!", ephemeral=True)
            return

        try:
            new_pool = await self.bot.db.add_to_pool(amount)
            circulation = await self.bot.db.get_total_bst_in_circulation()
            total_supply = new_pool + circulation
            
            embed = discord.Embed(
                title="✅ BST Minted",
                description=f"Minted **{amount:.2f} BST** into economy pool",
                color=0x57F287
            )
            embed.add_field(name="💰 Pool Balance", value=f"**{new_pool:.2f} BST**", inline=True)
            embed.add_field(name="💵 In Circulation", value=f"**{circulation:.2f} BST**", inline=True)
            embed.add_field(name="🌍 Total Supply", value=f"**{total_supply:.2f} BST**", inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="pool", description="View economy stats (Owner Only)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def pool(self, interaction: discord.Interaction):
        if not self.has_owner_role(interaction):
            await interaction.response.send_message("❌ Owner role required!", ephemeral=True)
            return

        try:
            pool = await self.bot.db.get_pool_balance()
            circulation = await self.bot.db.get_total_bst_in_circulation()
            users = await self.bot.db.get_user_count()
            boxes = await self.bot.db.get_total_boxes_opened()
            weekly_remaining = await self.bot.db.get_weekly_remaining()
            
            embed = discord.Embed(title="📊 Economy Overview", color=0x5865F2)
            embed.add_field(name="💰 Pool (Available)", value=f"{pool:.2f} BST", inline=True)
            embed.add_field(name="💵 In Circulation", value=f"{circulation:.2f} BST", inline=True)
            embed.add_field(name="🌍 Total Supply", value=f"{pool + circulation:.2f} BST", inline=True)
            embed.add_field(name="👥 Users", value=f"{users}", inline=True)
            embed.add_field(name="📦 Boxes Opened", value=f"{boxes}", inline=True)
            embed.add_field(name="📅 Weekly Left", value=f"{weekly_remaining:.1f} BST", inline=True)
            
            embed.set_footer(text="Managers can only distribute BST from the Pool")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="resetpool", description="Reset economy pool to 0 (Owner Only)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def resetpool(self, interaction: discord.Interaction):
        if not self.has_owner_role(interaction):
            await interaction.response.send_message("❌ Owner role required!", ephemeral=True)
            return

        class ConfirmView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=30)
                self.value = None

            @discord.ui.button(label="⚠️ CONFIRM RESET", style=discord.ButtonStyle.danger)
            async def confirm(self, button_int: discord.Interaction, button: discord.ui.Button):
                self.value = True
                self.stop()
                await button_int.response.defer()

            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
            async def cancel(self, button_int: discord.Interaction, button: discord.ui.Button):
                self.value = False
                self.stop()
                await button_int.response.defer()

        pool = await self.bot.db.get_pool_balance()
        circulation = await self.bot.db.get_total_bst_in_circulation()
        
        embed = discord.Embed(
            title="⚠️ WARNING: Reset Economy Pool",
            description=(
                f"This will reset the pool to **0 BST**!\n\n"
                f"**Current Pool:** {pool:.2f} BST\n"
                f"**In Circulation:** {circulation:.2f} BST\n\n"
                f"**This ONLY removes BST from the pool!**\n"
                f"**User balances will NOT be affected!**"
            ),
            color=0xED4245
        )

        view = ConfirmView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        await view.wait()

        if view.value:
            try:
                await self.bot.db.reset_pool()
                await interaction.edit_original_response(
                    content="✅ Economy pool reset to 0 BST!",
                    embed=None,
                    view=None
                )
            except Exception as e:
                await interaction.edit_original_response(
                    content=f"❌ Error: {e}",
                    embed=None,
                    view=None
                )
        else:
            await interaction.edit_original_response(
                content="❌ Reset cancelled.",
                embed=None,
                view=None
            )

    # ==================== MANAGER COMMANDS (UPDATED) ====================

    @app_commands.command(name="addbst", description="Give BST to user FROM POOL (Manager)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def addbst(self, interaction: discord.Interaction, user: discord.Member, amount: float):
        if not self.has_manager_role(interaction):
            await interaction.response.send_message("❌ Manager role required!", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be positive!", ephemeral=True)
            return

        try:
            # Check pool balance
            pool_balance = await self.bot.db.get_pool_balance()
            
            if pool_balance < amount:
                embed = discord.Embed(
                    title="❌ Insufficient Pool Balance",
                    description=f"Cannot add **{amount:.2f} BST** to {user.mention}",
                    color=0xED4245
                )
                embed.add_field(
                    name="💰 Pool Balance",
                    value=f"**{pool_balance:.2f} BST** available",
                    inline=True
                )
                embed.add_field(
                    name="❌ Short By",
                    value=f"**{amount - pool_balance:.2f} BST**",
                    inline=True
                )
                embed.set_footer(text="Ask owner to mint more BST!")
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Add BST from pool
            success = await self.bot.db.add_bst(user.id, amount)
            
            if not success:
                await interaction.response.send_message("❌ Failed to add BST!", ephemeral=True)
                return
            
            new_balance = await self.bot.db.get_balance(user.id)
            new_pool = await self.bot.db.get_pool_balance()
            
            embed = discord.Embed(
                title="✅ BST Added",
                description=f"Gave **{amount:.2f} BST** to {user.mention}",
                color=0x57F287
            )
            embed.add_field(name="👤 User Balance", value=f"{new_balance:.2f} BST", inline=True)
            embed.add_field(name="💰 Pool Remaining", value=f"{new_pool:.2f} BST", inline=True)
            
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="removebst", description="Remove BST from user (Manager)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def removebst(self, interaction: discord.Interaction, user: discord.Member, amount: float):
        if not self.has_manager_role(interaction):
            await interaction.response.send_message("❌ Manager role required!", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be positive!", ephemeral=True)
            return

        try:
            balance = await self.bot.db.get_balance(user.id)
            
            if balance < amount:
                await interaction.response.send_message(
                    f"❌ User only has {balance:.2f} BST!",
                    ephemeral=True
                )
                return

            success = await self.bot.db.remove_bst(user.id, amount)
            
            if not success:
                await interaction.response.send_message("❌ Failed to remove BST!", ephemeral=True)
                return

            new_balance = await self.bot.db.get_balance(user.id)
            
            embed = discord.Embed(
                title="✅ BST Removed",
                description=f"Removed **{amount:.2f} BST** from {user.mention}",
                color=0xFEE75C
            )
            embed.add_field(name="💰 New Balance", value=f"{new_balance:.2f} BST")
            embed.set_footer(text="⚠️ This BST is destroyed (not returned to pool)")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="setbst", description="Set exact BST amount (Manager)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def setbst(self, interaction: discord.Interaction, user: discord.Member, amount: float):
        if not self.has_manager_role(interaction):
            await interaction.response.send_message("❌ Manager role required!", ephemeral=True)
            return

        if amount < 0:
            await interaction.response.send_message("❌ Amount cannot be negative!", ephemeral=True)
            return

        try:
            old_balance = await self.bot.db.get_balance(user.id)
            await self.bot.db.set_bst(user.id, amount)
            
            embed = discord.Embed(
                title="✅ BST Set",
                description=f"Set {user.mention}'s BST to **{amount:.2f} BST**",
                color=0x5865F2
            )
            embed.add_field(name="📊 Previous", value=f"{old_balance:.2f} BST", inline=True)
            embed.add_field(name="💰 New", value=f"{amount:.2f} BST", inline=True)
            embed.set_footer(text="⚠️ This bypasses the pool system")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="resetuser", description="Reset user's BST to 0 (Manager)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def resetuser(self, interaction: discord.Interaction, user: discord.Member):
        if not self.has_manager_role(interaction):
            await interaction.response.send_message("❌ Manager role required!", ephemeral=True)
            return

        try:
            old_balance = await self.bot.db.get_balance(user.id)
            await self.bot.db.set_bst(user.id, 0.0)
            
            embed = discord.Embed(
                title="✅ User Reset",
                description=f"Reset {user.mention}'s BST to **0 BST**",
                color=0xED4245
            )
            embed.add_field(name="📊 Previous Balance", value=f"{old_balance:.2f} BST")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Admin(bot))
