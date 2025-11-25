import discord
from discord.ext import commands
from discord import app_commands
import os

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.owner_role_id = int(os.getenv('OWNER_ROLE_ID'))
        self.manager_role_id = int(os.getenv('MANAGER_ROLE_ID'))

    def has_owner_role(self, interaction: discord.Interaction) -> bool:
        """Check if user has owner role"""
        return any(role.id == self.owner_role_id for role in interaction.user.roles)

    def has_manager_role(self, interaction: discord.Interaction) -> bool:
        """Check if user has manager role"""
        return any(role.id == self.manager_role_id for role in interaction.user.roles)

    # ==================== OWNER COMMANDS ====================

    @app_commands.command(name="mint", description="Mint BST into economy pool (Owner Only)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    @app_commands.describe(amount="Amount of BST to mint")
    async def mint(self, interaction: discord.Interaction, amount: float):
        """Mint BST into economy pool"""
        if not self.has_owner_role(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission! (Owner role required)",
                ephemeral=True
            )
            return

        if amount <= 0:
            await interaction.response.send_message(
                "❌ Amount must be positive!",
                ephemeral=True
            )
            return

        try:
            new_pool = await self.bot.db.add_to_pool(amount)

            embed = discord.Embed(
                title="✅ BST Minted",
                description=f"Minted **{amount:.2f} BST** into economy pool",
                color=discord.Color.green()
            )

            embed.add_field(
                name="💰 New Pool Amount",
                value=f"**{new_pool:.2f} BST**",
                inline=False
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="pool", description="View economy pool (Owner Only)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def pool(self, interaction: discord.Interaction):
        """View economy pool"""
        if not self.has_owner_role(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission! (Owner role required)",
                ephemeral=True
            )
            return

        try:
            pool_amount = await self.bot.db.get_economy_pool()
            total_circulation = await self.bot.db.get_total_bst_in_circulation()
            user_count = await self.bot.db.get_user_count()
            boxes_opened = await self.bot.db.get_total_boxes_opened()

            embed = discord.Embed(
                title="📊 Economy Overview",
                color=discord.Color.blue()
            )

            embed.add_field(
                name="💰 Economy Pool",
                value=f"**{pool_amount:.2f} BST**",
                inline=True
            )

            embed.add_field(
                name="💵 BST in Circulation",
                value=f"**{total_circulation:.2f} BST**",
                inline=True
            )

            embed.add_field(
                name="👥 Total Users",
                value=f"**{user_count}** users",
                inline=True
            )

            embed.add_field(
                name="📦 Boxes Opened",
                value=f"**{boxes_opened}** boxes",
                inline=True
            )

            total_bst = pool_amount + total_circulation
            embed.add_field(
                name="🌍 Total BST Supply",
                value=f"**{total_bst:.2f} BST**",
                inline=False
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="reseteconomy", description="Reset entire economy (Owner Only)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def reseteconomy(self, interaction: discord.Interaction):
        """Reset entire economy"""
        if not self.has_owner_role(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission! (Owner role required)",
                ephemeral=True
            )
            return

        # Confirmation view
        class ConfirmView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=30)
                self.value = None

            @discord.ui.button(label="Confirm Reset", style=discord.ButtonStyle.danger, emoji="⚠️")
            async def confirm(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                self.value = True
                self.stop()
                await button_interaction.response.defer()

            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
            async def cancel(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                self.value = False
                self.stop()
                await button_interaction.response.defer()

        embed = discord.Embed(
            title="⚠️ WARNING: Economy Reset",
            description="This will:\n• Remove ALL BST from ALL users\n• Reset economy pool to 0\n• **THIS CANNOT BE UNDONE!**",
            color=discord.Color.red()
        )

        view = ConfirmView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        await view.wait()

        if view.value:
            try:
                # Reset all user balances
                async with self.bot.db.pool.acquire() as conn:
                    await conn.execute("UPDATE users SET bst_balance = 0.0")

                # Reset pool
                await self.bot.db.reset_economy_pool()

                embed = discord.Embed(
                    title="✅ Economy Reset Complete",
                    description="All BST has been removed from the economy.",
                    color=discord.Color.green()
                )

                await interaction.edit_original_response(embed=embed, view=None)

            except Exception as e:
                await interaction.edit_original_response(
                    content=f"❌ Error: {str(e)}",
                    embed=None,
                    view=None
                )
        else:
            await interaction.edit_original_response(
                content="❌ Economy reset cancelled.",
                embed=None,
                view=None
            )

    @app_commands.command(name="drawfrompool", description="Draw BST from pool to give to users (Owner Only)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    @app_commands.describe(
        user="User to give BST to",
        amount="Amount of BST to draw from pool"
    )
    async def drawfrompool(self, interaction: discord.Interaction, user: discord.Member, amount: float):
        """Draw BST from pool and give to user"""
        if not self.has_owner_role(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission! (Owner role required)",
                ephemeral=True
            )
            return

        if amount <= 0:
            await interaction.response.send_message(
                "❌ Amount must be positive!",
                ephemeral=True
            )
            return

        try:
            # Check pool has enough
            pool_amount = await self.bot.db.get_economy_pool()

            if pool_amount < amount:
                await interaction.response.send_message(
                    f"❌ Insufficient BST in pool! Pool has **{pool_amount:.2f} BST**",
                    ephemeral=True
                )
                return

            # Remove from pool
            new_pool = await self.bot.db.remove_from_pool(amount)

            if new_pool is None:
                await interaction.response.send_message(
                    "❌ Failed to draw from pool!",
                    ephemeral=True
                )
                return

            # Add to user
            await self.bot.db.add_bst(user.id, amount)
            user_balance = await self.bot.db.get_balance(user.id)

            embed = discord.Embed(
                title="✅ BST Drawn from Pool",
                description=f"Gave **{amount:.2f} BST** to {user.mention}",
                color=discord.Color.green()
            )

            embed.add_field(
                name="💰 Pool Remaining",
                value=f"**{new_pool:.2f} BST**",
                inline=True
            )

            embed.add_field(
                name="💵 User Balance",
                value=f"**{user_balance:.2f} BST**",
                inline=True
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )

    # ==================== MANAGER COMMANDS ====================

    @app_commands.command(name="addbst", description="Add BST to user (Manager)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    @app_commands.describe(
        user="User to give BST to",
        amount="Amount of BST to add"
    )
    async def addbst(self, interaction: discord.Interaction, user: discord.Member, amount: float):
        """Add BST to user"""
        if not self.has_manager_role(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission! (Manager role required)",
                ephemeral=True
            )
            return

        if amount <= 0:
            await interaction.response.send_message(
                "❌ Amount must be positive!",
                ephemeral=True
            )
            return

        try:
            await self.bot.db.add_bst(user.id, amount)
            new_balance = await self.bot.db.get_balance(user.id)

            embed = discord.Embed(
                title="✅ BST Added",
                description=f"Added **{amount:.2f} BST** to {user.mention}",
                color=discord.Color.green()
            )

            embed.add_field(
                name="💰 New Balance",
                value=f"**{new_balance:.2f} BST**",
                inline=False
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="removebst", description="Remove BST from user (Manager)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    @app_commands.describe(
        user="User to remove BST from",
        amount="Amount of BST to remove"
    )
    async def removebst(self, interaction: discord.Interaction, user: discord.Member, amount: float):
        """Remove BST from user"""
        if not self.has_manager_role(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission! (Manager role required)",
                ephemeral=True
            )
            return

        if amount <= 0:
            await interaction.response.send_message(
                "❌ Amount must be positive!",
                ephemeral=True
            )
            return

        try:
            balance = await self.bot.db.get_balance(user.id)

            if balance < amount:
                await interaction.response.send_message(
                    f"❌ User only has **{balance:.2f} BST**!",
                    ephemeral=True
                )
                return

            success = await self.bot.db.remove_bst(user.id, amount)

            if not success:
                await interaction.response.send_message(
                    "❌ Failed to remove BST!",
                    ephemeral=True
                )
                return

            new_balance = await self.bot.db.get_balance(user.id)

            embed = discord.Embed(
                title="✅ BST Removed",
                description=f"Removed **{amount:.2f} BST** from {user.mention}",
                color=discord.Color.orange()
            )

            embed.add_field(
                name="💰 New Balance",
                value=f"**{new_balance:.2f} BST**",
                inline=False
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="setbst", description="Set exact BST amount for user (Manager)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    @app_commands.describe(
        user="User to set BST for",
        amount="Exact BST amount to set"
    )
    async def setbst(self, interaction: discord.Interaction, user: discord.Member, amount: float):
        """Set exact BST amount"""
        if not self.has_manager_role(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission! (Manager role required)",
                ephemeral=True
            )
            return

        if amount < 0:
            await interaction.response.send_message(
                "❌ Amount cannot be negative!",
                ephemeral=True
            )
            return

        try:
            old_balance = await self.bot.db.get_balance(user.id)
            await self.bot.db.set_bst(user.id, amount)

            embed = discord.Embed(
                title="✅ BST Set",
                description=f"Set {user.mention}'s BST to **{amount:.2f} BST**",
                color=discord.Color.blue()
            )

            embed.add_field(
                name="📊 Previous Balance",
                value=f"**{old_balance:.2f} BST**",
                inline=True
            )

            embed.add_field(
                name="💰 New Balance",
                value=f"**{amount:.2f} BST**",
                inline=True
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="resetuser", description="Reset user's BST to 0 (Manager)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    @app_commands.describe(user="User to reset")
    async def resetuser(self, interaction: discord.Interaction, user: discord.Member):
        """Reset user's BST"""
        if not self.has_manager_role(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission! (Manager role required)",
                ephemeral=True
            )
            return

        try:
            old_balance = await self.bot.db.get_balance(user.id)
            await self.bot.db.set_bst(user.id, 0.0)

            embed = discord.Embed(
                title="✅ User Reset",
                description=f"Reset {user.mention}'s BST to **0 BST**",
                color=discord.Color.red()
            )

            embed.add_field(
                name="📊 Previous Balance",
                value=f"**{old_balance:.2f} BST**",
                inline=False
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Admin(bot))
