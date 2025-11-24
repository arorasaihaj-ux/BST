import discord
import asyncio
from typing import Optional, List
import config

async def send_error(ctx_or_interaction, message: str):
    """Send an error message"""
    embed = discord.Embed(
        description=config.Design.small_caps(message),
        color=config.Colors.ERROR
    )
    
    if isinstance(ctx_or_interaction, discord.Interaction):
        if ctx_or_interaction.response.is_done():
            await ctx_or_interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await ctx_or_interaction.send(embed=embed, ephemeral=True)

async def send_success(ctx_or_interaction, message: str):
    """Send a success message"""
    embed = discord.Embed(
        description=config.Design.small_caps(message),
        color=config.Colors.SUCCESS
    )
    
    if isinstance(ctx_or_interaction, discord.Interaction):
        if ctx_or_interaction.response.is_done():
            await ctx_or_interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await ctx_or_interaction.send(embed=embed, ephemeral=True)

async def send_info(ctx_or_interaction, message: str):
    """Send an info message"""
    embed = discord.Embed(
        description=config.Design.small_caps(message),
        color=config.Colors.INFO
    )
    
    if isinstance(ctx_or_interaction, discord.Interaction):
        if ctx_or_interaction.response.is_done():
            await ctx_or_interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await ctx_or_interaction.send(embed=embed, ephemeral=True)

def format_bst(amount: float) -> str:
    """Format BST amount consistently"""
    return f"{amount:.2f} BST"

def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text to max length"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

async def confirm_action(ctx, message: str, timeout: int = 30) -> bool:
    """
    Ask user to confirm an action
    
    Returns:
        bool: True if confirmed, False otherwise
    """
    embed = discord.Embed(
        description=f"{config.Design.small_caps(message)}\n\n{config.Design.small_caps('react to confirm')}",
        color=config.Colors.WARNING
    )
    
    view = ConfirmView(timeout=timeout)
    msg = await ctx.send(embed=embed, view=view)
    
    await view.wait()
    
    await msg.delete()
    
    return view.value

class ConfirmView(discord.ui.View):
    def __init__(self, timeout: int = 30):
        super().__init__(timeout=timeout)
        self.value = None
    
    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()
        await interaction.response.defer()
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()
        await interaction.response.defer()

class Paginator:
    """Simple pagination for embeds"""
    def __init__(self, items: List, per_page: int = 10):
        self.items = items
        self.per_page = per_page
        self.pages = [items[i:i + per_page] for i in range(0, len(items), per_page)]
        self.current_page = 0
    
    def get_page(self, page: int) -> List:
        """Get specific page"""
        if 0 <= page < len(self.pages):
            self.current_page = page
            return self.pages[page]
        return []
    
    def next_page(self) -> Optional[List]:
        """Get next page"""
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            return self.pages[self.current_page]
        return None
    
    def prev_page(self) -> Optional[List]:
        """Get previous page"""
        if self.current_page > 0:
            self.current_page -= 1
            return self.pages[self.current_page]
        return None
    
    @property
    def total_pages(self) -> int:
        return len(self.pages)