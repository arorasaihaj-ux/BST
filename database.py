import asyncpg
import os
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self.db_url = os.getenv('DATABASE_URL')

    async def connect(self):
        """Connect to Supabase PostgreSQL"""
        self.pool = await asyncpg.create_pool(
            self.db_url,
            min_size=1,
            max_size=5,
            statement_cache_size=0
        )
        print("✅ Database connected")
        
        # Initialize weekly cap if not exists
        await self.initialize_weekly_cap()

    async def close(self):
        """Close database connection"""
        if self.pool:
            await self.pool.close()
            print("✅ Database disconnected")

    async def initialize_weekly_cap(self):
        """Initialize weekly cap system"""
        async with self.pool.acquire() as conn:
            # Create weekly_cap table if not exists
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS weekly_cap (
                    week_id SERIAL PRIMARY KEY,
                    week_start DATE DEFAULT CURRENT_DATE,
                    bst_distributed DECIMAL(10,2) DEFAULT 0.00,
                    total_cap DECIMAL(10,2) DEFAULT 10.00,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Insert current week if not exists
            await conn.execute("""
                INSERT INTO weekly_cap (week_start, bst_distributed, total_cap)
                SELECT CURRENT_DATE, 0.00, 10.00
                WHERE NOT EXISTS (
                    SELECT 1 FROM weekly_cap 
                    WHERE week_start = DATE_TRUNC('week', CURRENT_DATE)::DATE
                )
            """)

    # ==================== WEEKLY CAP SYSTEM ====================
    
    async def get_weekly_cap(self) -> Dict[str, Any]:
        """Get current week's cap information"""
        async with self.pool.acquire() as conn:
            # Get or create current week
            week_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = week_start - timedelta(days=week_start.weekday())  # Monday
            
            row = await conn.fetchrow("""
                INSERT INTO weekly_cap (week_start, bst_distributed, total_cap)
                VALUES ($1, 0.00, 10.00)
                ON CONFLICT (week_start) DO UPDATE SET week_start = weekly_cap.week_start
                RETURNING *
            """, week_start.date())
            
            return dict(row) if row else None

    async def increment_weekly_distributed(self, amount: float = 1.0) -> bool:
        """Increment weekly distributed BST"""
        async with self.pool.acquire() as conn:
            week_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = week_start - timedelta(days=week_start.weekday())
            
            result = await conn.execute("""
                UPDATE weekly_cap 
                SET bst_distributed = bst_distributed + $1
                WHERE week_start = $2 AND bst_distributed + $1 <= total_cap
            """, amount, week_start.date())
            
            return "UPDATE 1" in result

    async def get_weekly_remaining(self) -> float:
        """Get remaining BST available this week"""
        weekly_cap = await self.get_weekly_cap()
        return max(0, weekly_cap['total_cap'] - weekly_cap['bst_distributed'])

    async def reset_weekly_cap(self) -> bool:
        """Reset weekly cap (for testing or manual reset)"""
        async with self.pool.acquire() as conn:
            week_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = week_start - timedelta(days=week_start.weekday())
            
            await conn.execute("""
                UPDATE weekly_cap 
                SET bst_distributed = 0.00
                WHERE week_start = $1
            """, week_start.date())
            return True

    # ==================== USERS ====================
    
    async def get_user(self, user_id: int) -> Dict[str, Any]:
        """Get or create user"""
        async with self.pool.acquire() as conn:
            user = await conn.fetchrow("""
                INSERT INTO users (user_id, bst_balance, message_count)
                VALUES ($1, 0.0, 0)
                ON CONFLICT (user_id) DO UPDATE SET user_id = users.user_id
                RETURNING *
            """, user_id)
            return dict(user)

    async def get_balance(self, user_id: int) -> float:
        """Get user BST balance"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT bst_balance FROM users WHERE user_id = $1",
                user_id
            )
            return float(result) if result else 0.0

    async def add_bst(self, user_id: int, amount: float) -> bool:
        """Add BST to user"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, bst_balance, message_count)
                VALUES ($1, $2, 0)
                ON CONFLICT (user_id) DO UPDATE SET
                    bst_balance = users.bst_balance + $2
            """, user_id, amount)
            return True

    async def remove_bst(self, user_id: int, amount: float) -> bool:
        """Remove BST from user (with balance check)"""
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE users 
                SET bst_balance = bst_balance - $1
                WHERE user_id = $2 AND bst_balance >= $1
            """, amount, user_id)
            return "UPDATE 1" in result

    async def set_bst(self, user_id: int, amount: float) -> bool:
        """Set exact BST amount"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, bst_balance, message_count)
                VALUES ($1, $2, 0)
                ON CONFLICT (user_id) DO UPDATE SET bst_balance = $2
            """, user_id, amount)
            return True

    async def get_all_balances(self) -> List[tuple]:
        """Get all users with BST"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT user_id, bst_balance 
                FROM users 
                WHERE bst_balance > 0
                ORDER BY bst_balance DESC
            """)
            return [(row['user_id'], float(row['bst_balance'])) for row in rows]

    # ==================== MESSAGES ====================
    
    async def increment_messages(self, user_id: int) -> int:
        """Increment message count, return new count"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                INSERT INTO users (user_id, bst_balance, message_count)
                VALUES ($1, 0.0, 1)
                ON CONFLICT (user_id) DO UPDATE SET
                    message_count = users.message_count + 1
                RETURNING message_count
            """, user_id)
            return result['message_count']

    async def reset_messages(self, user_id: int) -> bool:
        """Reset message count to 0"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE users SET message_count = 0 WHERE user_id = $1
            """, user_id)
            return True

    async def get_message_count(self, user_id: int) -> int:
        """Get user message count"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT message_count FROM users WHERE user_id = $1",
                user_id
            )
            return result if result else 0

    # ==================== ECONOMY POOL ====================
    
    async def get_economy_pool(self) -> float:
        """Get total BST in economy pool"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT pool_amount FROM economy_pool WHERE pool_id = 1"
            )
            return float(result) if result else 0.0

    async def add_to_pool(self, amount: float) -> float:
        """Add BST to economy pool"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                INSERT INTO economy_pool (pool_id, pool_amount)
                VALUES (1, $1)
                ON CONFLICT (pool_id) DO UPDATE SET
                    pool_amount = economy_pool.pool_amount + $1
                RETURNING pool_amount
            """, amount)
            return float(result['pool_amount'])

    async def remove_from_pool(self, amount: float) -> Optional[float]:
        """Remove BST from pool (with check)"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                UPDATE economy_pool
                SET pool_amount = pool_amount - $1
                WHERE pool_id = 1 AND pool_amount >= $1
                RETURNING pool_amount
            """, amount)
            return float(result['pool_amount']) if result else None

    async def reset_economy_pool(self) -> bool:
        """Reset economy pool to 0"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO economy_pool (pool_id, pool_amount)
                VALUES (1, 0.0)
                ON CONFLICT (pool_id) DO UPDATE SET pool_amount = 0.0
            """)
            return True

    # ==================== BOXES ====================
    
    async def add_box(self, user_id: int, box_type: str) -> str:
        """Add box to user inventory, return box_id"""
        async with self.pool.acquire() as conn:
            box_id = await conn.fetchval("""
                INSERT INTO boxes (user_id, box_type, opened)
                VALUES ($1, $2, false)
                RETURNING box_id
            """, user_id, box_type)
            return str(box_id)

    async def get_user_boxes(self, user_id: int) -> List[Dict]:
        """Get user's unopened boxes"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT box_id, box_type, created_at
                FROM boxes
                WHERE user_id = $1 AND opened = false
                ORDER BY created_at DESC
            """, user_id)
            return [dict(row) for row in rows]

    async def open_box(self, box_id: str, user_id: int, item_won: str) -> bool:
        """Mark box as opened and add item to inventory"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Mark box as opened
                result = await conn.execute("""
                    UPDATE boxes 
                    SET opened = true, opened_at = NOW()
                    WHERE box_id = $1 AND user_id = $2 AND opened = false
                """, box_id, user_id)
                
                if "UPDATE 0" in result:
                    return False
                
                # Add item to inventory
                await conn.execute("""
                    INSERT INTO inventory (user_id, item_name, quantity)
                    VALUES ($1, $2, 1)
                    ON CONFLICT (user_id, item_name) DO UPDATE SET
                        quantity = inventory.quantity + 1
                """, user_id, item_won)
                
                return True

    async def get_box_count(self, user_id: int, box_type: str = None) -> int:
        """Get count of unopened boxes"""
        async with self.pool.acquire() as conn:
            if box_type:
                count = await conn.fetchval("""
                    SELECT COUNT(*) FROM boxes
                    WHERE user_id = $1 AND box_type = $2 AND opened = false
                """, user_id, box_type)
            else:
                count = await conn.fetchval("""
                    SELECT COUNT(*) FROM boxes
                    WHERE user_id = $1 AND opened = false
                """, user_id)
            return count

    # ==================== INVENTORY ====================
    
    async def get_inventory(self, user_id: int) -> Dict[str, Any]:
        """Get user's full inventory"""
        async with self.pool.acquire() as conn:
            # Get boxes
            boxes = await conn.fetch("""
                SELECT box_type, COUNT(*) as count
                FROM boxes
                WHERE user_id = $1 AND opened = false
                GROUP BY box_type
            """, user_id)
            
            # Get items
            items = await conn.fetch("""
                SELECT item_name, quantity
                FROM inventory
                WHERE user_id = $1 AND quantity > 0
                ORDER BY quantity DESC
            """, user_id)
            
            return {
                'boxes': [dict(b) for b in boxes],
                'items': [dict(i) for i in items]
            }

    # ==================== TRADING ====================
    
    async def create_trade(self, creator_id: int, channel_id: int) -> str:
        """Create new trade ticket"""
        async with self.pool.acquire() as conn:
            # Ensure user exists first
            await self.get_user(creator_id)
            
            trade_id = await conn.fetchval("""
                INSERT INTO trades (creator_id, channel_id, status, escrow_amount)
                VALUES ($1, $2, 'pending', 0.0)
                RETURNING trade_id
            """, creator_id, channel_id)
            return str(trade_id)

    async def get_trade_by_channel(self, channel_id: int) -> Optional[Dict]:
        """Get active trade by channel"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM trades
                WHERE channel_id = $1 AND status = 'active'
            """, channel_id)
            return dict(row) if row else None

    async def update_trade(self, trade_id: str, **kwargs) -> bool:
        """Update trade fields"""
        async with self.pool.acquire() as conn:
            set_clauses = []
            values = []
            idx = 1
            
            for key, value in kwargs.items():
                set_clauses.append(f"{key} = ${idx}")
                values.append(value)
                idx += 1
            
            values.append(trade_id)
            query = f"""
                UPDATE trades SET {', '.join(set_clauses)}
                WHERE trade_id = ${idx}
            """
            
            await conn.execute(query, *values)
            return True

    async def complete_trade(self, trade_id: str) -> bool:
        """Mark trade as completed"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE trades SET status = 'completed'
                WHERE trade_id = $1
            """, trade_id)
            return True

    # ==================== STATS ====================
    
    async def get_total_bst_in_circulation(self) -> float:
        """Get total BST held by users"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT COALESCE(SUM(bst_balance), 0) FROM users"
            )
            return float(result)

    async def get_user_count(self) -> int:
        """Get total registered users"""
        async with self.pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM users")

    async def get_total_boxes_opened(self) -> int:
        """Get total boxes opened"""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM boxes WHERE opened = true"
            )
