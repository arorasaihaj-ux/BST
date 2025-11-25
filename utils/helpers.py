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
    
    if hasattr(ctx_or_interaction, 'response'):
        await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await ctx_or_interaction.send(embed=embed, ephemeral=True)

async def send_success(ctx_or_interaction, message: str):
    """Send a success message"""
    embed = discord.Embed(
        description=config.Design.small_caps(message),
        color=config.Colors.SUCCESS
    )
    
    if hasattr(ctx_or_interaction, 'response'):
        await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await ctx_or_interaction.send(embed=embed, ephemeral=True)

async def send_warning(ctx_or_interaction, message: str):
    """Send a warning message"""
    embed = discord.Embed(
        description=config.Design.small_caps(message),
        color=config.Colors.WARNING
    )
    
    if hasattr(ctx_or_interaction, 'response'):
        await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await ctx_or_interaction.send(embed=embed, ephemeral=True)

def format_bst_amount(amount: float) -> str:
    """Format BST amount with proper decimal places"""
    return f"{amount:.2f}"

def format_large_number(number: int) -> str:
    """Format large numbers with commas"""
    return f"{number:,}"

async def paginate_embeds(ctx, embeds: List[discord.Embed], timeout: int = 60):
    """Paginate through multiple embeds"""
    if not embeds:
        return
    
    current_page = 0
    
    # Create view with navigation buttons
    class PaginationView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=timeout)
            self.current_page = 0
            self.embeds = embeds
        
        @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
        async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.current_page > 0:
                self.current_page -= 1
                await interaction.response.edit_message(embed=self.embeds[self.current_page])
        
        @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
        async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.current_page < len(self.embeds) - 1:
                self.current_page += 1
                await interaction.response.edit_message(embed=self.embeds[self.current_page])
        
        @discord.ui.button(label="❌", style=discord.ButtonStyle.danger)
        async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.defer()
            await interaction.delete_original_response()
            self.stop()
    
    view = PaginationView()
    message = await ctx.send(embed=embeds[0], view=view)
    
    # Wait for timeout
    await asyncio.sleep(timeout)
    try:
        await message.edit(view=None)
    except:
        pass

def create_progress_bar(progress: float, total: float, length: int = 20) -> str:
    """Create a visual progress bar"""
    if total == 0:
        return "[" + " " * length + "]"
    
    percentage = min(progress / total, 1.0)
    filled = int(length * percentage)
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}] {percentage:.1%}"

async def get_user_display(user_id: int, bot) -> str:
    """Get user display name from user ID"""
    user = bot.get_user(user_id)
    if user:
        return user.display_name
    return f"User {user_id}"

def safe_divide(numerator: float, denominator: float) -> float:
    """Safely divide two numbers, return 0 if denominator is 0"""
    if denominator == 0:
        return 0.0
    return numerator / denominator

class TimeConverter:
    """Convert time strings to seconds"""
    
    @staticmethod
    def to_seconds(time_str: str) -> Optional[int]:
        """Convert time string to seconds"""
        try:
            time_str = time_str.lower().strip()
            
            if time_str.endswith('s'):
                return int(time_str[:-1])
            elif time_str.endswith('m'):
                return int(time_str[:-1]) * 60
            elif time_str.endswith('h'):
                return int(time_str[:-1]) * 3600
            elif time_str.endswith('d'):
                return int(time_str[:-1]) * 86400
            else:
                # Assume minutes if no unit specified
                return int(time_str) * 60
                
        except (ValueError, AttributeError):
            return None
    
    @staticmethod
    def to_readable(seconds: int) -> str:
        """Convert seconds to readable time"""
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}m"
        elif seconds < 86400:
            return f"{seconds // 3600}h"
        else:
            return f"{seconds // 86400}d"
