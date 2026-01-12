# ref_manager.py
import aiosqlite
import logging
from typing import Dict, Optional, List, Tuple
from datetime import datetime

logger = logging.getLogger("watch-engine.ref_manager")

class RefManager:
    """Manages reference prices with connection pooling support"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._pool: Optional[aiosqlite.Pool] = None
    
    async def init_pool(self, minsize: int = 1, maxsize: int = 10):
        """Initialize connection pool"""
        if self._pool is None:
            self._pool = await aiosqlite.create_pool(
                self.db_path,
                minsize=minsize,
                maxsize=maxsize,
                setup=lambda conn: conn.execute("PRAGMA journal_mode=WAL")
            )
            logger.info(f"RefManager pool initialized for {self.db_path}")
    
    async def close(self):
        """Close connection pool"""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("RefManager pool closed")
    
    async def _execute_with_pool(self, query: str, params: tuple = ()) -> aiosqlite.Cursor:
        """Execute query using connection pool"""
        if self._pool is None:
            raise RuntimeError("Connection pool not initialized. Call init_pool() first.")
        
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, params)
                await conn.commit()
                return cursor
    
    async def init_ref_table(self):
        """Initializes the target_prices table for dynamic market tracking."""
        try:
            await self._execute_with_pool("""
                CREATE TABLE IF NOT EXISTS target_prices (
                    ref_number TEXT PRIMARY KEY,
                    market_price INTEGER NOT NULL CHECK (market_price >= 0),
                    description TEXT,
                    volatility_score INTEGER DEFAULT 0,
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for performance
            await self._execute_with_pool(
                "CREATE INDEX IF NOT EXISTS idx_ref_updated ON target_prices (last_updated)"
            )
            logger.info("Target prices table initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize ref table: {e}")
            raise
    
    async def update_target_price(self, ref: str, price: int, description: Optional[str] = None):
        """Upserts a target price into the database with validation."""
        if price < 100:
            raise ValueError(f"Invalid price: {price}. Price must be at least $100")
        
        cleaned_ref = ref.upper().replace(" ", "").strip()
        if not cleaned_ref:
            raise ValueError("Reference number cannot be empty")
        
        try:
            # Get previous price to calculate volatility
            prev_price = await self.get_target_price(cleaned_ref)
            
            await self._execute_with_pool("""
                INSERT INTO target_prices (ref_number, market_price, description, last_updated)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(ref_number) DO UPDATE SET 
                    market_price = excluded.market_price,
                    description = COALESCE(excluded.description, target_prices.description),
                    last_updated = CURRENT_TIMESTAMP
            """, (cleaned_ref, price, description))
            
            # Log price changes
            if prev_price and prev_price != price:
                change_pct = ((price - prev_price) / prev_price) * 100
                logger.info(f"Price updated: {cleaned_ref} ${prev_price} → ${price} ({change_pct:+.1f}%)")
            else:
                logger.info(f"Price set: {cleaned_ref} = ${price}")
                
        except Exception as e:
            logger.error(f"Failed to update target price for {cleaned_ref}: {e}")
            raise
    
    async def get_target_price(self, ref: str) -> Optional[int]:
        """Get target price for a specific reference."""
        cleaned_ref = ref.upper().replace(" ", "").strip()
        try:
            async with (await self._execute_with_pool(
                "SELECT market_price FROM target_prices WHERE ref_number = ?",
                (cleaned_ref,)
            )) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.error(f"Failed to get target price for {cleaned_ref}: {e}")
            return None
    
    async def get_all_targets(self) -> Dict[str, int]:
        """Returns a dictionary of all target prices."""
        try:
            async with (await self._execute_with_pool(
                "SELECT ref_number, market_price FROM target_prices ORDER BY ref_number"
            )) as cursor:
                rows = await cursor.fetchall()
                return {row[0]: row[1] for row in rows}
        except Exception as e:
            logger.error(f"Failed to get all targets: {e}")
            return {}
    
    async def get_targets_with_details(self) -> List[Dict]:
        """Get all targets with full details."""
        try:
            async with (await self._execute_with_pool(
                """SELECT ref_number, market_price, description, 
                          last_updated, created_at, volatility_score
                   FROM target_prices 
                   ORDER BY ref_number"""
            )) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "ref_number": row[0],
                        "market_price": row[1],
                        "description": row[2],
                        "last_updated": row[3],
                        "created_at": row[4],
                        "volatility_score": row[5]
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"Failed to get targets with details: {e}")
            return []
    
    async def delete_target(self, ref: str) -> bool:
        """Delete a target price entry."""
        cleaned_ref = ref.upper().replace(" ", "").strip()
        try:
            async with (await self._execute_with_pool(
                "DELETE FROM target_prices WHERE ref_number = ?",
                (cleaned_ref,)
            )) as cursor:
                deleted = cursor.rowcount > 0
                if deleted:
                    logger.info(f"Deleted target price for {cleaned_ref}")
                return deleted
        except Exception as e:
            logger.error(f"Failed to delete target price for {cleaned_ref}: {e}")
            return False
    
    async def search_targets(self, query: str, limit: int = 20) -> List[Tuple[str, int]]:
        """Search for target prices by reference number."""
        search_pattern = f"%{query.upper().replace(' ', '')}%"
        try:
            async with (await self._execute_with_pool(
                """SELECT ref_number, market_price 
                   FROM target_prices 
                   WHERE ref_number LIKE ? 
                   ORDER BY ref_number 
                   LIMIT ?""",
                (search_pattern, limit)
            )) as cursor:
                return await cursor.fetchall()
        except Exception as e:
            logger.error(f"Failed to search targets: {e}")
            return []
    
    async def get_outdated_targets(self, days_old: int = 30) -> List[Dict]:
        """Get targets that haven't been updated in specified days."""
        try:
            async with (await self._execute_with_pool(
                """SELECT ref_number, market_price, last_updated
                   FROM target_prices 
                   WHERE last_updated < datetime('now', ?)
                   ORDER BY last_updated""",
                (f"-{days_old} days",)
            )) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "ref_number": row[0],
                        "market_price": row[1],
                        "last_updated": row[2],
                        "days_outdated": (datetime.now() - datetime.fromisoformat(row[2])).days
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"Failed to get outdated targets: {e}")
            return []

# Legacy functions for backward compatibility
async def init_ref_table(db_path: str):
    """Legacy function - initializes table without pooling"""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS target_prices (
                ref_number TEXT PRIMARY KEY,
                market_price INTEGER NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def update_target_price_in_db(db_path: str, ref: str, price: int):
    """Legacy function - updates price without pooling"""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            INSERT INTO target_prices (ref_number, market_price, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(ref_number) DO UPDATE SET 
                market_price = excluded.market_price,
                updated_at = CURRENT_TIMESTAMP
        """, (ref.upper().replace(" ", ""), price))
        await db.commit()

async def get_all_targets_from_db(db_path: str) -> dict:
    """Legacy function - gets all targets without pooling"""
    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT ref_number, market_price FROM target_prices") as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}
