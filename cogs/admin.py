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
        return interaction.user.id in self.owner_user_ids

    def has_manager_role(self, interaction: discord.Interaction) -> bool:
        return any(role.id in self.manager_role_ids for role in interaction.user.roles)

    # ==================== OWNER COMMANDS ====================

    @app_commands.command(name="mint", description="Mint BST into main pool")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def mint(self, interaction: discord.Interaction, amount: float):
        if not self.has_owner_role(interaction):
            await interaction.response.send_message("**𝐎𝐖𝐍𝐄𝐑 𝐎𝐍𝐋𝐘**", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("**𝐈𝐍𝐕𝐀𝐋𝐈𝐃 𝐀𝐌𝐎𝐔𝐍𝐓**", ephemeral=True)
            return

        try:
            new_pool = await self.bot.db.add_to_pool(amount)
            circulation = await self.bot.db.get_total_bst_in_circulation()
            weekly_pool = await self.bot.db.get_weekly_pool()
            
            embed = discord.Embed(
                title="𝐌𝐈𝐍𝐓𝐄𝐃",
                description=f"**{amount:.2f} 𝐁𝐒𝐓** 𝐦𝐢𝐧𝐭𝐞𝐝\n**𝐌𝐚𝐢𝐧 𝐏𝐨𝐨𝐥:** {new_pool:.2f}\n**𝐖𝐞𝐞𝐤𝐥𝐲:** {weekly_pool:.2f}\n**𝐂𝐢𝐫𝐜𝐮𝐥𝐚𝐭𝐢𝐨𝐧:** {circulation:.2f}",
                color=0x2B2D31
            )
            
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"**𝐄𝐑𝐑𝐎𝐑**\n{e}", ephemeral=True)

    @app_commands.command(name="pool", description="View economy stats")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def pool(self, interaction: discord.Interaction):
        try:
            main_pool = await self.bot.db.get_pool_balance()
            weekly_pool = await self.bot.db.get_weekly_pool()
            circulation = await self.bot.db.get_total_bst_in_circulation()
            users = await self.bot.db.get_user_count()
            boxes = await self.bot.db.get_total_boxes_opened()
            
            embed = discord.Embed(
                title="𝐄𝐂𝐎𝐍𝐎𝐌𝐘 𝐎𝐕𝐄𝐑𝐕𝐈𝐄𝐖",
                description=f"**𝐌𝐚𝐢𝐧 𝐏𝐨𝐨𝐥:** {main_pool:.2f} 𝐁𝐒𝐓\n**𝐖𝐞𝐞𝐤𝐥𝐲 𝐏𝐨𝐨𝐥:** {weekly_pool:.2f} 𝐁𝐒𝐓\n**𝐂𝐢𝐫𝐜𝐮𝐥𝐚𝐭𝐢𝐨𝐧:** {circulation:.2f} 𝐁𝐒𝐓\n**𝐓𝐨𝐭𝐚𝐥 𝐒𝐮𝐩𝐩𝐥𝐲:** {main_pool + circulation:.2f} 𝐁𝐒𝐓\n**𝐔𝐬𝐞𝐫𝐬:** {users}\n**𝐁𝐨𝐱𝐞𝐬 𝐎𝐩𝐞𝐧𝐞𝐝:** {boxes}",
                color=0x2B2D31
            )
            
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"**𝐄𝐑𝐑𝐎𝐑**\n{e}", ephemeral=True)

    @app_commands.command(name="setweekly", description="Set weekly pool amount")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def setweekly(self, interaction: discord.Interaction, amount: float):
        if not (self.has_owner_role(interaction) or self.has_manager_role(interaction)):
            await interaction.response.send_message("**𝐎𝐖𝐍𝐄𝐑/𝐌𝐀𝐍𝐀𝐆𝐄𝐑 𝐎𝐍𝐋𝐘**", ephemeral=True)
            return

        if amount < 0:
            await interaction.response.send_message("**𝐈𝐍𝐕𝐀𝐋𝐈𝐃 𝐀𝐌𝐎𝐔𝐍𝐓**", ephemeral=True)
            return

        try:
            old_weekly = await self.bot.db.get_weekly_pool()
            await self.bot.db.set_weekly_pool(amount)
            
            embed = discord.Embed(
                title="𝐖𝐄𝐄𝐊𝐋𝐘 𝐏𝐎𝐎𝐋 𝐒𝐄𝐓",
                description=f"**𝐏𝐫𝐞𝐯𝐢𝐨𝐮𝐬:** {old_weekly:.2f} 𝐁𝐒𝐓\n**𝐍𝐞𝐰:** {amount:.2f} 𝐁𝐒𝐓",
                color=0x2B2D31
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"**𝐄𝐑𝐑𝐎𝐑**\n{e}", ephemeral=True)

    # ==================== UID-BASED COMMANDS ====================

    @app_commands.command(name="addbstuid", description="Add BST using UID (Manager)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def addbstuid(self, interaction: discord.Interaction, user_id: str, amount: float):
        if not self.has_manager_role(interaction):
            await interaction.response.send_message("**𝐌𝐀𝐍𝐀𝐆𝐄𝐑 𝐎𝐍𝐋𝐘**", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("**𝐈𝐍𝐕𝐀𝐋𝐈𝐃 𝐀𝐌𝐎𝐔𝐍𝐓**", ephemeral=True)
            return

        try:
            uid = int(user_id)
            pool_balance = await self.bot.db.get_pool_balance()
            
            if pool_balance < amount:
                await interaction.response.send_message(
                    f"**𝐈𝐍𝐒𝐔𝐅𝐅𝐈𝐂𝐈𝐄𝐍𝐓 𝐏𝐎𝐎𝐋**\n{pool_balance:.2f} 𝐁𝐒𝐓 𝐚𝐯𝐚𝐢𝐥𝐚𝐛𝐥𝐞",
                    ephemeral=True
                )
                return
            
            success = await self.bot.db.add_bst(uid, amount)
            
            if not success:
                await interaction.response.send_message("**𝐅𝐀𝐈𝐋𝐄𝐃**", ephemeral=True)
                return
            
            new_balance = await self.bot.db.get_balance(uid)
            
            embed = discord.Embed(
                title="𝐁𝐒𝐓 𝐀𝐃𝐃𝐄𝐃",
                description=f"**𝐔𝐬𝐞𝐫 𝐈𝐃:** {uid}\n**𝐀𝐦𝐨𝐮𝐧𝐭:** {amount:.2f} 𝐁𝐒𝐓\n**𝐍𝐞𝐰 𝐁𝐚𝐥𝐚𝐧𝐜𝐞:** {new_balance:.2f} 𝐁𝐒𝐓",
                color=0x2B2D31
            )
            
            await interaction.response.send_message(embed=embed)
        except ValueError:
            await interaction.response.send_message("**𝐈𝐍𝐕𝐀𝐋𝐈𝐃 𝐔𝐈𝐃**", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"**𝐄𝐑𝐑𝐎𝐑**\n{e}", ephemeral=True)

    @app_commands.command(name="removebstuid", description="Remove BST using UID (Manager)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def removebstuid(self, interaction: discord.Interaction, user_id: str, amount: float):
        if not self.has_manager_role(interaction):
            await interaction.response.send_message("**𝐌𝐀𝐍𝐀𝐆𝐄𝐑 𝐎𝐍𝐋𝐘**", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("**𝐈𝐍𝐕𝐀𝐋𝐈𝐃 𝐀𝐌𝐎𝐔𝐍𝐓**", ephemeral=True)
            return

        try:
            uid = int(user_id)
            balance = await self.bot.db.get_balance(uid)
            
            if balance < amount:
                await interaction.response.send_message(
                    f"**𝐈𝐍𝐒𝐔𝐅𝐅𝐈𝐂𝐈𝐄𝐍𝐓 𝐁𝐀𝐋𝐀𝐍𝐂𝐄**\n𝐔𝐬𝐞𝐫 𝐡𝐚𝐬 {balance:.2f} 𝐁𝐒𝐓",
                    ephemeral=True
                )
                return

            success = await self.bot.db.remove_bst_return_to_pool(uid, amount)
            
            if not success:
                await interaction.response.send_message("**𝐅𝐀𝐈𝐋𝐄𝐃**", ephemeral=True)
                return

            new_balance = await self.bot.db.get_balance(uid)
            
            embed = discord.Embed(
                title="𝐁𝐒𝐓 𝐑𝐄𝐌𝐎𝐕𝐄𝐃",
                description=f"**𝐔𝐬𝐞𝐫 𝐈𝐃:** {uid}\n**𝐀𝐦𝐨𝐮𝐧𝐭:** {amount:.2f} 𝐁𝐒𝐓\n**𝐍𝐞𝐰 𝐁𝐚𝐥𝐚𝐧𝐜𝐞:** {new_balance:.2f} 𝐁𝐒𝐓",
                color=0x2B2D31
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except ValueError:
            await interaction.response.send_message("**𝐈𝐍𝐕𝐀𝐋𝐈𝐃 𝐔𝐈𝐃**", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"**𝐄𝐑𝐑𝐎𝐑**\n{e}", ephemeral=True)

    @app_commands.command(name="resetinventoryuid", description="Reset inventory using UID (Manager)")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def resetinventoryuid(self, interaction: discord.Interaction, user_id: str):
        if not self.has_manager_role(interaction):
            await interaction.response.send_message("**𝐌𝐀𝐍𝐀𝐆𝐄𝐑 𝐎𝐍𝐋𝐘**", ephemeral=True)
            return

        try:
            uid = int(user_id)
            inventory = await self.bot.db.get_inventory(uid)
            
            if not inventory['items']:
                await interaction.response.send_message(
                    f"**𝐍𝐎 𝐈𝐓𝐄𝐌𝐒**\n𝐔𝐬𝐞𝐫 𝐈𝐃 {uid} 𝐡𝐚𝐬 𝐧𝐨 𝐢𝐭𝐞𝐦𝐬",
                    ephemeral=True
                )
                return
            
            success = await self.bot.db.clear_inventory(uid)
            
            if not success:
                await interaction.response.send_message("**𝐅𝐀𝐈𝐋𝐄𝐃**", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="𝐈𝐍𝐕𝐄𝐍𝐓𝐎𝐑𝐘 𝐂𝐋𝐄𝐀𝐑𝐄𝐃",
                description=f"**𝐔𝐬𝐞𝐫 𝐈𝐃:** {uid}\n**𝐈𝐭𝐞𝐦𝐬 𝐑𝐞𝐦𝐨𝐯𝐞𝐝:** {len(inventory['items'])}",
                color=0x2B2D31
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except ValueError:
            await interaction.response.send_message("**𝐈𝐍𝐕𝐀𝐋𝐈𝐃 𝐔𝐈𝐃**", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"**𝐄𝐑𝐑𝐎𝐑**\n{e}", ephemeral=True)


# ==================== CONTINUATION OF ADMIN COG ====================
    # ADD THIS TO THE END OF admin.py BEFORE async def setup(bot)

    @app_commands.command(name="addbst", description="Add BST to user")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def addbst(self, interaction: discord.Interaction, user: discord.Member, amount: float):
        if not self.has_manager_role(interaction):
            await interaction.response.send_message("**𝐌𝐀𝐍𝐀𝐆𝐄𝐑 𝐎𝐍𝐋𝐘**", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("**𝐈𝐍𝐕𝐀𝐋𝐈𝐃 𝐀𝐌𝐎𝐔𝐍𝐓**", ephemeral=True)
            return

        try:
            pool_balance = await self.bot.db.get_pool_balance()
            
            if pool_balance < amount:
                await interaction.response.send_message(
                    f"**𝐈𝐍𝐒𝐔𝐅𝐅𝐈𝐂𝐈𝐄𝐍𝐓 𝐏𝐎𝐎𝐋**\n{pool_balance:.2f} 𝐁𝐒𝐓",
                    ephemeral=True
                )
                return
            
            success = await self.bot.db.add_bst(user.id, amount)
            
            if not success:
                await interaction.response.send_message("**𝐅𝐀𝐈𝐋𝐄𝐃**", ephemeral=True)
                return
            
            new_balance = await self.bot.db.get_balance(user.id)
            
            embed = discord.Embed(
                title="𝐁𝐒𝐓 𝐀𝐃𝐃𝐄𝐃",
                description=f"**𝐔𝐬𝐞𝐫:** {user.mention}\n**𝐀𝐦𝐨𝐮𝐧𝐭:** {amount:.2f} 𝐁𝐒𝐓\n**𝐍𝐞𝐰 𝐁𝐚𝐥𝐚𝐧𝐜𝐞:** {new_balance:.2f} 𝐁𝐒𝐓",
                color=0x2B2D31
            )
            
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"**𝐄𝐑𝐑𝐎𝐑**\n{e}", ephemeral=True)

    @app_commands.command(name="removebst", description="Remove BST from user")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def removebst(self, interaction: discord.Interaction, user: discord.Member, amount: float):
        if not self.has_manager_role(interaction):
            await interaction.response.send_message("**𝐌𝐀𝐍𝐀𝐆𝐄𝐑 𝐎𝐍𝐋𝐘**", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("**𝐈𝐍𝐕𝐀𝐋𝐈𝐃 𝐀𝐌𝐎𝐔𝐍𝐓**", ephemeral=True)
            return

        try:
            balance = await self.bot.db.get_balance(user.id)
            
            if balance < amount:
                await interaction.response.send_message(
                    f"**𝐈𝐍𝐒𝐔𝐅𝐅𝐈𝐂𝐈𝐄𝐍𝐓**\n{balance:.2f} 𝐁𝐒𝐓",
                    ephemeral=True
                )
                return

            success = await self.bot.db.remove_bst_return_to_pool(user.id, amount)
            
            if not success:
                await interaction.response.send_message("**𝐅𝐀𝐈𝐋𝐄𝐃**", ephemeral=True)
                return

            new_balance = await self.bot.db.get_balance(user.id)
            
            embed = discord.Embed(
                title="𝐁𝐒𝐓 𝐑𝐄𝐌𝐎𝐕𝐄𝐃",
                description=f"**𝐔𝐬𝐞𝐫:** {user.mention}\n**𝐀𝐦𝐨𝐮𝐧𝐭:** {amount:.2f} 𝐁𝐒𝐓\n**𝐍𝐞𝐰 𝐁𝐚𝐥𝐚𝐧𝐜𝐞:** {new_balance:.2f} 𝐁𝐒𝐓",
                color=0x2B2D31
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"**𝐄𝐑𝐑𝐎𝐑**\n{e}", ephemeral=True)

    @app_commands.command(name="setbst", description="Set exact BST amount")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def setbst(self, interaction: discord.Interaction, user: discord.Member, amount: float):
        if not self.has_manager_role(interaction):
            await interaction.response.send_message("**𝐌𝐀𝐍𝐀𝐆𝐄𝐑 𝐎𝐍𝐋𝐘**", ephemeral=True)
            return

        if amount < 0:
            await interaction.response.send_message("**𝐈𝐍𝐕𝐀𝐋𝐈𝐃 𝐀𝐌𝐎𝐔𝐍𝐓**", ephemeral=True)
            return

        try:
            old_balance = await self.bot.db.get_balance(user.id)
            await self.bot.db.set_bst(user.id, amount)
            
            embed = discord.Embed(
                title="𝐁𝐒𝐓 𝐒𝐄𝐓",
                description=f"**𝐔𝐬𝐞𝐫:** {user.mention}\n**𝐏𝐫𝐞𝐯𝐢𝐨𝐮𝐬:** {old_balance:.2f} 𝐁𝐒𝐓\n**𝐍𝐞𝐰:** {amount:.2f} 𝐁𝐒𝐓",
                color=0x2B2D31
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"**𝐄𝐑𝐑𝐎𝐑**\n{e}", ephemeral=True)

    @app_commands.command(name="resetuser", description="Reset user to 0 BST")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def resetuser(self, interaction: discord.Interaction, user: discord.Member):
        if not self.has_manager_role(interaction):
            await interaction.response.send_message("**𝐌𝐀𝐍𝐀𝐆𝐄𝐑 𝐎𝐍𝐋𝐘**", ephemeral=True)
            return

        try:
            old_balance = await self.bot.db.get_balance(user.id)
            
            if old_balance == 0:
                await interaction.response.send_message(
                    f"**𝐀𝐋𝐑𝐄𝐀𝐃𝐘 𝟎**\n{user.mention}",
                    ephemeral=True
                )
                return
            
            success = await self.bot.db.reset_user_and_return_to_pool(user.id)
            
            if not success:
                await interaction.response.send_message("**𝐅𝐀𝐈𝐋𝐄𝐃**", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="𝐔𝐒𝐄𝐑 𝐑𝐄𝐒𝐄𝐓",
                description=f"**𝐔𝐬𝐞𝐫:** {user.mention}\n**𝐏𝐫𝐞𝐯𝐢𝐨𝐮𝐬:** {old_balance:.2f} 𝐁𝐒𝐓\n**𝐍𝐞𝐰:** 0.00 𝐁𝐒𝐓",
                color=0x2B2D31
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"**𝐄𝐑𝐑𝐎𝐑**\n{e}", ephemeral=True)

    @app_commands.command(name="circulation", description="View BST circulation")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def circulation(self, interaction: discord.Interaction, page: int = 1):
        if not self.has_owner_role(interaction):
            await interaction.response.send_message("**𝐎𝐖𝐍𝐄𝐑 𝐎𝐍𝐋𝐘**", ephemeral=True)
            return

        try:
            all_balances = await self.bot.db.get_all_balances()
            
            if not all_balances:
                await interaction.response.send_message("**𝐍𝐎 𝐔𝐒𝐄𝐑𝐒**", ephemeral=True)
                return
            
            per_page = 15
            total_pages = (len(all_balances) + per_page - 1) // per_page
            page = max(1, min(page, total_pages))
            
            start = (page - 1) * per_page
            end = start + per_page
            page_balances = all_balances[start:end]
            
            users_text = ""
            for user_id, balance in page_balances:
                member = interaction.guild.get_member(user_id)
                name = member.display_name if member else f"𝐔𝐈𝐃 {user_id}"
                users_text += f"**{name}** {balance:.2f} 𝐁𝐒𝐓\n"
            
            total_circulation = sum(b[1] for b in all_balances)
            
            embed = discord.Embed(
                title=f"𝐂𝐈𝐑𝐂𝐔𝐋𝐀𝐓𝐈𝐎𝐍 {page}/{total_pages}",
                description=f"{users_text}\n**𝐓𝐨𝐭𝐚𝐥:** {len(all_balances)} 𝐮𝐬𝐞𝐫𝐬\n**𝐂𝐢𝐫𝐜𝐮𝐥𝐚𝐭𝐢𝐨𝐧:** {total_circulation:.2f} 𝐁𝐒𝐓",
                color=0x2B2D31
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"**𝐄𝐑𝐑𝐎𝐑**\n{e}", ephemeral=True)

    @app_commands.command(name="removeitem", description="Remove item from inventory")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def removeitem(self, interaction: discord.Interaction, user: discord.Member, item_name: str, quantity: int = 1):
        if not self.has_manager_role(interaction):
            await interaction.response.send_message("**𝐌𝐀𝐍𝐀𝐆𝐄𝐑 𝐎𝐍𝐋𝐘**", ephemeral=True)
            return

        if quantity <= 0:
            await interaction.response.send_message("**𝐈𝐍𝐕𝐀𝐋𝐈𝐃 𝐐𝐔𝐀𝐍𝐓𝐈𝐓𝐘**", ephemeral=True)
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
                    f"**𝐈𝐓𝐄𝐌 𝐍𝐎𝐓 𝐅𝐎𝐔𝐍𝐃**\n{item_name}",
                    ephemeral=True
                )
                return
            
            if item_found['quantity'] < quantity:
                await interaction.response.send_message(
                    f"**𝐈𝐍𝐒𝐔𝐅𝐅𝐈𝐂𝐈𝐄𝐍𝐓**\n{item_found['quantity']}x {item_name}",
                    ephemeral=True
                )
                return
            
            success = await self.bot.db.remove_inventory_item(user.id, item_name, quantity)
            
            if not success:
                await interaction.response.send_message("**𝐅𝐀𝐈𝐋𝐄𝐃**", ephemeral=True)
                return
            
            remaining = item_found['quantity'] - quantity
            
            embed = discord.Embed(
                title="𝐈𝐓𝐄𝐌 𝐑𝐄𝐌𝐎𝐕𝐄𝐃",
                description=f"**𝐔𝐬𝐞𝐫:** {user.mention}\n**𝐈𝐭𝐞𝐦:** {item_name}\n**𝐑𝐞𝐦𝐨𝐯𝐞𝐝:** {quantity}\n**𝐑𝐞𝐦𝐚𝐢𝐧𝐢𝐧𝐠:** {remaining}",
                color=0x2B2D31
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"**𝐄𝐑𝐑𝐎𝐑**\n{e}", ephemeral=True)

    @app_commands.command(name="resetinventory", description="Clear user inventory")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def resetinventory(self, interaction: discord.Interaction, user: discord.Member):
        if not self.has_manager_role(interaction):
            await interaction.response.send_message("**𝐌𝐀𝐍𝐀𝐆𝐄𝐑 𝐎𝐍𝐋𝐘**", ephemeral=True)
            return

        try:
            inventory = await self.bot.db.get_inventory(user.id)
            
            if not inventory['items']:
                await interaction.response.send_message(
                    f"**𝐍𝐎 𝐈𝐓𝐄𝐌𝐒**\n{user.mention}",
                    ephemeral=True
                )
                return
            
            success = await self.bot.db.clear_inventory(user.id)
            
            if not success:
                await interaction.response.send_message("**𝐅𝐀𝐈𝐋𝐄𝐃**", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="𝐈𝐍𝐕𝐄𝐍𝐓𝐎𝐑𝐘 𝐂𝐋𝐄𝐀𝐑𝐄𝐃",
                description=f"**𝐔𝐬𝐞𝐫:** {user.mention}\n**𝐈𝐭𝐞𝐦𝐬 𝐑𝐞𝐦𝐨𝐯𝐞𝐝:** {len(inventory['items'])}",
                color=0x2B2D31
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"**𝐄𝐑𝐑𝐎𝐑**\n{e}", ephemeral=True)

    @app_commands.command(name="addweekly", description="Add to weekly pool")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def addweekly(self, interaction: discord.Interaction, amount: float):
        if not (self.has_owner_role(interaction) or self.has_manager_role(interaction)):
            await interaction.response.send_message("**𝐎𝐖𝐍𝐄𝐑/𝐌𝐀𝐍𝐀𝐆𝐄𝐑 𝐎𝐍𝐋𝐘**", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("**𝐈𝐍𝐕𝐀𝐋𝐈𝐃 𝐀𝐌𝐎𝐔𝐍𝐓**", ephemeral=True)
            return

        try:
            new_weekly = await self.bot.db.add_to_weekly_pool(amount)
            
            embed = discord.Embed(
                title="𝐖𝐄𝐄𝐊𝐋𝐘 𝐏𝐎𝐎𝐋 𝐔𝐏𝐃𝐀𝐓𝐄𝐃",
                description=f"**𝐀𝐝𝐝𝐞𝐝:** {amount:.2f} 𝐁𝐒𝐓\n**𝐍𝐞𝐰 𝐓𝐨𝐭𝐚𝐥:** {new_weekly:.2f} 𝐁𝐒𝐓",
                color=0x2B2D31
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"**𝐄𝐑𝐑𝐎𝐑**\n{e}", ephemeral=True)

    @app_commands.command(name="removeweekly", description="Remove from weekly pool")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def removeweekly(self, interaction: discord.Interaction, amount: float):
        if not (self.has_owner_role(interaction) or self.has_manager_role(interaction)):
            await interaction.response.send_message("**𝐎𝐖𝐍𝐄𝐑/𝐌𝐀𝐍𝐀𝐆𝐄𝐑 𝐎𝐍𝐋𝐘**", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("**𝐈𝐍𝐕𝐀𝐋𝐈𝐃 𝐀𝐌𝐎𝐔𝐍𝐓**", ephemeral=True)
            return

        try:
            weekly_balance = await self.bot.db.get_weekly_pool()
            
            if weekly_balance < amount:
                await interaction.response.send_message(
                    f"**𝐈𝐍𝐒𝐔𝐅𝐅𝐈𝐂𝐈𝐄𝐍𝐓**\n{weekly_balance:.2f} 𝐁𝐒𝐓",
                    ephemeral=True
                )
                return
            
            new_weekly = await self.bot.db.remove_from_weekly_pool(amount)
            
            if new_weekly is None:
                await interaction.response.send_message("**𝐅𝐀𝐈𝐋𝐄𝐃**", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="𝐖𝐄𝐄𝐊𝐋𝐘 𝐏𝐎𝐎𝐋 𝐔𝐏𝐃𝐀𝐓𝐄𝐃",
                description=f"**𝐑𝐞𝐦𝐨𝐯𝐞𝐝:** {amount:.2f} 𝐁𝐒𝐓\n**𝐍𝐞𝐰 𝐓𝐨𝐭𝐚𝐥:** {new_weekly:.2f} 𝐁𝐒𝐓",
                color=0x2B2D31
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"**𝐄𝐑𝐑𝐎𝐑**\n{e}", ephemeral=True)

    @app_commands.command(name="resetweekly", description="Reset weekly pool")
    @app_commands.guilds(discord.Object(id=int(os.getenv('GUILD_ID'))))
    async def resetweekly(self, interaction: discord.Interaction, amount: float = 10.0):
        if not (self.has_owner_role(interaction) or self.has_manager_role(interaction)):
            await interaction.response.send_message("**𝐎𝐖𝐍𝐄𝐑/𝐌𝐀𝐍𝐀𝐆𝐄𝐑 𝐎𝐍𝐋𝐘**", ephemeral=True)
            return

        try:
            old_weekly = await self.bot.db.get_weekly_pool()
            await self.bot.db.reset_weekly_pool(amount)
            
            embed = discord.Embed(
                title="𝐖𝐄𝐄𝐊𝐋𝐘 𝐏𝐎𝐎𝐋 𝐑𝐄𝐒𝐄𝐓",
                description=f"**𝐏𝐫𝐞𝐯𝐢𝐨𝐮𝐬:** {old_weekly:.2f} 𝐁𝐒𝐓\n**𝐍𝐞𝐰:** {amount:.2f} 𝐁𝐒𝐓",
                color=0x2B2D31
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"**𝐄𝐑𝐑𝐎𝐑**\n{e}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Admin(bot))
