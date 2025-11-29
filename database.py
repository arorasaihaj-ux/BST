import asyncpg
import os
import uuid
from typing import Optional, Dict, Any, List, Tuple
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
            max_size=10,
            statement_cache_size=0,
            command_timeout=60
        )
        
        # Initialize pools if not exists
        async with self.pool.acquire() as conn:
            # Main pool
            await conn.execute("""
                INSERT INTO economy_pool (pool_id, pool_amount)
                VALUES (1, 0.0)
                ON CONFLICT (pool_id) DO NOTHING
            """)
            # Weekly pool
            await conn.execute("""
                INSERT INTO economy_pool (pool_id, pool_amount)
                VALUES (2, 10.0)
                ON CONFLICT (pool_id) DO NOTHING
            """)
        
        print("✅ Database connected")

    async def close(self):
        if self.pool:
            await self.pool.close()
            print("✅ Database disconnected")

    # ==================== USER MANAGEMENT ====================
    
    async def get_user(self, user_id: int) -> Dict[str, Any]:
        async with self.pool.acquire() as conn:
            user = await conn.fetchrow("""
                INSERT INTO users (user_id, bst_balance, message_count)
                VALUES ($1, 0.0, 0)
                ON CONFLICT (user_id) DO UPDATE SET user_id = users.user_id
                RETURNING *
            """, user_id)
            return dict(user) if user else None

    async def get_balance(self, user_id: int) -> float:
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT bst_balance FROM users WHERE user_id = $1",
                user_id
            )
            if result is None:
                await self.get_user(user_id)
                return 0.0
            return float(result)

    async def add_bst(self, user_id: int, amount: float) -> bool:
        """Add BST FROM MAIN POOL"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                pool_balance = await conn.fetchval(
                    "SELECT pool_amount FROM economy_pool WHERE pool_id = 1"
                )
                
                if not pool_balance or pool_balance < amount:
                    return False
                
                result = await conn.execute("""
                    UPDATE economy_pool
                    SET pool_amount = pool_amount - $1, updated_at = NOW()
                    WHERE pool_id = 1 AND pool_amount >= $1
                """, amount)
                
                if "UPDATE 0" in result:
                    return False
                
                await conn.execute("""
                    INSERT INTO users (user_id, bst_balance, message_count)
                    VALUES ($1, $2, 0)
                    ON CONFLICT (user_id) DO UPDATE SET
                        bst_balance = users.bst_balance + $2
                """, user_id, amount)
                
                return True

    async def add_bst_from_weekly(self, user_id: int, amount: float) -> bool:
        """Add BST FROM WEEKLY POOL"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                weekly_pool = await conn.fetchval(
                    "SELECT pool_amount FROM economy_pool WHERE pool_id = 2"
                )
                
                if not weekly_pool or weekly_pool < amount:
                    return False
                
                result = await conn.execute("""
                    UPDATE economy_pool
                    SET pool_amount = pool_amount - $1, updated_at = NOW()
                    WHERE pool_id = 2 AND pool_amount >= $1
                """, amount)
                
                if "UPDATE 0" in result:
                    return False
                
                await conn.execute("""
                    INSERT INTO users (user_id, bst_balance, message_count)
                    VALUES ($1, $2, 0)
                    ON CONFLICT (user_id) DO UPDATE SET
                        bst_balance = users.bst_balance + $2
                """, user_id, amount)
                
                return True

    async def remove_bst_return_to_pool(self, user_id: int, amount: float) -> bool:
        """Remove BST and return to MAIN pool"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                result = await conn.execute("""
                    UPDATE users 
                    SET bst_balance = bst_balance - $1
                    WHERE user_id = $2 AND bst_balance >= $1
                """, amount, user_id)
                
                if "UPDATE 0" in result:
                    return False
                
                await conn.execute("""
                    UPDATE economy_pool
                    SET pool_amount = pool_amount + $1, updated_at = NOW()
                    WHERE pool_id = 1
                """, amount)
                
                return True

    async def buy_box_with_bst(self, user_id: int, cost: float) -> bool:
        """Remove BST when buying box and return to MAIN pool"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                balance = await conn.fetchval(
                    "SELECT bst_balance FROM users WHERE user_id = $1",
                    user_id
                )
                
                if not balance or balance < cost:
                    return False
                
                result = await conn.execute("""
                    UPDATE users 
                    SET bst_balance = bst_balance - $1
                    WHERE user_id = $2 AND bst_balance >= $1
                """, cost, user_id)
                
                if "UPDATE 0" in result:
                    return False
                
                await conn.execute("""
                    UPDATE economy_pool
                    SET pool_amount = pool_amount + $1, updated_at = NOW()
                    WHERE pool_id = 1
                """, cost)
                
                return True

    async def set_bst(self, user_id: int, amount: float) -> bool:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, bst_balance, message_count)
                VALUES ($1, $2, 0)
                ON CONFLICT (user_id) DO UPDATE SET bst_balance = $2
            """, user_id, amount)
            return True

    async def reset_user_and_return_to_pool(self, user_id: int) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                balance = await conn.fetchval(
                    "SELECT bst_balance FROM users WHERE user_id = $1",
                    user_id
                )
                
                if not balance or balance == 0:
                    await conn.execute("""
                        UPDATE users 
                        SET bst_balance = 0.0, message_count = 0
                        WHERE user_id = $1
                    """, user_id)
                    return True
                
                await conn.execute("""
                    UPDATE economy_pool
                    SET pool_amount = pool_amount + $1, updated_at = NOW()
                    WHERE pool_id = 1
                """, balance)
                
                await conn.execute("""
                    UPDATE users 
                    SET bst_balance = 0.0, message_count = 0
                    WHERE user_id = $1
                """, user_id)
                
                return True

    # ==================== MESSAGE TRACKING ====================
    
    async def increment_messages(self, user_id: int) -> int:
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                INSERT INTO users (user_id, bst_balance, message_count)
                VALUES ($1, 0.0, 1)
                ON CONFLICT (user_id) DO UPDATE SET
                    message_count = users.message_count + 1
                RETURNING message_count
            """, user_id)
            return result['message_count'] if result else 0

    async def reset_messages(self, user_id: int) -> bool:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET message_count = 0 WHERE user_id = $1",
                user_id
            )
            return True

    async def get_message_count(self, user_id: int) -> int:
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT message_count FROM users WHERE user_id = $1",
                user_id
            )
            return result if result else 0

    async def set_message_count(self, user_id: int, count: int) -> bool:
        """Set exact message count (admin function)"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, bst_balance, message_count)
                VALUES ($1, 0.0, $2)
                ON CONFLICT (user_id) DO UPDATE SET
                    message_count = $2
            """, user_id, count)
            return True

    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Get comprehensive user statistics"""
        async with self.pool.acquire() as conn:
            user = await conn.fetchrow("""
                SELECT user_id, bst_balance, message_count, created_at
                FROM users WHERE user_id = $1
            """, user_id)
            
            if not user:
                await self.get_user(user_id)
                return {
                    'user_id': user_id,
                    'bst_balance': 0.0,
                    'message_count': 0,
                    'total_boxes': 0,
                    'boxes_opened': 0,
                    'unique_items': 0,
                    'total_items': 0
                }
            
            boxes_owned = await conn.fetchval("""
                SELECT COUNT(*) FROM boxes
                WHERE user_id = $1 AND opened = false
            """, user_id)
            
            boxes_opened = await conn.fetchval("""
                SELECT COUNT(*) FROM boxes
                WHERE user_id = $1 AND opened = true
            """, user_id)
            
            unique_items = await conn.fetchval("""
                SELECT COUNT(*) FROM inventory
                WHERE user_id = $1 AND quantity > 0
            """, user_id)
            
            total_items = await conn.fetchval("""
                SELECT COALESCE(SUM(quantity), 0) FROM inventory
                WHERE user_id = $1
            """, user_id)
            
            return {
                'user_id': user['user_id'],
                'bst_balance': float(user['bst_balance']),
                'message_count': user['message_count'],
                'created_at': user['created_at'],
                'total_boxes': boxes_owned or 0,
                'boxes_opened': boxes_opened or 0,
                'unique_items': unique_items or 0,
                'total_items': total_items or 0
            }

    # ==================== MAIN ECONOMY POOL ====================
    
    async def get_pool_balance(self) -> float:
        """Get MAIN pool balance"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT pool_amount FROM economy_pool WHERE pool_id = 1"
            )
            return float(result) if result else 0.0

    async def add_to_pool(self, amount: float) -> float:
        """Add to MAIN pool (minting)"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                INSERT INTO economy_pool (pool_id, pool_amount)
                VALUES (1, $1)
                ON CONFLICT (pool_id) DO UPDATE SET
                    pool_amount = economy_pool.pool_amount + $1,
                    updated_at = NOW()
                RETURNING pool_amount
            """, amount)
            return float(result['pool_amount']) if result else 0.0

    async def remove_from_pool_direct(self, amount: float) -> float:
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                UPDATE economy_pool
                SET pool_amount = pool_amount - $1, updated_at = NOW()
                WHERE pool_id = 1
                RETURNING pool_amount
            """, amount)
            return float(result['pool_amount']) if result else 0.0

    async def set_pool_balance(self, amount: float) -> bool:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE economy_pool 
                SET pool_amount = $1, updated_at = NOW() 
                WHERE pool_id = 1
            """, amount)
            return True

    async def reset_pool(self) -> bool:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE economy_pool 
                SET pool_amount = 0.0, updated_at = NOW() 
                WHERE pool_id = 1
            """)
            return True

    # ==================== WEEKLY POOL (SEPARATE) ====================
    
    async def get_weekly_pool(self) -> float:
        """Get WEEKLY pool balance"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT pool_amount FROM economy_pool WHERE pool_id = 2"
            )
            return float(result) if result else 0.0

    async def add_to_weekly_pool(self, amount: float) -> float:
        """Add BST to weekly pool"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                INSERT INTO economy_pool (pool_id, pool_amount)
                VALUES (2, $1)
                ON CONFLICT (pool_id) DO UPDATE SET
                    pool_amount = economy_pool.pool_amount + $1,
                    updated_at = NOW()
                RETURNING pool_amount
            """, amount)
            return float(result['pool_amount']) if result else 0.0

    async def remove_from_weekly_pool(self, amount: float) -> Optional[float]:
        """Remove BST from weekly pool"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                UPDATE economy_pool
                SET pool_amount = pool_amount - $1, updated_at = NOW()
                WHERE pool_id = 2 AND pool_amount >= $1
                RETURNING pool_amount
            """, amount)
            return float(result['pool_amount']) if result else None

    async def set_weekly_pool(self, amount: float) -> bool:
        """Set exact weekly pool amount"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO economy_pool (pool_id, pool_amount)
                VALUES (2, $1)
                ON CONFLICT (pool_id) DO UPDATE SET
                    pool_amount = $1, updated_at = NOW()
            """, amount)
            return True

    async def reset_weekly_pool(self, amount: float = 10.0) -> bool:
        """Reset weekly pool to specified amount"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE economy_pool 
                SET pool_amount = $1, updated_at = NOW() 
                WHERE pool_id = 2
            """, amount)
            return True

    async def transfer_weekly_to_main(self) -> float:
        """Transfer remaining weekly pool to main pool and return amount transferred"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                weekly = await conn.fetchval(
                    "SELECT pool_amount FROM economy_pool WHERE pool_id = 2"
                )
                
                if weekly and weekly > 0:
                    await conn.execute("""
                        UPDATE economy_pool
                        SET pool_amount = pool_amount + $1, updated_at = NOW()
                        WHERE pool_id = 1
                    """, weekly)
                    
                    await conn.execute("""
                        UPDATE economy_pool
                        SET pool_amount = 0.0, updated_at = NOW()
                        WHERE pool_id = 2
                    """)
                    
                    return float(weekly)
                
                return 0.0

    async def get_both_pools(self) -> Dict[str, float]:
        """Get both main and weekly pool in one call"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT pool_id, pool_amount FROM economy_pool
                WHERE pool_id IN (1, 2)
                ORDER BY pool_id
            """)
            
            result = {'main_pool': 0.0, 'weekly_pool': 0.0}
            for row in rows:
                if row['pool_id'] == 1:
                    result['main_pool'] = float(row['pool_amount'])
                elif row['pool_id'] == 2:
                    result['weekly_pool'] = float(row['pool_amount'])
            
            return result

    async def add_to_both_pools(self, main_amount: float, weekly_amount: float) -> Dict[str, float]:
        """Add to both pools at once"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("""
                    UPDATE economy_pool
                    SET pool_amount = pool_amount + $1, updated_at = NOW()
                    WHERE pool_id = 1
                """, main_amount)
                
                await conn.execute("""
                    UPDATE economy_pool
                    SET pool_amount = pool_amount + $1, updated_at = NOW()
                    WHERE pool_id = 2
                """, weekly_amount)
                
                return await self.get_both_pools()

    async def transfer_between_pools(self, from_pool: int, to_pool: int, amount: float) -> bool:
        """Transfer BST between pools (1=main, 2=weekly)"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Check source pool has enough
                source = await conn.fetchval("""
                    SELECT pool_amount FROM economy_pool WHERE pool_id = $1
                """, from_pool)
                
                if not source or source < amount:
                    return False
                
                # Remove from source
                result = await conn.execute("""
                    UPDATE economy_pool
                    SET pool_amount = pool_amount - $1, updated_at = NOW()
                    WHERE pool_id = $2 AND pool_amount >= $1
                """, amount, from_pool)
                
                if "UPDATE 0" in result:
                    return False
                
                # Add to destination
                await conn.execute("""
                    UPDATE economy_pool
                    SET pool_amount = pool_amount + $1, updated_at = NOW()
                    WHERE pool_id = $2
                """, amount, to_pool)
                
                return True

    # ==================== STATISTICS ====================
    
    async def get_all_balances(self) -> List[tuple]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT user_id, bst_balance 
                FROM users 
                WHERE bst_balance > 0
                ORDER BY bst_balance DESC
                LIMIT 100
            """)
            return [(row['user_id'], float(row['bst_balance'])) for row in rows]

    async def get_total_bst_in_circulation(self) -> float:
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT COALESCE(SUM(bst_balance), 0) FROM users"
            )
            return float(result)

    async def get_user_count(self) -> int:
        async with self.pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM users")

    async def get_total_boxes_opened(self) -> int:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM boxes WHERE opened = true"
            )

    async def search_users_by_balance(self, min_balance: float = 0.0, max_balance: float = None) -> List[Dict]:
        """Search users by balance range"""
        async with self.pool.acquire() as conn:
            if max_balance:
                rows = await conn.fetch("""
                    SELECT user_id, bst_balance, message_count
                    FROM users
                    WHERE bst_balance >= $1 AND bst_balance <= $2
                    ORDER BY bst_balance DESC
                """, min_balance, max_balance)
            else:
                rows = await conn.fetch("""
                    SELECT user_id, bst_balance, message_count
                    FROM users
                    WHERE bst_balance >= $1
                    ORDER BY bst_balance DESC
                """, min_balance)
            
            return [dict(row) for row in rows]

    async def get_users_with_messages(self, min_messages: int = 1) -> List[Dict]:
        """Get users who have sent messages"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT user_id, bst_balance, message_count
                FROM users
                WHERE message_count >= $1
                ORDER BY message_count DESC
                LIMIT 100
            """, min_messages)
            return [dict(row) for row in rows]

    async def get_richest_users(self, limit: int = 10) -> List[Dict]:
        """Get top users by balance"""
        return await self.get_top_users(limit)

    async def count_users_with_balance(self) -> int:
        """Count users with BST > 0"""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE bst_balance > 0"
            )

    async def get_total_messages_sent(self) -> int:
        """Get sum of all messages sent"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT COALESCE(SUM(message_count), 0) FROM users"
            )
            return result or 0

    async def get_average_balance(self) -> float:
        """Get average BST balance across all users"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval("""
                SELECT AVG(bst_balance) FROM users WHERE bst_balance > 0
            """)
            return float(result) if result else 0.0

    async def get_median_balance(self) -> float:
        """Get median BST balance"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval("""
                SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY bst_balance)
                FROM users WHERE bst_balance > 0
            """)
            return float(result) if result else 0.0

    # ==================== TRADING ====================
    
    async def create_trade(self, creator_id: int, channel_id: int) -> str:
        async with self.pool.acquire() as conn:
            await self.get_user(creator_id)
            trade_id = await conn.fetchval("""
                INSERT INTO trades (
                    channel_id, creator_id, status, stage, 
                    bst_amount, escrow_amount, sender_confirmed, receiver_confirmed
                )
                VALUES ($1, $2, 'active', 'awaiting_partner', 0.0, 0.0, false, false)
                RETURNING trade_id
            """, channel_id, creator_id)
            return str(trade_id)

    async def get_trade_by_channel(self, channel_id: int) -> Optional[Dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM trades
                WHERE channel_id = $1 AND status IN ('active', 'pending')
                ORDER BY created_at DESC LIMIT 1
            """, channel_id)
            return dict(row) if row else None

    async def update_trade_partner(self, trade_id: str, partner_id: int) -> bool:
        async with self.pool.acquire() as conn:
            await self.get_user(partner_id)
            await conn.execute("""
                UPDATE trades 
                SET partner_id = $1, stage = 'role_selection', last_activity = NOW()
                WHERE trade_id = $2
            """, partner_id, trade_id)
            return True

    async def set_trade_roles(self, trade_id: str, sender_id: int, receiver_id: int) -> bool:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE trades 
                SET sender_id = $1, receiver_id = $2, stage = 'roles_set', last_activity = NOW()
                WHERE trade_id = $3
            """, sender_id, receiver_id, trade_id)
            return True

    async def update_trade_stage(self, trade_id: str, stage: str) -> bool:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE trades 
                SET stage = $1, last_activity = NOW()
                WHERE trade_id = $2
            """, stage, trade_id)
            return True

    async def hold_bst_in_escrow(self, trade_id: str, sender_id: int, amount: float) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                balance = await conn.fetchval(
                    "SELECT bst_balance FROM users WHERE user_id = $1", sender_id
                )
                if balance < amount:
                    return False
                
                result = await conn.execute("""
                    UPDATE users 
                    SET bst_balance = bst_balance - $1
                    WHERE user_id = $2 AND bst_balance >= $1
                """, amount, sender_id)
                
                if "UPDATE 0" in result:
                    return False
                
                await conn.execute("""
                    UPDATE trades 
                    SET stage = 'bst_held', escrow_amount = $1, last_activity = NOW()
                    WHERE trade_id = $2
                """, amount, trade_id)
                return True

    async def release_bst(self, trade_id: str, receiver_id: int, amount: float) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("""
                    INSERT INTO users (user_id, bst_balance, message_count)
                    VALUES ($1, $2, 0)
                    ON CONFLICT (user_id) DO UPDATE SET
                        bst_balance = users.bst_balance + $2
                """, receiver_id, amount)
                
                await conn.execute("""
                    UPDATE trades 
                    SET status = 'completed', stage = 'completed',
                        completed_at = NOW(), last_activity = NOW()
                    WHERE trade_id = $1
                """, trade_id)
                return True

    async def cancel_trade(self, trade_id: str, refund: bool = False) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                trade = await conn.fetchrow("""
                    SELECT sender_id, escrow_amount, stage 
                    FROM trades WHERE trade_id = $1
                """, trade_id)
                
                if refund and trade and trade['stage'] == 'bst_held' and trade['escrow_amount'] > 0:
                    await conn.execute("""
                        UPDATE users 
                        SET bst_balance = bst_balance + $1
                        WHERE user_id = $2
                    """, trade['escrow_amount'], trade['sender_id'])
                
                await conn.execute("""
                    UPDATE trades 
                    SET status = 'cancelled', last_activity = NOW()
                    WHERE trade_id = $1
                """, trade_id)
                return True

    async def get_inactive_trades(self, minutes: int = 30) -> List[Dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM trades
                WHERE status = 'active' 
                AND last_activity < NOW() - INTERVAL '%s minutes'
            """, minutes)
            return [dict(row) for row in rows]

    async def get_user_active_trades(self, user_id: int) -> List[Dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM trades
                WHERE (creator_id = $1 OR partner_id = $1)
                AND status IN ('active', 'pending')
                ORDER BY created_at DESC
            """, user_id)
            return [dict(row) for row in rows]

    async def update_trade_activity(self, trade_id: str) -> bool:
        """Update last activity timestamp"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE trades SET last_activity = NOW()
                WHERE trade_id = $1
            """, trade_id)
            return True

    async def set_trade_amount(self, trade_id: str, amount: float) -> bool:
        """Set BST amount for trade"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE trades 
                SET bst_amount = $1, last_activity = NOW()
                WHERE trade_id = $2
            """, amount, trade_id)
            return True

    async def get_trade_by_id(self, trade_id: str) -> Optional[Dict]:
        """Get trade by trade ID"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM trades WHERE trade_id = $1
            """, trade_id)
            return dict(row) if row else None

    async def get_all_active_trades(self) -> List[Dict]:
        """Get all active trades (for admin monitoring)"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM trades
                WHERE status = 'active'
                ORDER BY created_at DESC
            """)
            return [dict(row) for row in rows]

    # ==================== BOXES ====================
    
    async def add_box(self, user_id: int, box_type: str) -> str:
        async with self.pool.acquire() as conn:
            box_id = await conn.fetchval("""
                INSERT INTO boxes (user_id, box_type, opened)
                VALUES ($1, $2, false)
                RETURNING box_id
            """, user_id, box_type)
            return str(box_id)

    async def get_user_boxes(self, user_id: int) -> List[Dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT box_id, box_type, created_at
                FROM boxes
                WHERE user_id = $1 AND opened = false
                ORDER BY created_at DESC
            """, user_id)
            return [dict(row) for row in rows]

    async def open_box(self, box_id: str, user_id: int, item_won: str) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                result = await conn.execute("""
                    UPDATE boxes 
                    SET opened = true, opened_at = NOW()
                    WHERE box_id = $1 AND user_id = $2 AND opened = false
                """, box_id, user_id)
                
                if "UPDATE 0" in result:
                    return False
                
                await conn.execute("""
                    INSERT INTO inventory (user_id, item_name, quantity)
                    VALUES ($1, $2, 1)
                    ON CONFLICT (user_id, item_name) DO UPDATE SET
                        quantity = inventory.quantity + 1
                """, user_id, item_won)
                return True

    async def get_total_boxes_owned(self, user_id: int) -> int:
        """Get total unopened boxes for user"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval("""
                SELECT COUNT(*) FROM boxes
                WHERE user_id = $1 AND opened = false
            """, user_id)
            return result or 0

    async def get_box_by_id(self, box_id: str) -> Optional[Dict]:
        """Get specific box by ID"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM boxes WHERE box_id = $1
            """, box_id)
            return dict(row) if row else None

    async def delete_box(self, box_id: str, user_id: int) -> bool:
        """Delete a box (admin function)"""
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM boxes
                WHERE box_id = $1 AND user_id = $2
            """, box_id, user_id)
            return "DELETE 1" in result

    # ==================== INVENTORY ====================
    
    async def get_inventory(self, user_id: int) -> Dict[str, Any]:
        async with self.pool.acquire() as conn:
            boxes = await conn.fetch("""
                SELECT box_type, COUNT(*) as count
                FROM boxes
                WHERE user_id = $1 AND opened = false
                GROUP BY box_type
            """, user_id)
            
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

    async def remove_inventory_item(self, user_id: int, item_name: str, quantity: int) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                current_qty = await conn.fetchval("""
                    SELECT quantity FROM inventory
                    WHERE user_id = $1 AND LOWER(item_name) = LOWER($2)
                """, user_id, item_name)
                
                if not current_qty or current_qty < quantity:
                    return False
                
                new_qty = current_qty - quantity
                
                if new_qty == 0:
                    await conn.execute("""
                        DELETE FROM inventory
                        WHERE user_id = $1 AND LOWER(item_name) = LOWER($2)
                    """, user_id, item_name)
                else:
                    await conn.execute("""
                        UPDATE inventory SET quantity = $3
                        WHERE user_id = $1 AND LOWER(item_name) = LOWER($2)
                    """, user_id, item_name, new_qty)
                return True

    async def clear_inventory(self, user_id: int) -> bool:
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM inventory WHERE user_id = $1", user_id)
            return True

    async def add_inventory_item(self, user_id: int, item_name: str, quantity: int = 1) -> bool:
        """Add item directly to inventory (admin function)"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO inventory (user_id, item_name, quantity)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, item_name) DO UPDATE SET
                    quantity = inventory.quantity + $3
            """, user_id, item_name, quantity)
            return True

    async def get_item_quantity(self, user_id: int, item_name: str) -> int:
        """Get quantity of specific item"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval("""
                SELECT quantity FROM inventory
                WHERE user_id = $1 AND LOWER(item_name) = LOWER($2)
            """, user_id, item_name)
            return result or 0

    async def get_all_items(self, user_id: int) -> List[Dict]:
        """Get all items for user"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT item_name, quantity, obtained_at, updated_at
                FROM inventory
                WHERE user_id = $1 AND quantity > 0
                ORDER BY quantity DESC, item_name ASC
            """, user_id)
            return [dict(row) for row in rows]

    async def get_total_item_count(self, user_id: int) -> int:
        """Get total number of items (counting quantities)"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval("""
                SELECT COALESCE(SUM(quantity), 0) FROM inventory
                WHERE user_id = $1
            """, user_id)
            return result or 0

    async def get_unique_item_count(self, user_id: int) -> int:
        """Get number of unique items"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval("""
                SELECT COUNT(*) FROM inventory
                WHERE user_id = $1 AND quantity > 0
            """, user_id)
            return result or 0

    # ==================== ECONOMY STATS & ADMIN ====================
    
    async def get_economy_stats(self) -> Dict[str, Any]:
        """Get comprehensive economy statistics"""
        pool_balance = await self.get_pool_balance()
        weekly_pool = await self.get_weekly_pool()
        circulation = await self.get_total_bst_in_circulation()
        user_count = await self.get_user_count()
        boxes_opened = await self.get_total_boxes_opened()
        
        return {
            'main_pool': pool_balance,
            'weekly_pool': weekly_pool,
            'circulation': circulation,
            'total_supply': pool_balance + circulation,
            'user_count': user_count,
            'boxes_opened': boxes_opened
        }

    async def get_top_users(self, limit: int = 10) -> List[Dict]:
        """Get top users by BST balance"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT user_id, bst_balance, message_count
                FROM users 
                WHERE bst_balance > 0
                ORDER BY bst_balance DESC
                LIMIT $1
            """, limit)
            return [dict(row) for row in rows]

    async def get_trade_statistics(self) -> Dict[str, Any]:
        """Get trading statistics"""
        async with self.pool.acquire() as conn:
            total_trades = await conn.fetchval("SELECT COUNT(*) FROM trades")
            completed_trades = await conn.fetchval("SELECT COUNT(*) FROM trades WHERE status = 'completed'")
            active_trades = await conn.fetchval("SELECT COUNT(*) FROM trades WHERE status = 'active'")
            total_traded = await conn.fetchval("SELECT COALESCE(SUM(bst_amount), 0) FROM trades WHERE status = 'completed'")
            
            return {
                'total_trades': total_trades or 0,
                'completed_trades': completed_trades or 0,
                'active_trades': active_trades or 0,
                'total_traded': float(total_traded) if total_traded else 0.0
            }

    # ==================== WEEKLY POOL HISTORY (Optional tracking) ====================
    
    async def log_weekly_reset(self, week_start: datetime, initial: float, final: float, distributed: float):
        """Log weekly pool reset for tracking"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO weekly_pool_history (week_start, initial_amount, final_amount, total_distributed, reset_at)
                VALUES ($1, $2, $3, $4, NOW())
            """, week_start.date(), initial, final, distributed)

    async def get_weekly_history(self, limit: int = 10) -> List[Dict]:
        """Get weekly pool history"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM weekly_pool_history
                ORDER BY week_start DESC
                LIMIT $1
            """, limit)
            return [dict(row) for row in rows]

    # ==================== BULK OPERATIONS ====================
    
    async def bulk_add_bst(self, user_amounts: List[Tuple[int, float]]) -> int:
        """Add BST to multiple users at once (from main pool)"""
        total_needed = sum(amount for _, amount in user_amounts)
        pool = await self.get_pool_balance()
        
        if pool < total_needed:
            return 0
        
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Remove from pool
                await conn.execute("""
                    UPDATE economy_pool
                    SET pool_amount = pool_amount - $1, updated_at = NOW()
                    WHERE pool_id = 1
                """, total_needed)
                
                # Add to users
                count = 0
                for user_id, amount in user_amounts:
                    await conn.execute("""
                        INSERT INTO users (user_id, bst_balance, message_count)
                        VALUES ($1, $2, 0)
                        ON CONFLICT (user_id) DO UPDATE SET
                            bst_balance = users.bst_balance + $2
                    """, user_id, amount)
                    count += 1
                
                return count

    async def bulk_reset_messages(self, user_ids: List[int]) -> int:
        """Reset message count for multiple users"""
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE users SET message_count = 0
                WHERE user_id = ANY($1::bigint[])
            """, user_ids)
            return int(result.split()[-1]) if result else 0

    async def cleanup_old_trades(self, days: int = 30) -> int:
        """Delete old completed/cancelled trades"""
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM trades
                WHERE status IN ('completed', 'cancelled')
                AND created_at < NOW() - INTERVAL '%s days'
            """, days)
            return int(result.split()[-1]) if result else 0

    async def cleanup_zero_balances(self) -> int:
        """Remove users with 0 balance and 0 messages (cleanup)"""
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM users
                WHERE bst_balance = 0 AND message_count = 0
                AND user_id NOT IN (SELECT DISTINCT user_id FROM boxes)
                AND user_id NOT IN (SELECT DISTINCT user_id FROM inventory WHERE quantity > 0)
            """)
            return int(result.split()[-1]) if result else 0

    # ==================== BACKUP & RESTORE ====================
    
    async def backup_economy_state(self) -> Dict[str, Any]:
        """Create a snapshot of current economy state"""
        async with self.pool.acquire() as conn:
            pools = await self.get_both_pools()
            circulation = await self.get_total_bst_in_circulation()
            user_count = await self.get_user_count()
            
            return {
                'timestamp': datetime.now().isoformat(),
                'main_pool': pools['main_pool'],
                'weekly_pool': pools['weekly_pool'],
                'circulation': circulation,
                'total_supply': pools['main_pool'] + circulation,
                'user_count': user_count,
                'boxes_opened': await self.get_total_boxes_opened()
            }

    async def verify_economy_integrity(self) -> Dict[str, Any]:
        """Verify economy data integrity"""
        async with self.pool.acquire() as conn:
            # Check for negative balances
            negative_balances = await conn.fetchval("""
                SELECT COUNT(*) FROM users WHERE bst_balance < 0
            """)
            
            # Check for orphaned boxes
            orphaned_boxes = await conn.fetchval("""
                SELECT COUNT(*) FROM boxes
                WHERE user_id NOT IN (SELECT user_id FROM users)
            """)
            
            # Check for orphaned inventory
            orphaned_inventory = await conn.fetchval("""
                SELECT COUNT(*) FROM inventory
                WHERE user_id NOT IN (SELECT user_id FROM users)
            """)
            
            # Check for negative quantities
            negative_quantities = await conn.fetchval("""
                SELECT COUNT(*) FROM inventory WHERE quantity < 0
            """)
            
            # Get economy totals
            pools = await self.get_both_pools()
            circulation = await self.get_total_bst_in_circulation()
            
            return {
                'is_valid': (negative_balances == 0 and orphaned_boxes == 0 and 
                           orphaned_inventory == 0 and negative_quantities == 0),
                'negative_balances': negative_balances,
                'orphaned_boxes': orphaned_boxes,
                'orphaned_inventory': orphaned_inventory,
                'negative_quantities': negative_quantities,
                'main_pool': pools['main_pool'],
                'weekly_pool': pools['weekly_pool'],
                'circulation': circulation,
                'total_supply': pools['main_pool'] + circulation
            }

    async def fix_orphaned_data(self) -> Dict[str, int]:
        """Fix orphaned data (boxes/inventory without users)"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                boxes_deleted = await conn.execute("""
                    DELETE FROM boxes
                    WHERE user_id NOT IN (SELECT user_id FROM users)
                """)
                
                inventory_deleted = await conn.execute("""
                    DELETE FROM inventory
                    WHERE user_id NOT IN (SELECT user_id FROM users)
                """)
                
                return {
                    'boxes_deleted': int(boxes_deleted.split()[-1]) if boxes_deleted else 0,
                    'inventory_deleted': int(inventory_deleted.split()[-1]) if inventory_deleted else 0
                }
