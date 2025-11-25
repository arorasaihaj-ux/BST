import asyncpg
import config
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import random

class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self._connected = False

    async def connect(self):
        """Initialize database connection pool with pgbouncer fix"""
        try:
            if not config.DATABASE_URL:
                raise Exception("DATABASE_URL not found in environment variables")
                
            self.pool = await asyncpg.create_pool(
                config.DATABASE_URL,
                min_size=1,
                max_size=5,
                statement_cache_size=0  # Fix for pgbouncer
            )
            self._connected = True
            print("✓ Database connected")
        except Exception as e:
            print(f"✗ Database connection error: {e}")
            self._connected = False
            raise

    async def close(self):
        """Close database connection"""
        if self.pool:
            await self.pool.close()
            self._connected = False
            print("✓ Database disconnected")

    def _ensure_connected(self):
        """Ensure database is connected before operations"""
        if not self._connected or not self.pool:
            raise Exception("Database not connected. Please ensure the bot has started properly.")

    # User Operations
    async def get_user(self, user_id: int) -> Dict[str, Any]:
        """Get or create user"""
        self._ensure_connected()
        async with self.pool.acquire() as conn:
            user = await conn.fetchrow("""
                INSERT INTO users (user_id, discord_tag, bst_balance, total_messages, weekly_messages, last_active)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (user_id) DO UPDATE SET
                    discord_tag = EXCLUDED.discord_tag,
                    last_active = EXCLUDED.last_active
                RETURNING *
            """, user_id, f"user_{user_id}", 0.0, 0, 0, datetime.utcnow())
            
            return dict(user) if user else None

    async def update_user_balance(self, user_id: int, amount: float) -> bool:
        """Update user BST balance"""
        self._ensure_connected()
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                result = await conn.execute("""
                    UPDATE users 
                    SET bst_balance = bst_balance + $1,
                        last_active = $2
                    WHERE user_id = $3 AND bst_balance + $1 >= 0
                """, amount, datetime.utcnow(), user_id)
                
                return "UPDATE 1" in result

    async def record_message(self, user_id: int, discord_tag: str, channel_id: int) -> bool:
        """Record user message and award BST if eligible"""
        self._ensure_connected()
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Get current week start
                week_start = datetime.utcnow() - timedelta(days=datetime.utcnow().weekday())
                
                # Update message counts
                await conn.execute("""
                    INSERT INTO users (user_id, discord_tag, total_messages, weekly_messages, last_active)
                    VALUES ($1, $2, 1, 1, $3)
                    ON CONFLICT (user_id) DO UPDATE SET
                        discord_tag = EXCLUDED.discord_tag,
                        total_messages = users.total_messages + 1,
                        weekly_messages = CASE 
                            WHEN users.weekly_reset < $4 THEN 1
                            ELSE users.weekly_messages + 1
                        END,
                        weekly_reset = CASE
                            WHEN users.weekly_reset < $4 THEN $4
                            ELSE users.weekly_reset
                        END,
                        last_active = EXCLUDED.last_active
                """, user_id, discord_tag, datetime.utcnow(), week_start)
                
                # Check if eligible for BST
                user = await conn.fetchrow("""
                    SELECT weekly_messages, bst_balance FROM users 
                    WHERE user_id = $1
                """, user_id)
                
                if user and user['weekly_messages'] % config.MESSAGES_FOR_BST == 0:
                    # Check weekly cap
                    weekly_bst = await conn.fetchval("""
                        SELECT COALESCE(SUM(amount_bst), 0) FROM transactions 
                        WHERE user_id = $1 AND tx_type = 'message_reward' 
                        AND created_at >= $2
                    """, user_id, week_start)
                    
                    if weekly_bst < config.WEEKLY_MESSAGE_CAP:
                        bst_earned = config.BST_PER_100_MESSAGES
                        await conn.execute("""
                            UPDATE users SET bst_balance = bst_balance + $1
                            WHERE user_id = $2
                        """, bst_earned, user_id)
                        
                        await conn.execute("""
                            INSERT INTO transactions (user_id, tx_type, amount_bst, metadata)
                            VALUES ($1, 'message_reward', $2, $3)
                        """, user_id, bst_earned, {"channel_id": channel_id, "messages": config.MESSAGES_FOR_BST})
                        
                        return True
                
                return False

    # Box Operations
    async def purchase_box(self, user_id: int, box_type: str) -> Dict[str, Any]:
        """Purchase a mystery box"""
        self._ensure_connected()
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Get box info and check supply
                box_info = config.BOX_TYPES[box_type]
                box_data = await conn.fetchrow("""
                    SELECT released, initial_release FROM box_types 
                    WHERE box_type_id = $1
                """, box_type)
                
                if not box_data or box_data['released'] >= box_data['initial_release']:
                    raise Exception("Box sold out")
                
                # Check user balance
                user = await conn.fetchrow("""
                    SELECT bst_balance FROM users WHERE user_id = $1
                """, user_id)
                
                if not user or user['bst_balance'] < box_info['cost']:
                    raise Exception("Insufficient BST")
                
                # Deduct BST and create box
                await conn.execute("""
                    UPDATE users SET bst_balance = bst_balance - $1
                    WHERE user_id = $2
                """, box_info['cost'], user_id)
                
                # Create box
                box = await conn.fetchrow("""
                    INSERT INTO boxes (box_type_id, owner_user_id, source)
                    VALUES ($1, $2, 'purchase')
                    RETURNING *
                """, box_type, user_id)
                
                # Update released count
                await conn.execute("""
                    UPDATE box_types SET released = released + 1
                    WHERE box_type_id = $1
                """, box_type)
                
                # Record transaction
                await conn.execute("""
                    INSERT INTO transactions (user_id, tx_type, amount_bst, metadata)
                    VALUES ($1, 'box_purchase', $2, $3)
                """, user_id, -box_info['cost'], {"box_type": box_type, "box_id": box['box_id']})
                
                return dict(box)

    async def open_box(self, box_id: str, user_id: int) -> Dict[str, Any]:
        """Open a mystery box and get reward"""
        self._ensure_connected()
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Verify box ownership and status
                box = await conn.fetchrow("""
                    SELECT * FROM boxes 
                    WHERE box_id = $1 AND owner_user_id = $2 AND status = 'owned'
                """, box_id, user_id)
                
                if not box:
                    raise Exception("Box not found or already opened")
                
                # Get box type info
                box_type = box['box_type_id']
                box_info = config.BOX_TYPES[box_type]
                
                # Determine reward using weighted random
                reward = self._get_box_reward(box_info['drops'])
                
                # Get item ID
                item = await conn.fetchrow("""
                    SELECT item_id FROM items WHERE name = $1
                """, reward)
                
                if not item:
                    raise Exception("Item not found in database")
                
                # Add item to user inventory
                await conn.execute("""
                    INSERT INTO user_items (user_id, item_id, obtained_from)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id, item_id) DO UPDATE SET
                        quantity = user_items.quantity + 1
                """, user_id, item['item_id'], box_id)
                
                # Mark box as opened
                await conn.execute("""
                    UPDATE boxes SET status = 'opened', opened_at = $1
                    WHERE box_id = $2
                """, datetime.utcnow(), box_id)
                
                # Record transaction
                await conn.execute("""
                    INSERT INTO transactions (user_id, tx_type, amount_bst, metadata)
                    VALUES ($1, 'box_opened', 0, $2)
                """, user_id, {"box_id": box_id, "reward": reward})
                
                return {"item": reward, "box_type": box_info['name']}

    def _get_box_reward(self, drops: List[Dict]) -> str:
        """Get random reward based on weighted chances"""
        total = sum(drop['chance'] for drop in drops)
        rand = random.uniform(0, total)
        current = 0
        
        for drop in drops:
            current += drop['chance']
            if rand <= current:
                return drop['item']
        
        return drops[0]['item']

    # Inventory Operations
    async def get_user_inventory(self, user_id: int) -> Dict[str, Any]:
        """Get user's boxes and items"""
        self._ensure_connected()
        async with self.pool.acquire() as conn:
            # Get owned boxes
            boxes = await conn.fetch("""
                SELECT b.box_id, bt.name, bt.cost_bst
                FROM boxes b
                JOIN box_types bt ON b.box_type_id = bt.box_type_id
                WHERE b.owner_user_id = $1 AND b.status = 'owned'
            """, user_id)
            
            # Get items with quantities
            items = await conn.fetch("""
                SELECT i.name, i.value_usd, ui.quantity
                FROM user_items ui
                JOIN items i ON ui.item_id = i.item_id
                WHERE ui.user_id = $1 AND ui.quantity > 0
            """, user_id)
            
            return {
                "boxes": [dict(box) for box in boxes],
                "items": [dict(item) for item in items]
            }

    # Shop Operations
    async def get_shop_items(self) -> List[Dict[str, Any]]:
        """Get all available shop items"""
        self._ensure_connected()
        async with self.pool.acquire() as conn:
            items = await conn.fetch("""
                SELECT * FROM shop_items 
                WHERE quantity > 0 AND is_active = true
                ORDER BY price_bst
            """)
            return [dict(item) for item in items]

    async def purchase_shop_item(self, user_id: int, item_id: str) -> Dict[str, Any]:
        """Purchase item from shop"""
        self._ensure_connected()
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Get item details
                item = await conn.fetchrow("""
                    SELECT * FROM shop_items 
                    WHERE item_id = $1 AND quantity > 0 AND is_active = true
                """, item_id)
                
                if not item:
                    raise Exception("Item not available")
                
                # Check user balance
                user = await conn.fetchrow("""
                    SELECT bst_balance FROM users WHERE user_id = $1
                """, user_id)
                
                if not user or user['bst_balance'] < item['price_bst']:
                    raise Exception("Insufficient BST")
                
                # Deduct BST
                await conn.execute("""
                    UPDATE users SET bst_balance = bst_balance - $1
                    WHERE user_id = $2
                """, item['price_bst'], user_id)
                
                # Reduce item quantity
                await conn.execute("""
                    UPDATE shop_items SET quantity = quantity - 1
                    WHERE item_id = $1
                """, item_id)
                
                # Add to user inventory
                await conn.execute("""
                    INSERT INTO user_items (user_id, item_id, obtained_from)
                    VALUES ($1, $2, 'shop')
                    ON CONFLICT (user_id, item_id) DO UPDATE SET
                        quantity = user_items.quantity + 1
                """, user_id, item['base_item_id'])
                
                # Record transaction
                await conn.execute("""
                    INSERT INTO transactions (user_id, tx_type, amount_bst, metadata)
                    VALUES ($1, 'shop_purchase', $2, $3)
                """, user_id, -item['price_bst'], {"item_id": item_id, "item_name": item['name']})
                
                return dict(item)

    # Gift Operations
    async def send_gift(self, from_user: int, to_user: int, amount: float = 0, item_id: str = None) -> bool:
        """Send BST or item as gift"""
        self._ensure_connected()
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                if amount > 0:
                    # Gift BST
                    # Check sender balance
                    sender = await conn.fetchrow("""
                        SELECT bst_balance FROM users WHERE user_id = $1
                    """, from_user)
                    
                    if not sender or sender['bst_balance'] < amount:
                        return False
                    
                    # Transfer BST
                    await conn.execute("""
                        UPDATE users SET bst_balance = bst_balance - $1
                        WHERE user_id = $2
                    """, amount, from_user)
                    
                    await conn.execute("""
                        UPDATE users SET bst_balance = bst_balance + $1
                        WHERE user_id = $2
                    """, amount, to_user)
                    
                    # Record gift
                    await conn.execute("""
                        INSERT INTO gifts (from_user_id, to_user_id, amount_bst, item_id)
                        VALUES ($1, $2, $3, $4)
                    """, from_user, to_user, amount, item_id)
                    
                    # Record transactions
                    await conn.execute("""
                        INSERT INTO transactions (user_id, tx_type, amount_bst, metadata)
                        VALUES ($1, 'gift_sent', $2, $3)
                    """, from_user, -amount, {"to_user": to_user, "gift_type": "bst"})
                    
                    await conn.execute("""
                        INSERT INTO transactions (user_id, tx_type, amount_bst, metadata)
                        VALUES ($1, 'gift_received', $2, $3)
                    """, to_user, amount, {"from_user": from_user, "gift_type": "bst"})
                
                elif item_id:
                    # Gift item
                    # Check sender has item
                    sender_item = await conn.fetchrow("""
                        SELECT quantity FROM user_items 
                        WHERE user_id = $1 AND item_id = $2 AND quantity > 0
                    """, from_user, item_id)
                    
                    if not sender_item:
                        return False
                    
                    # Transfer item
                    await conn.execute("""
                        UPDATE user_items SET quantity = quantity - 1
                        WHERE user_id = $1 AND item_id = $2
                    """, from_user, item_id)
                    
                    await conn.execute("""
                        INSERT INTO user_items (user_id, item_id, obtained_from)
                        VALUES ($1, $2, 'gift')
                        ON CONFLICT (user_id, item_id) DO UPDATE SET
                            quantity = user_items.quantity + 1
                    """, to_user, item_id)
                    
                    # Record gift
                    await conn.execute("""
                        INSERT INTO gifts (from_user_id, to_user_id, amount_bst, item_id)
                        VALUES ($1, $2, $3, $4)
                    """, from_user, to_user, 0, item_id)
                
                return True

    # Admin Operations
    async def admin_add_points(self, user_id: int, amount: float, admin_id: int) -> bool:
        """Admin add points to user"""
        self._ensure_connected()
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                result = await conn.execute("""
                    UPDATE users SET bst_balance = bst_balance + $1
                    WHERE user_id = $2
                """, amount, user_id)
                
                if "UPDATE 1" in result:
                    await conn.execute("""
                        INSERT INTO transactions (user_id, tx_type, amount_bst, metadata)
                        VALUES ($1, 'admin_add', $2, $3)
                    """, user_id, amount, {"admin_id": admin_id})
                    return True
                return False

    async def get_economy_stats(self) -> Dict[str, Any]:
        """Get economy statistics"""
        self._ensure_connected()
        async with self.pool.acquire() as conn:
            total_bst = await conn.fetchval("SELECT SUM(bst_balance) FROM users")
            total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
            total_transactions = await conn.fetchval("SELECT COUNT(*) FROM transactions")
            
            return {
                "total_bst": total_bst or 0,
                "total_users": total_users or 0,
                "total_transactions": total_transactions or 0
            }

    # Secure Trading Operations
    async def get_next_ticket_number(self) -> int:
        """Get next ticket number"""
        self._ensure_connected()
        async with self.pool.acquire() as conn:
            result = await conn.fetchval("""
                SELECT COALESCE(MAX(ticket_number), 0) + 1 
                FROM secure_trades
            """)
            return result

    async def create_secure_trade(self, creator_id: int, channel_id: int) -> Dict[str, Any]:
        """Create a new secure trade"""
        self._ensure_connected()
        async with self.pool.acquire() as conn:
            trade = await conn.fetchrow("""
                INSERT INTO secure_trades (creator_id, channel_id)
                VALUES ($1, $2)
                RETURNING *
            """, creator_id, channel_id)
            return dict(trade)

    async def update_secure_trade(self, trade_id: str, updates: Dict[str, Any]) -> bool:
        """Update secure trade"""
        self._ensure_connected()
        async with self.pool.acquire() as conn:
            set_clause = ", ".join([f"{key} = ${i+2}" for i, key in enumerate(updates.keys())])
            values = list(updates.values())
            
            result = await conn.execute(f"""
                UPDATE secure_trades 
                SET {set_clause}, last_activity = $1
                WHERE trade_id = ${len(values) + 2}
            """, datetime.utcnow(), *values, trade_id)
            
            return "UPDATE 1" in result

    async def get_secure_trade_by_channel(self, channel_id: int) -> Dict[str, Any]:
        """Get secure trade by channel ID"""
        self._ensure_connected()
        async with self.pool.acquire() as conn:
            trade = await conn.fetchrow("""
                SELECT * FROM secure_trades 
                WHERE channel_id = $1 AND status = 'active'
            """, channel_id)
            return dict(trade) if trade else None

    # Simple balance check for testing
    async def get_balance(self, user_id: int) -> float:
        """Get user balance for testing"""
        self._ensure_connected()
        async with self.pool.acquire() as conn:
            result = await conn.fetchval("SELECT bst_balance FROM users WHERE user_id = $1", user_id)
            return result or 0.0

# Global database instance
db = Database()
              
