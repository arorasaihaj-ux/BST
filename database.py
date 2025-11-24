import asyncpg
import config
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import random

class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """Initialize database connection pool"""
        self.pool = await asyncpg.create_pool(
            config.DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=60
        )
        print("✓ Database connected")
    
    async def close(self):
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()
            print("✓ Database disconnected")
    
    # ==================== USER OPERATIONS ====================
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user data or create if doesn't exist"""
        async with self.pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT * FROM users WHERE user_id = $1",
                user_id
            )
            if not user:
                await conn.execute(
                    """INSERT INTO users (user_id, bst_balance, total_messages, weekly_bst_earned)
                       VALUES ($1, 0, 0, 0)""",
                    user_id
                )
                user = await conn.fetchrow(
                    "SELECT * FROM users WHERE user_id = $1",
                    user_id
                )
            return dict(user) if user else None
    
    async def update_balance(self, user_id: int, amount: float, operation: str = 'add'):
        """Update user BST balance"""
        async with self.pool.acquire() as conn:
            if operation == 'add':
                await conn.execute(
                    "UPDATE users SET bst_balance = bst_balance + $1, updated_at = NOW() WHERE user_id = $2",
                    amount, user_id
                )
            elif operation == 'subtract':
                await conn.execute(
                    "UPDATE users SET bst_balance = bst_balance - $1, updated_at = NOW() WHERE user_id = $2",
                    amount, user_id
                )
            elif operation == 'set':
                await conn.execute(
                    "UPDATE users SET bst_balance = $1, updated_at = NOW() WHERE user_id = $2",
                    amount, user_id
                )
    
    async def get_balance(self, user_id: int) -> float:
        """Get user's BST balance"""
        user = await self.get_user(user_id)
        return float(user['bst_balance']) if user else 0.0
    
    async def increment_messages(self, user_id: int) -> float:
        """Increment message count and award BST if applicable"""
        async with self.pool.acquire() as conn:
            # Get or create user
            user = await self.get_user(user_id)
            
            # Check weekly cap
            if float(user['weekly_bst_earned']) >= config.WEEKLY_MESSAGE_CAP:
                return 0.0
            
            # Increment message count
            new_count = user['total_messages'] + 1
            await conn.execute(
                "UPDATE users SET total_messages = $1, updated_at = NOW() WHERE user_id = $2",
                new_count, user_id
            )
            
            # Check if eligible for BST
            if new_count % config.MESSAGES_FOR_BST == 0:
                bst_to_award = config.BST_PER_100_MESSAGES
                
                # Check if it would exceed weekly cap
                potential_total = float(user['weekly_bst_earned']) + bst_to_award
                if potential_total > config.WEEKLY_MESSAGE_CAP:
                    bst_to_award = config.WEEKLY_MESSAGE_CAP - float(user['weekly_bst_earned'])
                
                if bst_to_award > 0:
                    await conn.execute(
                        """UPDATE users 
                           SET bst_balance = bst_balance + $1, 
                               weekly_bst_earned = weekly_bst_earned + $1,
                               updated_at = NOW()
                           WHERE user_id = $2""",
                        bst_to_award, user_id
                    )
                    return bst_to_award
            
            return 0.0
    
    async def reset_weekly_caps(self):
        """Reset weekly BST caps for all users"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """UPDATE users 
                   SET weekly_bst_earned = 0, 
                       weekly_reset_date = NOW()
                   WHERE weekly_reset_date < NOW() - INTERVAL '7 days'"""
            )
    
    # ==================== BOX OPERATIONS ====================
    
    async def get_box_types(self) -> List[Dict]:
        """Get all box types"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM box_types ORDER BY cost_bst")
            return [dict(row) for row in rows]
    
    async def purchase_box(self, user_id: int, box_type_id: str) -> Dict:
        """Purchase a mystery box"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Get box type
                box_type = await conn.fetchrow(
                    "SELECT * FROM box_types WHERE box_type_id = $1 FOR UPDATE",
                    box_type_id
                )
                
                if not box_type:
                    return {'success': False, 'error': 'Box type not found'}
                
                # Check supply
                if box_type['released'] >= box_type['initial_release']:
                    return {'success': False, 'error': 'Out of stock'}
                
                # Check balance
                balance = await self.get_balance(user_id)
                cost = float(box_type['cost_bst'])
                
                if balance < cost:
                    return {'success': False, 'error': 'Insufficient balance'}
                
                # Deduct balance
                await conn.execute(
                    "UPDATE users SET bst_balance = bst_balance - $1, updated_at = NOW() WHERE user_id = $2",
                    cost, user_id
                )
                
                # Increment released count
                await conn.execute(
                    "UPDATE box_types SET released = released + 1 WHERE box_type_id = $1",
                    box_type_id
                )
                
                # Create box
                box_id = await conn.fetchval(
                    """INSERT INTO boxes (box_type_id, owner_user_id, source, status)
                       VALUES ($1, $2, 'purchase', 'stored')
                       RETURNING box_id""",
                    box_type_id, user_id
                )
                
                # Log transaction
                await conn.execute(
                    """INSERT INTO transactions (tx_type, from_user, to_user, amount_bst, item_data)
                       VALUES ('purchase', $1, NULL, $2, $3)""",
                    user_id, cost, {'box_id': str(box_id), 'box_type': box_type['name']}
                )
                
                return {
                    'success': True,
                    'box_id': str(box_id),
                    'box_name': box_type['name'],
                    'cost': cost,
                    'new_balance': balance - cost
                }
    
    async def get_user_boxes(self, user_id: int) -> List[Dict]:
        """Get user's stored boxes"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT b.box_id, bt.box_type_id, bt.name, bt.sell_value
                   FROM boxes b
                   JOIN box_types bt ON b.box_type_id = bt.box_type_id
                   WHERE b.owner_user_id = $1 AND b.status = 'stored'
                   ORDER BY bt.cost_bst DESC""",
                user_id
            )
            return [dict(row) for row in rows]
    
    async def open_box(self, box_id: str, user_id: int, reward_item: str, roll_value: float, odds: list) -> Dict:
        """Open a mystery box and award item"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Verify box ownership and status
                box = await conn.fetchrow(
                    """SELECT b.*, bt.box_type_id
                       FROM boxes b
                       JOIN box_types bt ON b.box_type_id = bt.box_type_id
                       WHERE b.box_id = $1 AND b.owner_user_id = $2 AND b.status = 'stored'
                       FOR UPDATE""",
                    box_id, user_id
                )
                
                if not box:
                    return {'success': False, 'error': 'Box not found or already opened'}
                
                # Mark box as opened
                await conn.execute(
                    "UPDATE boxes SET status = 'opened', opened_at = NOW() WHERE box_id = $1",
                    box_id
                )
                
                # Find the item
                item = await conn.fetchrow(
                    "SELECT * FROM items WHERE name = $1",
                    reward_item
                )
                
                if not item:
                    # Log the opening without item
                    await conn.execute(
                        """INSERT INTO open_logs (user_id, box_id, box_type_id, reward_name, roll_value, odds_used)
                           VALUES ($1, $2, $3, $4, $5, $6)""",
                        user_id, box_id, box['box_type_id'], reward_item, roll_value, odds
                    )
                    return {'success': True, 'box_name': 'Mystery Box', 'reward': reward_item, 'item_value': 0}
                
                # Add item to user's inventory
                existing = await conn.fetchrow(
                    "SELECT user_item_id, quantity FROM user_items WHERE user_id = $1 AND item_id = $2",
                    user_id, item['item_id']
                )
                
                if existing:
                    await conn.execute(
                        "UPDATE user_items SET quantity = quantity + 1 WHERE user_item_id = $1",
                        existing['user_item_id']
                    )
                else:
                    await conn.execute(
                        """INSERT INTO user_items (user_id, item_id, quantity, source_box_id)
                           VALUES ($1, $2, 1, $3)""",
                        user_id, item['item_id'], box_id
                    )
                
                # Log the opening
                await conn.execute(
                    """INSERT INTO open_logs (user_id, box_id, box_type_id, reward_item_id, reward_name, roll_value, odds_used)
                       VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                    user_id, box_id, box['box_type_id'], item['item_id'], reward_item, roll_value, odds
                )
                
                return {
                    'success': True,
                    'box_name': 'Mystery Box',
                    'reward': reward_item,
                    'item_value': float(item['value_usd'])
                }
    
    async def get_user_inventory(self, user_id: int) -> Dict:
        """Get user's complete inventory"""
        async with self.pool.acquire() as conn:
            # Get boxes
            boxes = await conn.fetch(
                """SELECT bt.name, bt.short_name, COUNT(*) as count
                   FROM boxes b
                   JOIN box_types bt ON b.box_type_id = bt.box_type_id
                   WHERE b.owner_user_id = $1 AND b.status = 'stored'
                   GROUP BY bt.name, bt.short_name
                   ORDER BY bt.cost_bst DESC""",
                user_id
            )
            
            # Get items
            items = await conn.fetch(
                """SELECT i.name, i.short_name, i.value_usd, SUM(ui.quantity) as quantity
                   FROM user_items ui
                   JOIN items i ON ui.item_id = i.item_id
                   WHERE ui.user_id = $1
                   GROUP BY i.item_id, i.name, i.short_name, i.value_usd
                   ORDER BY i.value_usd DESC""",
                user_id
            )
            
            return {
                'boxes': [dict(row) for row in boxes],
                'items': [dict(row) for row in items]
            }
    
    # ==================== TICKET OPERATIONS ====================
    
    async def create_ticket(self, creator_id: int, channel_id: int) -> int:
        """Create a new ticket and return ticket number"""
        async with self.pool.acquire() as conn:
            ticket_number = await conn.fetchval(
                """INSERT INTO tickets (creator_id, channel_id, status)
                   VALUES ($1, $2, 'pending')
                   RETURNING ticket_number""",
                creator_id, channel_id
            )
            return ticket_number
    
    async def get_ticket_by_channel(self, channel_id: int) -> Optional[Dict]:
        """Get ticket by channel ID"""
        async with self.pool.acquire() as conn:
            ticket = await conn.fetchrow(
                "SELECT * FROM tickets WHERE channel_id = $1",
                channel_id
            )
            return dict(ticket) if ticket else None
    
    async def add_partner_to_ticket(self, ticket_number: int, partner_id: int):
        """Add partner to ticket"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE tickets SET partner_id = $1, status = 'active' WHERE ticket_number = $2",
                partner_id, ticket_number
            )
    
    # ==================== GIVEAWAY OPERATIONS ====================
    
    async def create_giveaway(self, host_id: int, prize_type: str, prize_amount: float,
                             prize_item_name: str, winners_count: int, duration_minutes: int,
                             channel_id: int, required_role: Optional[int] = None) -> str:
        """Create a giveaway"""
        async with self.pool.acquire() as conn:
            ends_at = datetime.now() + timedelta(minutes=duration_minutes)
            
            giveaway_id = await conn.fetchval(
                """INSERT INTO giveaways 
                   (host_id, prize_type, prize_amount, prize_item_name, winners_count, 
                    required_role, duration_minutes, channel_id, ends_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                   RETURNING giveaway_id""",
                host_id, prize_type, prize_amount, prize_item_name, winners_count,
                required_role, duration_minutes, channel_id, ends_at
            )
            return str(giveaway_id)
    
    async def enter_giveaway(self, giveaway_id: str, user_id: int) -> bool:
        """Enter a user into a giveaway"""
        async with self.pool.acquire() as conn:
            try:
                await conn.execute(
                    """INSERT INTO giveaway_entries (giveaway_id, user_id)
                       VALUES ($1, $2)""",
                    giveaway_id, user_id
                )
                return True
            except:
                return False
    
    # ==================== SHOP OPERATIONS ====================
    
    async def create_shop_item(self, name: str, description: str, price: float,
                               stock: int, created_by: int) -> str:
        """Create a shop item"""
        async with self.pool.acquire() as conn:
            item_id = await conn.fetchval(
                """INSERT INTO shop_items (name, description, price_bst, stock, created_by)
                   VALUES ($1, $2, $3, $4, $5)
                   RETURNING shop_item_id""",
                name, description, price, stock, created_by
            )
            return str(item_id)
    
    async def get_shop_items(self) -> List[Dict]:
        """Get all active shop items"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT * FROM shop_items 
                   WHERE is_active = TRUE 
                   AND (stock > 0 OR stock = -1)
                   ORDER BY created_at DESC"""
            )
            return [dict(row) for row in rows]
    
    async def purchase_shop_item(self, item_id: str, buyer_id: int) -> Dict:
        """Purchase a shop item"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                item = await conn.fetchrow(
                    "SELECT * FROM shop_items WHERE shop_item_id = $1 FOR UPDATE",
                    item_id
                )
                
                if not item or not item['is_active']:
                    return {'success': False, 'error': 'Item not available'}
                
                if item['stock'] == 0:
                    return {'success': False, 'error': 'Out of stock'}
                
                balance = await self.get_balance(buyer_id)
                price = float(item['price_bst'])
                
                if balance < price:
                    return {'success': False, 'error': 'Insufficient balance'}
                
                await self.update_balance(buyer_id, price, 'subtract')
                
                if item['stock'] != -1:
                    await conn.execute(
                        "UPDATE shop_items SET stock = stock - 1 WHERE shop_item_id = $1",
                        item_id
                    )
                
                await conn.execute(
                    """INSERT INTO shop_purchases (shop_item_id, buyer_id, price_paid)
                       VALUES ($1, $2, $3)""",
                    item_id, buyer_id, price
                )
                
                return {
                    'success': True,
                    'item_name': item['name'],
                    'price': price,
                    'new_balance': balance - price
                }
    
    # ==================== LOGGING ====================
    
    async def log_transaction(self, tx_type: str, from_user: int, to_user: int, 
                              amount: float, metadata: dict = None):
        """Log a transaction"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO transactions (tx_type, from_user, to_user, amount_bst, metadata)
                   VALUES ($1, $2, $3, $4, $5)""",
                tx_type, from_user, to_user, amount, metadata or {}
            )
    
    async def log_action(self, actor_id: int, action: str, target_user_id: int = None, 
                        details: dict = None):
        """Log an admin action"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO logs (actor_id, action, target_user_id, details)
                   VALUES ($1, $2, $3, $4)""",
                actor_id, action, target_user_id, details or {}
            )

# Global database instance
db = Database()
