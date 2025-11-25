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
COMMAND_CHANNEL_ID = int(os.getenv('COMMAND_CHANNEL_ID', 0))
COUNTING_CHANNELS = [int(x.strip()) for x in os.getenv('COUNTING_CHANNELS', '').split(',') if x.strip()]
TICKET_CATEGORY_ID = int(os.getenv('TICKET_CATEGORY_ID', 0))
TICKET_SETUP_CHANNEL_ID = int(os.getenv('TICKET_SETUP_CHANNEL_ID', 0))
GIVEAWAY_CHANNEL_ID = int(os.getenv('GIVEAWAY_CHANNEL_ID', 0))
SHOP_CHANNEL_ID = int(os.getenv('SHOP_CHANNEL_ID', 0))

# Role IDs
MANAGER_ROLES = [int(x.strip()) for x in os.getenv('MANAGER_ROLES', '').split(',') if x.strip()]

# Economy Settings
MESSAGES_FOR_BST = int(os.getenv('MESSAGES_FOR_BST', 100))
BST_PER_100_MESSAGES = float(os.getenv('BST_PER_100_MESSAGES', 0.23))
WEEKLY_MESSAGE_CAP = float(os.getenv('WEEKLY_MESSAGE_CAP', 10.0))
DAILY_REWARD = float(os.getenv('DAILY_REWARD', 0.5))

# Permission Levels
class Permissions:
    OWNER_ONLY_COMMANDS = [
        'mint', 'releaseboxes', 'setboxprice', 'setmessagevalue',
        'setweeklycap', 'economystats', 'resetuser'
    ]
    
    MANAGER_COMMANDS = [
        'addpoints', 'removepoints', 'resetbst', 'listitem',
        'removeshopitem', 'restockshop', 'createevent'
    ]

# Design System
class Colors:
    PRIMARY = 0x1a1a1a
    SECONDARY = 0x2d2d2d
    SUCCESS = 0x00c853
    WARNING = 0xff6d00
    ERROR = 0xd50000
    INFO = 0x2979ff

class Design:
    @staticmethod
    def header(text, width=40):
        return f"**{text.upper()}**\n{'─' * width}"
    
    @staticmethod
    def section(text):
        return f"**{text}**"
    
    @staticmethod
    def field(key, value, width=15):
        spaces = ' ' * (width - len(key))
        return f"**{key}:**{spaces} `{value}`"
    
    @staticmethod
    def item(name, quantity):
        return f"• {name} {quantity}"
    
    @staticmethod
    def small_caps(text):
        return f"**{text.upper()}**"
    
    @staticmethod
    def panel_border():
        return "╔══════════════════════════════════════╗"
    
    @staticmethod
    def panel_divider():
        return "╠══════════════════════════════════════╣"
    
    @staticmethod
    def panel_footer():
        return "╚══════════════════════════════════════╝"
    
    @staticmethod
    def warning(text):
        return f"⚠️ **{text}**"
    
    @staticmethod
    def success(text):
        return f"✅ **{text}**"
    
    @staticmethod
    def error(text):
        return f"❌ **{text}**"

# Box Configuration
BOX_TYPES = {
    "base": {
        "name": "Base Mystery Box",
        "cost": 1.0,
        "initial_supply": 30,
        "drops": [
            {"item": "Taco Block", "chance": 40.0},
            {"item": "Los Lucky Block", "chance": 40.0},
            {"item": "40 Robux", "chance": 15.0},
            {"item": "Ques Croc", "chance": 2.5},
            {"item": "Base 67", "chance": 2.5}
        ]
    },
    "gold": {
        "name": "Gold Mystery Box", 
        "cost": 2.5,
        "initial_supply": 15,
        "drops": [
            {"item": "Los Lucky Block", "chance": 50.0},
            {"item": "Miet Bike", "chance": 30.0},
            {"item": "80 Robux", "chance": 15.0},
            {"item": "La Combination", "chance": 3.0},
            {"item": "La Grande Combi", "chance": 1.0},
            {"item": "400 Robux", "chance": 1.0}
        ]
    }
}
