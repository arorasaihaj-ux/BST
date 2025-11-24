import os
from dotenv import load_dotenv

load_dotenv()

# Discord Configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID', 0))
GUILD_ID = int(os.getenv('GUILD_ID', 0))

# Database Configuration
DATABASE_URL = os.getenv('DATABASE_URL')

# Channel IDs
COMMAND_CHANNEL_ID = int(os.getenv('COMMAND_CHANNEL_ID', 0)) if os.getenv('COMMAND_CHANNEL_ID') else None
TICKET_CATEGORY_ID = int(os.getenv('TICKET_CATEGORY_ID', 0)) if os.getenv('TICKET_CATEGORY_ID') else None
TICKET_SETUP_CHANNEL_ID = int(os.getenv('TICKET_SETUP_CHANNEL_ID', 0)) if os.getenv('TICKET_SETUP_CHANNEL_ID') else None

# Counting Channels (messages earn BST)
COUNTING_CHANNELS = [
    int(ch) for ch in os.getenv('COUNTING_CHANNELS', '').split(',') if ch.strip()
]

# Manager Role IDs
MANAGER_ROLES = [
    int(role) for role in os.getenv('MANAGER_ROLES', '').split(',') if role.strip()
]

# Economy Settings
MESSAGES_FOR_BST = int(os.getenv('MESSAGES_FOR_BST', 100))
BST_PER_100_MESSAGES = float(os.getenv('BST_PER_100_MESSAGES', 0.23))
WEEKLY_MESSAGE_CAP = float(os.getenv('WEEKLY_MESSAGE_CAP', 10.0))

# Bot Prefix
PREFIX = os.getenv('PREFIX', '"')

# Design System - Unicode Characters
class Design:
    # Box Drawing
    TOP_LEFT = '┏'
    TOP_RIGHT = '┓'
    BOTTOM_LEFT = '┗'
    BOTTOM_RIGHT = '┛'
    HORIZONTAL = '━'
    VERTICAL = '┃'
    
    # Bullets
    ARROW = '▸'
    DOT = '•'
    
    # Typography Functions
    @staticmethod
    def bold(text):
        """Convert text to bold unicode"""
        bold_map = {
            'A': '𝗔', 'B': '𝗕', 'C': '𝗖', 'D': '𝗗', 'E': '𝗘', 'F': '𝗙', 'G': '𝗚', 'H': '𝗛',
            'I': '𝗜', 'J': '𝗝', 'K': '𝗞', 'L': '𝗟', 'M': '𝗠', 'N': '𝗡', 'O': '𝗢', 'P': '𝗣',
            'Q': '𝗤', 'R': '𝗥', 'S': '𝗦', 'T': '𝗧', 'U': '𝗨', 'V': '𝗩', 'W': '𝗪', 'X': '𝗫',
            'Y': '𝗬', 'Z': '𝗭', '0': '𝟬', '1': '𝟭', '2': '𝟮', '3': '𝟯', '4': '𝟰',
            '5': '𝟱', '6': '𝟲', '7': '𝟳', '8': '𝟴', '9': '𝟵', '.': '.'
        }
        return ''.join(bold_map.get(c.upper(), c) for c in text)
    
    @staticmethod
    def small_caps(text):
        """Convert text to small caps"""
        small_map = {
            'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ғ', 'g': 'ɢ', 'h': 'ʜ',
            'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ', 'o': 'ᴏ', 'p': 'ᴘ',
            'q': 'ǫ', 'r': 'ʀ', 's': 's', 't': 'ᴛ', 'u': 'ᴜ', 'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x',
            'y': 'ʏ', 'z': 'ᴢ'
        }
        return ''.join(small_map.get(c.lower(), c) for c in text)
    
    @staticmethod
    def header(text, width=30):
        """Create a boxed header"""
        top = f"{Design.TOP_LEFT}{Design.HORIZONTAL * width}{Design.TOP_RIGHT}"
        middle = f"{Design.VERTICAL} {Design.bold(text):<{width}} {Design.VERTICAL}"
        bottom = f"{Design.BOTTOM_LEFT}{Design.HORIZONTAL * width}{Design.BOTTOM_RIGHT}"
        return f"{top}\n{middle}\n{bottom}"
    
    @staticmethod
    def section(title):
        """Create a section header"""
        return f"\n{Design.bold(title)}"
    
    @staticmethod
    def field(label, value, width=20):
        """Create a label-value field"""
        label_formatted = Design.small_caps(label)
        value_formatted = Design.bold(str(value))
        return f"{label_formatted:<{width}} {value_formatted}"
    
    @staticmethod
    def item(name, value=None):
        """Create a list item"""
        if value:
            return f"{Design.ARROW} {name}  {Design.DOT}  {value}"
        return f"{Design.ARROW} {name}"
    
    @staticmethod
    def divider(width=28):
        """Create a divider line"""
        return Design.HORIZONTAL * width

# Color Scheme
class Colors:
    PRIMARY = 0x2F3136    # Dark gray
    SUCCESS = 0x43B581    # Green
    ERROR = 0xF04747      # Red
    WARNING = 0xFAA61A    # Orange
    INFO = 0x5865F2       # Blurple
    YELLOW = 0xFEE75C     # Yellow