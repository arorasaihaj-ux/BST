import discord
from discord.ext import commands
import config

def is_owner():
    """Check if user is the bot owner"""
    async def predicate(ctx):
        return ctx.author.id == config.OWNER_ID
    return commands.check(predicate)

def is_manager():
    """Check if user is a manager or owner"""
    async def predicate(ctx):
        if ctx.author.id == config.OWNER_ID:
            return True
        
        if hasattr(ctx.author, 'roles'):
            manager_roles = config.MANAGER_ROLES
            if any(role.id in manager_roles for role in ctx.author.roles):
                return True
        
        return False
    return commands.check(predicate)

def is_counting_channel():
    """Check if command is used in a counting channel"""
    async def predicate(ctx):
        if not config.COUNTING_CHANNELS:
            return True  # If no channels specified, count everywhere
        
        return ctx.channel.id in config.COUNTING_CHANNELS
    return commands.check(predicate)

def is_command_channel():
    """Check if command is used in the command channel"""
    async def predicate(ctx):
        if not hasattr(config, 'COMMAND_CHANNEL_ID') or not config.COMMAND_CHANNEL_ID:
            return True  # If no command channel specified, allow everywhere
        
        return ctx.channel.id == config.COMMAND_CHANNEL_ID
    return commands.check(predicate)

async def has_permission(user_id: int, permission_level: str, guild = None) -> bool:
    """
    Check if user has specific permission level
    
    Args:
        user_id: Discord user ID
        permission_level: 'owner', 'manager', or 'user'
        guild: Discord guild object (for role checks)
    
    Returns:
        bool: True if user has permission
    """
    if permission_level == 'owner':
        return user_id == config.OWNER_ID
    
    if permission_level == 'manager':
        if user_id == config.OWNER_ID:
            return True
        
        # For role-based checks, we need the guild context
        if guild:
            member = guild.get_member(user_id)
            if member and any(role.id in config.MANAGER_ROLES for role in member.roles):
                return True
    
    return True  # All users have 'user' permission
