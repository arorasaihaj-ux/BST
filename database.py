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
        print("✅ Database connected")
        await self.initialize_weekly_cap()

    async def close(self):
        """Close database connection"""
        if self.pool:
            await self.pool.close()
            print("✅ Database disconnected")

    async def initialize_weekly_cap(self):
        """Initialize weekly cap system"""
        async with self.pool.acquire() as conn:
            week_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = week_start - timedelta(days=week_start.weekday())
            
            await conn.execute("""
                INSERT INTO weekly_cap (week_start, bst_distributed, total_cap)
                VALUES ($1, 0.00, 10.00)
                ON CONFLICT (week_start) DO NOTHING
            """, week_start.date())

    # ==================== USER MANAGEMENT ====================
    
    async def get_user(self, user_id: int) -> Dict[str, Any]:
        """Get or create user"""
        async with self.pool.acquire() as conn:
            user = await conn.fetchrow("""
                INSERT INTO users (user_id, bst_balance, message_count)
                VALUES ($1, 0.0, 0)
                ON CONFLICT (user_id) DO UPDATE SET user_id = users.user_id
                RETURNING *
            """, user_id)
            return dict(user) if user else None

    async def get_balance(self, user_id: int) -> float:
        """Get user BST balance"""
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
        """Add BST to user FROM POOL - REQUIRES POOL BALANCE"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Check pool has enough
                pool_balance = await conn.fetchval(
                    "SELECT pool_amount FROM economy_pool WHERE pool_id = 1"
                )
                
                if not pool_balance or pool_balance < amount:
                    return False
                
                # Remove from pool first
                result = await conn.execute("""
                    UPDATE economy_pool
                    SET pool_amount = pool_amount - $1,
                        updated_at = NOW()
                    WHERE pool_id = 1 AND pool_amount >= $1
                """, amount)
                
                if "UPDATE 0" in result:
                    return False
                
                # Add to user
                await conn.execute("""
                    INSERT INTO users (user_id, bst_balance, message_count)
                    VALUES ($1, $2, 0)
                    ON CONFLICT (user_id) DO UPDATE SET
                        bst_balance = users.bst_balance + $2
                """, user_id, amount)
                
                return True

    async def remove_bst(self, user_id: int, amount: float) -> bool:
        """Remove BST from user (with balance check) - BST IS DESTROYED"""
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE users 
                SET bst_balance = bst_balance - $1
                WHERE user_id = $2 AND bst_balance >= $1
            """, amount, user_id)
            return "UPDATE 1" in result

    async def set_bst(self, user_id: int, amount: float) -> bool:
        """Set exact BST amount - ONLY OWNER CAN USE THIS"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, bst_balance, message_count)
                VALUES ($1, $2, 0)
                ON CONFLICT (user_id) DO UPDATE SET bst_balance = $2
            """, user_id, amount)
            return True

    # ==================== MESSAGE TRACKING ====================
    
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
            return result['message_count'] if result else 0

    async def reset_messages(self, user_id: int) -> bool:
        """Reset message count to 0"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET message_count = 0 WHERE user_id = $1",
                user_id
            )
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
    
    async def get_pool_balance(self) -> float:
        """Get current pool balance"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT pool_amount FROM economy_pool WHERE pool_id = 1"
            )
            return float(result) if result else 0.0

    async def add_to_pool(self, amount: float) -> float:
        """Add BST to economy pool (minting) - OWNER ONLY"""
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

    async def remove_from_pool(self, amount: float) -> Optional[float]:
        """Remove BST from pool (with check)"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                UPDATE economy_pool
                SET pool_amount = pool_amount - $1,
                    updated_at = NOW()
                WHERE pool_id = 1 AND pool_amount >= $1
                RETURNING pool_amount
            """, amount)
            return float(result['pool_amount']) if result else None

    async def reset_pool(self) -> bool:
        """Reset pool to 0 (for supply reset)"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE economy_pool 
                SET pool_amount = 0.0, updated_at = NOW() 
                WHERE pool_id = 1
            """)
            return True

    # ==================== WEEKLY CAP ====================
    
    async def get_weekly_cap(self) -> Dict[str, Any]:
        """Get current week's cap information"""
        async with self.pool.acquire() as conn:
            week_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = week_start - timedelta(days=week_start.weekday())
            
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
        if not weekly_cap:
            return 10.0
        return max(0, weekly_cap['total_cap'] - weekly_cap['bst_distributed'])

    async def reset_weekly_cap(self) -> bool:
        """Reset weekly cap (Monday reset)"""
        async with self.pool.acquire() as conn:
            week_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = week_start - timedelta(days=week_start.weekday())
            
            await conn.execute("""
                UPDATE weekly_cap 
                SET bst_distributed = 0.00
                WHERE week_start = $1
            """, week_start.date())
            return True

    # ==================== TRADING SYSTEM ====================
    
    async def create_trade(self, creator_id: int, channel_id: int) -> str:
        """Create new trade ticket"""
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
        """Get trade by channel ID"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM trades
                WHERE channel_id = $1 AND status IN ('active', 'pending')
                ORDER BY created_at DESC
                LIMIT 1
            """, channel_id)
            return dict(row) if row else None

    async def update_trade_partner(self, trade_id: str, partner_id: int) -> bool:
        """Add partner to trade"""
        async with self.pool.acquire() as conn:
            await self.get_user(partner_id)
            
            await conn.execute("""
                UPDATE trades 
                SET partner_id = $1, stage = 'role_selection', last_activity = NOW()
                WHERE trade_id = $2
            """, partner_id, trade_id)
            return True

    async def set_trade_roles(self, trade_id: str, sender_id: int, receiver_id: int) -> bool:
        """Set sender and receiver roles"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE trades 
                SET sender_id = $1, receiver_id = $2, 
                    stage = 'roles_set', 
                    last_activity = NOW()
                WHERE trade_id = $3
            """, sender_id, receiver_id, trade_id)
            return True

    async def update_trade_stage(self, trade_id: str, stage: str) -> bool:
        """Update trade stage"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE trades 
                SET stage = $1, last_activity = NOW()
                WHERE trade_id = $2
            """, stage, trade_id)
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

    async def hold_bst_in_escrow(self, trade_id: str, sender_id: int, amount: float) -> bool:
        """Hold BST from sender (remove from their balance)"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Check if sender has enough
                balance = await conn.fetchval(
                    "SELECT bst_balance FROM users WHERE user_id = $1",
                    sender_id
                )
                
                if balance < amount:
                    return False
                
                # Remove from sender
                result = await conn.execute("""
                    UPDATE users 
                    SET bst_balance = bst_balance - $1
                    WHERE user_id = $2 AND bst_balance >= $1
                """, amount, sender_id)
                
                if "UPDATE 0" in result:
                    return False
                
                # Update trade stage and set escrow amount
                await conn.execute("""
                    UPDATE trades 
                    SET stage = 'bst_held', 
                        escrow_amount = $1,
                        last_activity = NOW()
                    WHERE trade_id = $2
                """, amount, trade_id)
                
                return True

    async def release_bst(self, trade_id: str, receiver_id: int, amount: float) -> bool:
        """Release BST to receiver"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Give to receiver
                await conn.execute("""
                    INSERT INTO users (user_id, bst_balance, message_count)
                    VALUES ($1, $2, 0)
                    ON CONFLICT (user_id) DO UPDATE SET
                        bst_balance = users.bst_balance + $2
                """, receiver_id, amount)
                
                # Complete trade
                await conn.execute("""
                    UPDATE trades 
                    SET status = 'completed', 
                        stage = 'completed',
                        completed_at = NOW(),
                        last_activity = NOW()
                    WHERE trade_id = $1
                """, trade_id)
                
                return True

    async def cancel_trade(self, trade_id: str, refund: bool = False) -> bool:
        """Cancel trade (with optional refund)"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                trade = await conn.fetchrow("""
                    SELECT sender_id, escrow_amount, stage 
                    FROM trades WHERE trade_id = $1
                """, trade_id)
                
                if refund and trade and trade['stage'] == 'bst_held' and trade['escrow_amount'] > 0:
                    # Refund to sender
                    await conn.execute("""
                        UPDATE users 
                        SET bst_balance = bst_balance + $1
                        WHERE user_id = $2
                    """, trade['escrow_amount'], trade['sender_id'])
                
                # Mark as cancelled
                await conn.execute("""
                    UPDATE trades 
                    SET status = 'cancelled', last_activity = NOW()
                    WHERE trade_id = $1
                """, trade_id)
                
                return True

    async def update_trade_activity(self, trade_id: str) -> bool:
        """Update last activity timestamp"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE trades SET last_activity = NOW()
                WHERE trade_id = $1
            """, trade_id)
            return True

    async def get_inactive_trades(self, minutes: int = 30) -> List[Dict]:
        """Get trades inactive for specified minutes"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM trades
                WHERE status = 'active' 
                AND last_activity < NOW() - INTERVAL '%s minutes'
            """, minutes)
            return [dict(row) for row in rows]

    async def get_user_active_trades(self, user_id: int) -> List[Dict]:
        """Get all active trades for a user (as creator or partner)"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM trades
                WHERE (creator_id = $1 OR partner_id = $1)
                AND status IN ('active', 'pending')
                ORDER BY created_at DESC
            """, user_id)
            return [dict(row) for row in rows]

    # ==================== BOXES SYSTEM ====================
    
    async def add_box(self, user_id: int, box_type: str) -> str:
        """Add box to user inventory"""
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
        """Mark box as opened and add item"""
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

    # ==================== INVENTORY SYSTEM ====================
    
    async def get_inventory(self, user_id: int) -> Dict[str, Any]:
        """Get user's full inventory"""
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

    # ==================== STATISTICS & ADMIN ====================
    
    async def get_all_balances(self) -> List[tuple]:
        """Get all users with BST"""
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
        """Get total BST held by all users"""
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

    async def get_economy_stats(self) -> Dict[str, Any]:
        """Get comprehensive economy statistics"""
        async with self.pool.acquire() as conn:
            pool_balance = await self.get_pool_balance()
            circulation = await self.get_total_bst_in_circulation()
            user_count = await self.get_user_count()
            boxes_opened = await self.get_total_boxes_opened()
            weekly_remaining = await self.get_weekly_remaining()
            
            return {
                'pool_balance': pool_balance,
                'circulation': circulation,
                'total_supply': pool_balance + circulation,
                'user_count': user_count,
                'boxes_opened': boxes_opened,
                'weekly_remaining': weekly_remaining
            }

    async def reset_user(self, user_id: int) -> bool:
        """Reset user's BST to 0"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE users 
                SET bst_balance = 0.0, message_count = 0
                WHERE user_id = $1
            """, user_id)
            return True

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
                'total_trades': total_trades,
                'completed_trades': completed_trades,
                'active_trades': active_trades,
                'total_traded': float(total_traded) if total_traded else 0.0
            }
