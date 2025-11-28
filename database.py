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

    async def close(self):
        """Close database connection"""
        if self.pool:
            await self.pool.close()
            print("✅ Database disconnected")

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

    async def add_bst_direct(self, user_id: int, amount: float) -> bool:
        """Add BST directly to user (for weekly message rewards - doesn't touch main pool)"""
        async with self.pool.acquire() as conn:
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

    async def reset_user_and_return_to_pool(self, user_id: int) -> bool:
        """Reset user's BST to 0 and RETURN their balance to the MAIN pool"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Get user's current balance
                balance = await conn.fetchval(
                    "SELECT bst_balance FROM users WHERE user_id = $1",
                    user_id
                )
                
                if not balance or balance == 0:
                    # User has no BST, just reset
                    await conn.execute("""
                        UPDATE users 
                        SET bst_balance = 0.0, message_count = 0
                        WHERE user_id = $1
                    """, user_id)
                    return True
                
                # Return BST to MAIN pool (not weekly pool)
                await conn.execute("""
                    UPDATE economy_pool
                    SET pool_amount = pool_amount + $1,
                        updated_at = NOW()
                    WHERE pool_id = 1
                """, balance)
                
                # Reset user
                await conn.execute("""
                    UPDATE users 
                    SET bst_balance = 0.0, message_count = 0
                    WHERE user_id = $1
                """, user_id)
                
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
        """Get current MAIN pool balance"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT pool_amount FROM economy_pool WHERE pool_id = 1"
            )
            return float(result) if result else 0.0

    async def add_to_pool(self, amount: float) -> float:
        """Add BST to MAIN economy pool (minting) - OWNER ONLY"""
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
        """Remove BST from MAIN pool (with check)"""
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
        """Reset MAIN pool to 0 (for supply reset)"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE economy_pool 
                SET pool_amount = 0.0, updated_at = NOW() 
                WHERE pool_id = 1
            """)
            return True

    # ==================== PER-USER WEEKLY CAP ====================
    
    async def get_user_weekly_earnings(self, user_id: int) -> Dict[str, Any]:
        """Get user's current week earnings"""
        async with self.pool.acquire() as conn:
            week_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = week_start - timedelta(days=week_start.weekday())
            
            row = await conn.fetchrow("""
                INSERT INTO user_weekly_earnings (user_id, week_start, bst_earned, weekly_limit)
                VALUES ($1, $2, 0.00, 10.00)
                ON CONFLICT (user_id, week_start) DO UPDATE 
                SET user_id = user_weekly_earnings.user_id
                RETURNING *
            """, user_id, week_start.date())
            
            return dict(row) if row else None

    async def increment_user_weekly_earnings(self, user_id: int, amount: float = 1.0) -> bool:
        """Increment user's weekly BST earned (returns True if under cap)"""
        async with self.pool.acquire() as conn:
            week_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = week_start - timedelta(days=week_start.weekday())
            
            # Get current earnings
            current = await conn.fetchrow("""
                INSERT INTO user_weekly_earnings (user_id, week_start, bst_earned, weekly_limit)
                VALUES ($1, $2, 0.00, 10.00)
                ON CONFLICT (user_id, week_start) DO UPDATE 
                SET user_id = user_weekly_earnings.user_id
                RETURNING bst_earned, weekly_limit
            """, user_id, week_start.date())
            
            if not current:
                return False
            
            # Check if user is under weekly limit
            if current['bst_earned'] + amount > current['weekly_limit']:
                return False
            
            # Increment earnings
            result = await conn.execute("""
                UPDATE user_weekly_earnings
                SET bst_earned = bst_earned + $3,
                    updated_at = NOW()
                WHERE user_id = $1 AND week_start = $2
            """, user_id, week_start.date(), amount)
            
            return "UPDATE 1" in result

    async def get_user_weekly_remaining(self, user_id: int) -> float:
        """Get how much BST user can still earn this week"""
        weekly = await self.get_user_weekly_earnings(user_id)
        if not weekly:
            return 10.0
        return max(0, weekly['weekly_limit'] - weekly['bst_earned'])

    async def reset_all_weekly_earnings(self) -> bool:
        """Reset ALL users' weekly earnings (Monday reset)"""
        async with self.pool.acquire() as conn:
            week_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = week_start - timedelta(days=week_start.weekday())
            
            # Delete old week records (keeps database clean)
            await conn.execute("""
                DELETE FROM user_weekly_earnings
                WHERE week_start < $1
            """, week_start.date())
            
            return True

    # ==================== WEEKLY CAP COMPATIBILITY (for display) ====================
    
    async def get_weekly_remaining(self) -> float:
        """Get server-wide weekly remaining (for display in /pool command)"""
        # This is just for display - actual checking is per-user now
        async with self.pool.acquire() as conn:
            week_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = week_start - timedelta(days=week_start.weekday())
            
            # Get total distributed this week across all users
            total = await conn.fetchval("""
                SELECT COALESCE(SUM(bst_earned), 0)
                FROM user_weekly_earnings
                WHERE week_start = $1
            """, week_start.date())
            
            return float(total) if total else 0.0

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

    async def remove_inventory_item(self, user_id: int, item_name: str, quantity: int) -> bool:
        """Remove specific quantity of item from user's inventory"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Check current quantity
                current_qty = await conn.fetchval("""
                    SELECT quantity FROM inventory
                    WHERE user_id = $1 AND LOWER(item_name) = LOWER($2)
                """, user_id, item_name)
                
                if not current_qty or current_qty < quantity:
                    return False
                
                new_qty = current_qty - quantity
                
                if new_qty == 0:
                    # Remove item completely
                    await conn.execute("""
                        DELETE FROM inventory
                        WHERE user_id = $1 AND LOWER(item_name) = LOWER($2)
                    """, user_id, item_name)
                else:
                    # Reduce quantity
                    await conn.execute("""
                        UPDATE inventory
                        SET quantity = $3
                        WHERE user_id = $1 AND LOWER(item_name) = LOWER($2)
                    """, user_id, item_name, new_qty)
                
                return True

    async def clear_inventory(self, user_id: int) -> bool:
        """Clear ALL items from user's inventory"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM inventory
                WHERE user_id = $1
            """, user_id)
            return True

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
            weekly_distributed = await self.get_weekly_remaining()
            
            return {
                'pool_balance': pool_balance,
                'circulation': circulation,
                'total_supply': pool_balance + circulation,
                'user_count': user_count,
                'boxes_opened': boxes_opened,
                'weekly_distributed': weekly_distributed
            }

    async def reset_user(self, user_id: int) -> bool:
        """Reset user's BST to 0 (OLD VERSION - DESTROYS BST)"""
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
