import asyncpg
import config
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

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
    
    # ==================== TICKET OPERATIONS ====================
    
    async def create_ticket(self, creator_id: int, channel_id: int) -> int:
        """Create a new ticket and return ticket number"""
        async with self.pool.acquire() as conn:
            ticket_number = await conn.fetchval(
                """INSERT INTO tickets (ticket_number, creator_id, channel_id, status)
                   VALUES (nextval('ticket_number_seq'), $1, $2, 'pending')
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
            # Deduct BST if prize is BST
            if prize_type == 'bst':
                balance = await self.get_balance(host_id)
                if balance < prize_amount:
                    return None
                await self.update_balance(host_id, prize_amount, 'subtract')
            
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
                return False  # Already entered
    
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
                # Get item
                item = await conn.fetchrow(
                    "SELECT * FROM shop_items WHERE shop_item_id = $1 FOR UPDATE",
                    item_id
                )
                
                if not item or not item['is_active']:
                    return {'success': False, 'error': 'Item not available'}
                
                if item['stock'] == 0:
                    return {'success': False, 'error': 'Out of stock'}
                
                # Check balance
                balance = await self.get_balance(buyer_id)
                price = float(item['price_bst'])
                
                if balance < price:
                    return {'success': False, 'error': 'Insufficient balance'}
                
                # Deduct balance
                await self.update_balance(buyer_id, price, 'subtract')
                
                # Decrement stock (if not unlimited)
                if item['stock'] != -1:
                    await conn.execute(
                        "UPDATE shop_items SET stock = stock - 1 WHERE shop_item_id = $1",
                        item_id
                    )
                
                # Log purchase
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
    
    # ==================== BOX OPERATIONS ====================
    
    async def get_box_types(self) -> List[Dict]:
        """Get all box types"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM box_types ORDER BY cost_bst")
            return [dict(row) for row in rows]
    
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

# Global database instance
db = Database()