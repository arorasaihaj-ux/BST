import discord
from discord.ext import commands
from discord import app_commands
import os

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # MULTIPLE OWNER SUPPORT
        owner_ids_str = os.getenv('OWNER_USER_IDS', '')
        self.owner_user_ids = [int(uid.strip()) for uid in owner_ids_str.split(',') if uid.strip()]
        
        # Manager roles
        manager_roles_str = os.getenv('MANAGER_ROLE_ID', '')
        self.manager_role_ids = [int(role_id.strip()) for role_id in manager_roles_str.split(',') if role_id.strip()]

    def has_owner_role(self, interaction: discord.Interaction) -> bool:
        """Check if user is an owner"""
        return interaction.user.id in self.owner_user_ids

    def has_manager_role(self, interaction: discord.Interaction) -> bool:
        """Check if user has manager role"""
        return any(role.id in self.manager_role_ids for role in interaction.user.roles)

    # ==================== OWNER: MAIN POOL COMMANDS ====================

    @app_commands.command(name="mint", description="Mint BST into main economy pool (Owner Only)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def mint(self, interaction: discord.Interaction, amount: float):
        if not self.has_owner_role(interaction):
            await interaction.response.send_message("❌ Owner permission required!", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be positive!", ephemeral=True)
            return

        try:
            new_pool = await self.bot.db.add_to_pool(amount)
            circulation = await self.bot.db.get_total_bst_in_circulation()
            weekly_pool = await self.bot.db.get_weekly_pool()
            total_supply = new_pool + circulation
            
            embed = discord.Embed(
                title="✅ BST Minted",
                description=f"Minted **{amount:.2f} BST** into main economy pool",
                color=0x57F287
            )
            embed.add_field(name="💰 Main Pool", value=f"**{new_pool:.2f} BST**", inline=True)
            embed.add_field(name="📅 Weekly Pool", value=f"**{weekly_pool:.2f} BST**", inline=True)
            embed.add_field(name="💵 In Circulation", value=f"**{circulation:.2f} BST**", inline=True)
            embed.add_field(name="🌐 Total Supply", value=f"**{total_supply:.2f} BST**", inline=False)
            
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="pool", description="View detailed economy stats")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def pool(self, interaction: discord.Interaction):
        try:
            main_pool = await self.bot.db.get_pool_balance()
            weekly_pool = await self.bot.db.get_weekly_pool()
            circulation = await self.bot.db.get_total_bst_in_circulation()
            users = await self.bot.db.get_user_count()
            boxes = await self.bot.db.get_total_boxes_opened()
            
            embed = discord.Embed(title="📊 Economy Overview", color=0x5865F2)
            embed.add_field(name="💰 Main Pool", value=f"{main_pool:.2f} BST", inline=True)
            embed.add_field(name="📅 Weekly Pool", value=f"{weekly_pool:.2f} BST", inline=True)
            embed.add_field(name="💵 In Circulation", value=f"{circulation:.2f} BST", inline=True)
            embed.add_field(name="🌐 Total Supply", value=f"{main_pool + circulation:.2f} BST", inline=True)
            embed.add_field(name="👥 Users", value=f"{users}", inline=True)
            embed.add_field(name="📦 Boxes Opened", value=f"{boxes}", inline=True)
            
            embed.set_footer(text="Weekly pool resets every Monday")
            
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="circulation", description="View all users holding BST (Owner Only)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def circulation(self, interaction: discord.Interaction, page: int = 1):
        if not self.has_owner_role(interaction):
            await interaction.response.send_message("❌ Owner permission required!", ephemeral=True)
            return

        try:
            all_balances = await self.bot.db.get_all_balances()
            
            if not all_balances:
                await interaction.response.send_message("No users have BST yet!", ephemeral=True)
                return
            
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
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="setpool", description="Set exact main pool amount (Owner Only)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def setpool(self, interaction: discord.Interaction, amount: float):
        if not self.has_owner_role(interaction):
            await interaction.response.send_message("❌ Owner permission required!", ephemeral=True)
            return

        if amount < 0:
            await interaction.response.send_message("❌ Amount cannot be negative!", ephemeral=True)
            return

        try:
            old_pool = await self.bot.db.get_pool_balance()
            await self.bot.db.set_pool_balance(amount)
            circulation = await self.bot.db.get_total_bst_in_circulation()
            
            embed = discord.Embed(
                title="✅ Main Pool Balance Set",
                description=f"Main pool balance changed to **{amount:.2f} BST**",
                color=0x5865F2
            )
            embed.add_field(name="📊 Previous Pool", value=f"{old_pool:.2f} BST", inline=True)
            embed.add_field(name="💰 New Pool", value=f"{amount:.2f} BST", inline=True)
            embed.add_field(name="💵 Circulation", value=f"{circulation:.2f} BST (unchanged)", inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="addpool", description="Add BST to main pool (Owner Only)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def addpool(self, interaction: discord.Interaction, amount: float):
        if not self.has_owner_role(interaction):
            await interaction.response.send_message("❌ Owner permission required!", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be positive!", ephemeral=True)
            return

        try:
            new_pool = await self.bot.db.add_to_pool(amount)
            circulation = await self.bot.db.get_total_bst_in_circulation()
            
            embed = discord.Embed(
                title="✅ BST Added to Main Pool",
                description=f"Added **{amount:.2f} BST** to main pool",
                color=0x57F287
            )
            embed.add_field(name="💰 New Pool", value=f"{new_pool:.2f} BST", inline=True)
            embed.add_field(name="💵 Circulation", value=f"{circulation:.2f} BST", inline=True)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="removepool", description="Remove BST from main pool (Owner Only)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def removepool(self, interaction: discord.Interaction, amount: float):
        if not self.has_owner_role(interaction):
            await interaction.response.send_message("❌ Owner permission required!", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be positive!", ephemeral=True)
            return

        try:
            pool_balance = await self.bot.db.get_pool_balance()
            
            if pool_balance < amount:
                await interaction.response.send_message(
                    f"❌ Main pool only has {pool_balance:.2f} BST!",
                    ephemeral=True
                )
                return
            
            new_pool = await self.bot.db.remove_from_pool_direct(amount)
            
            embed = discord.Embed(
                title="✅ BST Removed from Main Pool",
                description=f"Removed **{amount:.2f} BST** from main pool",
                color=0xFEE75C
            )
            embed.add_field(name="💰 New Pool", value=f"{new_pool:.2f} BST", inline=True)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    # ==================== OWNER/MANAGER: WEEKLY POOL COMMANDS ====================

    @app_commands.command(name="setweekly", description="Set exact weekly pool amount (Owner/Manager)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def setweekly(self, interaction: discord.Interaction, amount: float):
        if not (self.has_owner_role(interaction) or self.has_manager_role(interaction)):
            await interaction.response.send_message("❌ Owner/Manager permission required!", ephemeral=True)
            return

        if amount < 0:
            await interaction.response.send_message("❌ Amount cannot be negative!", ephemeral=True)
            return

        try:
            old_weekly = await self.bot.db.get_weekly_pool()
            await self.bot.db.set_weekly_pool(amount)
            
            embed = discord.Embed(
                title="✅ Weekly Pool Set",
                description=f"Weekly pool set to **{amount:.2f} BST**",
                color=0x5865F2
            )
            embed.add_field(name="📊 Previous", value=f"{old_weekly:.2f} BST", inline=True)
            embed.add_field(name="📅 New Weekly", value=f"{amount:.2f} BST", inline=True)
            embed.set_footer(text="Users can now earn from this pool via messages")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="addweekly", description="Add BST to weekly pool (Owner/Manager)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def addweekly(self, interaction: discord.Interaction, amount: float):
        if not (self.has_owner_role(interaction) or self.has_manager_role(interaction)):
            await interaction.response.send_message("❌ Owner/Manager permission required!", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be positive!", ephemeral=True)
            return

        try:
            new_weekly = await self.bot.db.add_to_weekly_pool(amount)
            
            embed = discord.Embed(
                title="✅ BST Added to Weekly Pool",
                description=f"Added **{amount:.2f} BST** to weekly pool",
                color=0x57F287
            )
            embed.add_field(name="📅 New Weekly Pool", value=f"{new_weekly:.2f} BST", inline=True)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="removeweekly", description="Remove BST from weekly pool (Owner/Manager)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def removeweekly(self, interaction: discord.Interaction, amount: float):
        if not (self.has_owner_role(interaction) or self.has_manager_role(interaction)):
            await interaction.response.send_message("❌ Owner/Manager permission required!", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be positive!", ephemeral=True)
            return

        try:
            weekly_balance = await self.bot.db.get_weekly_pool()
            
            if weekly_balance < amount:
                await interaction.response.send_message(
                    f"❌ Weekly pool only has {weekly_balance:.2f} BST!",
                    ephemeral=True
                )
                return
            
            new_weekly = await self.bot.db.remove_from_weekly_pool(amount)
            
            if new_weekly is None:
                await interaction.response.send_message("❌ Failed to remove BST!", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="✅ BST Removed from Weekly Pool",
                description=f"Removed **{amount:.2f} BST** from weekly pool",
                color=0xFEE75C
            )
            embed.add_field(name="📅 New Weekly Pool", value=f"{new_weekly:.2f} BST", inline=True)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="resetweekly", description="Reset weekly pool to default (Owner/Manager)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def resetweekly(self, interaction: discord.Interaction, amount: float = 10.0):
        if not (self.has_owner_role(interaction) or self.has_manager_role(interaction)):
            await interaction.response.send_message("❌ Owner/Manager permission required!", ephemeral=True)
            return

        try:
            old_weekly = await self.bot.db.get_weekly_pool()
            await self.bot.db.reset_weekly_pool(amount)
            
            embed = discord.Embed(
                title="✅ Weekly Pool Reset",
                description=f"Weekly pool reset to **{amount:.2f} BST**",
                color=0x57F287
            )
            embed.add_field(name="📊 Previous", value=f"{old_weekly:.2f} BST", inline=True)
            embed.add_field(name="📅 New Weekly", value=f"{amount:.2f} BST", inline=True)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    # ==================== MANAGER COMMANDS ====================

    @app_commands.command(name="addbst", description="Give BST to user FROM MAIN POOL (Manager)")
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
                await interaction.response.send_message(
                    f"❌ Main pool only has {pool_balance:.2f} BST!",
                    ephemeral=True
                )
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

    @app_commands.command(name="removebst", description="Remove BST from user and RETURN TO MAIN POOL (Manager)")
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
            embed.add_field(name="♻️ Returned to Main Pool", value=f"{new_pool:.2f} BST", inline=True)
            
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
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="resetuser", description="Reset user's BST to 0 and RETURN TO MAIN POOL (Manager)")
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
            
            success = await self.bot.db.reset_user_and_return_to_pool(user.id)
            
            if not success:
                await interaction.response.send_message("❌ Failed to reset user!", ephemeral=True)
                return
            
            new_pool = await self.bot.db.get_pool_balance()
            
            embed = discord.Embed(
                title="✅ User Reset",
                description=f"Reset {user.mention}'s BST to **0 BST**",
                color=0x57F287
            )
            embed.add_field(name="📊 Previous Balance", value=f"{old_balance:.2f} BST", inline=True)
            embed.add_field(name="♻️ Returned to Main Pool", value=f"{old_balance:.2f} BST", inline=True)
            embed.add_field(name="💰 New Main Pool", value=f"{new_pool:.2f} BST", inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    # ==================== INVENTORY MANAGEMENT ====================

    @app_commands.command(name="removeitem", description="Remove item from inventory (Manager)")
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
                    f"❌ {user.mention} doesn't have **{item_name}**!",
                    ephemeral=True
                )
                return
            
            if item_found['quantity'] < quantity:
                await interaction.response.send_message(
                    f"❌ {user.mention} only has **{item_found['quantity']}x {item_name}**",
                    ephemeral=True
                )
                return
            
            success = await self.bot.db.remove_inventory_item(user.id, item_name, quantity)
            
            if not success:
                await interaction.response.send_message("❌ Failed to remove item!", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="✅ Item Removed",
                description=f"Removed **{quantity}x {item_name}** from {user.mention}",
                color=0xFEE75C
            )
            
            remaining = item_found['quantity'] - quantity
            if remaining > 0:
                embed.add_field(name="📦 Remaining", value=f"{remaining}x {item_name}", inline=True)
            else:
                embed.add_field(name="📦 Status", value="Item removed completely", inline=True)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="resetinventory", description="Clear ALL items from inventory (Manager)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def resetinventory(self, interaction: discord.Interaction, user: discord.Member):
        if not self.has_manager_role(interaction):
            await interaction.response.send_message("❌ Manager role required!", ephemeral=True)
            return

        try:
            inventory = await self.bot.db.get_inventory(user.id)
            
            if not inventory['items']:
                await interaction.response.send_message(
                    f"❌ {user.mention} has no items!",
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

    @app_commands.command(name="resetpool", description="Reset main economy pool to 0 (Owner Only)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def resetpool(self, interaction: discord.Interaction):
        if not self.has_owner_role(interaction):
            await interaction.response.send_message("❌ Owner permission required!", ephemeral=True)
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
            title="⚠️ WARNING: Reset Main Economy Pool",
            description=(
                f"This will reset the main pool to **0 BST**!\n\n"
                f"**Current Main Pool:** {pool:.2f} BST\n"
                f"**In Circulation:** {circulation:.2f} BST\n\n"
                f"**This ONLY removes BST from the main pool!**\n"
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
                    content="✅ Main economy pool reset to 0 BST!",
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

async def setup(bot):
    await bot.add_cog(Admin(bot))
