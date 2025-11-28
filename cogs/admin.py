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

    @app_commands.command(name="pool", description="View detailed economy stats (Owner Only)")
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
            
            # Get weekly distributed total
            weekly_distributed = await self.bot.db.get_weekly_remaining()
            
            embed = discord.Embed(title="📊 Economy Overview", color=0x5865F2)
            embed.add_field(name="💰 Pool (Available)", value=f"{pool:.2f} BST", inline=True)
            embed.add_field(name="💵 In Circulation", value=f"{circulation:.2f} BST", inline=True)
            embed.add_field(name="🌍 Total Supply", value=f"{pool + circulation:.2f} BST", inline=True)
            embed.add_field(name="👥 Users", value=f"{users}", inline=True)
            embed.add_field(name="📦 Boxes Opened", value=f"{boxes}", inline=True)
            embed.add_field(name="📅 Weekly Distributed", value=f"{weekly_distributed:.1f} BST", inline=True)
            
            embed.set_footer(text="Use /circulation to see who holds BST • /setpool to edit pool")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="circulation", description="View all users holding BST (Owner Only)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def circulation(self, interaction: discord.Interaction, page: int = 1):
        if not self.has_owner_role(interaction):
            await interaction.response.send_message("❌ Owner role required!", ephemeral=True)
            return

        try:
            all_balances = await self.bot.db.get_all_balances()
            
            if not all_balances:
                await interaction.response.send_message("No users have BST yet!", ephemeral=True)
                return
            
            # Pagination
            per_page = 15
            total_pages = (len(all_balances) + per_page - 1) // per_page
            page = max(1, min(page, total_pages))
            
            start = (page - 1) * per_page
            end = start + per_page
            page_balances = all_balances[start:end]
            
            embed = discord.Embed(
                title=f"💵 BST Circulation (Page {page}/{total_pages})",
                description="All users holding BST",
                color=0x5865F2
            )
            
            users_text = ""
            for user_id, balance in page_balances:
                member = interaction.guild.get_member(user_id)
                name = member.display_name if member else f"User {user_id}"
                users_text += f"**{name}** — {balance:.2f} BST\n"
            
            embed.add_field(name="Users", value=users_text, inline=False)
            
            total_circulation = sum(b[1] for b in all_balances)
            embed.add_field(
                name="📊 Total",
                value=f"**{len(all_balances)} users** holding **{total_circulation:.2f} BST**",
                inline=False
            )
            
            embed.set_footer(text="Use /resetuser to remove a user's BST (returns to pool)")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="setpool", description="Set exact pool amount (Owner Only)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def setpool(self, interaction: discord.Interaction, amount: float):
        if not self.has_owner_role(interaction):
            await interaction.response.send_message("❌ Owner role required!", ephemeral=True)
            return

        if amount < 0:
            await interaction.response.send_message("❌ Amount cannot be negative!", ephemeral=True)
            return

        try:
            old_pool = await self.bot.db.get_pool_balance()
            await self.bot.db.set_pool_balance(amount)
            circulation = await self.bot.db.get_total_bst_in_circulation()
            
            embed = discord.Embed(
                title="✅ Pool Balance Set",
                description=f"Pool balance changed to **{amount:.2f} BST**",
                color=0x5865F2
            )
            embed.add_field(name="📊 Previous Pool", value=f"{old_pool:.2f} BST", inline=True)
            embed.add_field(name="💰 New Pool", value=f"{amount:.2f} BST", inline=True)
            embed.add_field(name="💵 Circulation", value=f"{circulation:.2f} BST (unchanged)", inline=False)
            embed.set_footer(text="⚠️ This only affects the pool, not user balances")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="addpool", description="Add BST to pool (Owner Only)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def addpool(self, interaction: discord.Interaction, amount: float):
        if not self.has_owner_role(interaction):
            await interaction.response.send_message("❌ Owner role required!", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be positive!", ephemeral=True)
            return

        try:
            new_pool = await self.bot.db.add_to_pool(amount)
            circulation = await self.bot.db.get_total_bst_in_circulation()
            
            embed = discord.Embed(
                title="✅ BST Added to Pool",
                description=f"Added **{amount:.2f} BST** to pool",
                color=0x57F287
            )
            embed.add_field(name="💰 New Pool", value=f"{new_pool:.2f} BST", inline=True)
            embed.add_field(name="💵 Circulation", value=f"{circulation:.2f} BST", inline=True)
            embed.add_field(name="🌍 Total Supply", value=f"{new_pool + circulation:.2f} BST", inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="removepool", description="Remove BST from pool (Owner Only)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def removepool(self, interaction: discord.Interaction, amount: float):
        if not self.has_owner_role(interaction):
            await interaction.response.send_message("❌ Owner role required!", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be positive!", ephemeral=True)
            return

        try:
            pool_balance = await self.bot.db.get_pool_balance()
            
            if pool_balance < amount:
                await interaction.response.send_message(
                    f"❌ Pool only has {pool_balance:.2f} BST!",
                    ephemeral=True
                )
                return
            
            new_pool = await self.bot.db.remove_from_pool_direct(amount)
            circulation = await self.bot.db.get_total_bst_in_circulation()
            
            embed = discord.Embed(
                title="✅ BST Removed from Pool",
                description=f"Removed **{amount:.2f} BST** from pool",
                color=0xFEE75C
            )
            embed.add_field(name="💰 New Pool", value=f"{new_pool:.2f} BST", inline=True)
            embed.add_field(name="💵 Circulation", value=f"{circulation:.2f} BST (unchanged)", inline=True)
            embed.set_footer(text="⚠️ This BST is destroyed")
            
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

    # ==================== MANAGER COMMANDS ====================

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

    @app_commands.command(name="removebst", description="Remove BST from user and RETURN TO POOL (Manager)")
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

            # FIXED: Remove BST and return to pool
            success = await self.bot.db.remove_bst_return_to_pool(user.id, amount)
            
            if not success:
                await interaction.response.send_message("❌ Failed to remove BST!", ephemeral=True)
                return

            new_balance = await self.bot.db.get_balance(user.id)
            new_pool = await self.bot.db.get_pool_balance()
            
            embed = discord.Embed(
                title="✅ BST Removed",
                description=f"Removed **{amount:.2f} BST** from {user.mention}",
                color=0x57F287
            )
            embed.add_field(name="💰 User Balance", value=f"{new_balance:.2f} BST", inline=True)
            embed.add_field(name="♻️ Returned to Pool", value=f"{new_pool:.2f} BST", inline=True)
            embed.set_footer(text="✅ BST returned to pool")
            
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

    @app_commands.command(name="resetuser", description="Reset user's BST to 0 and RETURN TO POOL (Manager)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def resetuser(self, interaction: discord.Interaction, user: discord.Member):
        if not self.has_manager_role(interaction):
            await interaction.response.send_message("❌ Manager role required!", ephemeral=True)
            return

        try:
            old_balance = await self.bot.db.get_balance(user.id)
            
            if old_balance == 0:
                await interaction.response.send_message(
                    f"❌ {user.mention} already has 0 BST!",
                    ephemeral=True
                )
                return
            
            # FIXED: Return BST to pool
            success = await self.bot.db.reset_user_and_return_to_pool(user.id)
            
            if not success:
                await interaction.response.send_message("❌ Failed to reset user!", ephemeral=True)
                return
            
            new_pool = await self.bot.db.get_pool_balance()
            circulation = await self.bot.db.get_total_bst_in_circulation()
            
            embed = discord.Embed(
                title="✅ User Reset",
                description=f"Reset {user.mention}'s BST to **0 BST**",
                color=0x57F287
            )
            embed.add_field(name="📊 Previous Balance", value=f"{old_balance:.2f} BST", inline=True)
            embed.add_field(name="♻️ Returned to Pool", value=f"{old_balance:.2f} BST", inline=True)
            embed.add_field(name="💰 New Pool Balance", value=f"{new_pool:.2f} BST", inline=False)
            embed.add_field(name="💵 New Circulation", value=f"{circulation:.2f} BST", inline=True)
            embed.set_footer(text="✅ BST returned to economy pool")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    # ==================== INVENTORY MANAGEMENT ====================

    @app_commands.command(name="removeitem", description="Remove specific item from user's inventory (Manager)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def removeitem(self, interaction: discord.Interaction, user: discord.Member, item_name: str, quantity: int = 1):
        if not self.has_manager_role(interaction):
            await interaction.response.send_message("❌ Manager role required!", ephemeral=True)
            return

        if quantity <= 0:
            await interaction.response.send_message("❌ Quantity must be positive!", ephemeral=True)
            return

        try:
            inventory = await self.bot.db.get_inventory(user.id)
            
            item_found = None
            for item in inventory['items']:
                if item['item_name'].lower() == item_name.lower():
                    item_found = item
                    break
            
            if not item_found:
                await interaction.response.send_message(
                    f"❌ {user.mention} doesn't have **{item_name}** in their inventory!",
                    ephemeral=True
                )
                return
            
            if item_found['quantity'] < quantity:
                await interaction.response.send_message(
                    f"❌ {user.mention} only has **{item_found['quantity']}x {item_name}** (trying to remove {quantity})",
                    ephemeral=True
                )
                return
            
            success = await self.bot.db.remove_inventory_item(user.id, item_name, quantity)
            
            if not success:
                await interaction.response.send_message("❌ Failed to remove item!", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="✅ Item Removed",
                description=f"Removed **{quantity}x {item_name}** from {user.mention}'s inventory",
                color=0xFEE75C
            )
            
            remaining = item_found['quantity'] - quantity
            if remaining > 0:
                embed.add_field(name="📦 Remaining", value=f"{remaining}x {item_name}", inline=True)
            else:
                embed.add_field(name="📦 Status", value="Item completely removed", inline=True)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="resetinventory", description="Clear ALL items from user's inventory (Manager)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def resetinventory(self, interaction: discord.Interaction, user: discord.Member):
        if not self.has_manager_role(interaction):
            await interaction.response.send_message("❌ Manager role required!", ephemeral=True)
            return

        try:
            inventory = await self.bot.db.get_inventory(user.id)
            
            if not inventory['items']:
                await interaction.response.send_message(
                    f"❌ {user.mention} has no items in their inventory!",
                    ephemeral=True
                )
                return
            
            item_count = len(inventory['items'])
            total_items = sum(item['quantity'] for item in inventory['items'])
            
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
            
            embed = discord.Embed(
                title="⚠️ WARNING: Reset Inventory",
                description=(
                    f"This will remove **ALL items** from {user.mention}'s inventory!\n\n"
                    f"**{item_count} unique items** ({total_items} total items) will be deleted.\n\n"
                    "**This action cannot be undone!**"
                ),
                color=0xED4245
            )
            
            items_list = []
            for item in inventory['items'][:10]:
                items_list.append(f"• {item['item_name']} x{item['quantity']}")
            
            if len(inventory['items']) > 10:
                items_list.append(f"\n*...and {len(inventory['items']) - 10} more items*")
            
            embed.add_field(name="Items to be deleted:", value="\n".join(items_list), inline=False)
            
            view = ConfirmView()
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            await view.wait()
            
            if view.value:
                success = await self.bot.db.clear_inventory(user.id)
                
                if not success:
                    await interaction.edit_original_response(
                        content="❌ Failed to clear inventory!",
                        embed=None,
                        view=None
                    )
                    return
                
                success_embed = discord.Embed(
                    title="✅ Inventory Cleared",
                    description=f"Removed **{total_items} items** from {user.mention}'s inventory",
                    color=0x57F287
                )
                success_embed.add_field(name="Unique Items", value=f"{item_count}", inline=True)
                success_embed.add_field(name="Total Items", value=f"{total_items}", inline=True)
                
                await interaction.edit_original_response(
                    content=None,
                    embed=success_embed,
                    view=None
                )
            else:
                await interaction.edit_original_response(
                    content="❌ Reset cancelled.",
                    embed=None,
                    view=None
                )
                
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Admin(bot))
