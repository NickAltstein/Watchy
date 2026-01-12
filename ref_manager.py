# ref_manager.py
import aiosqlite
import logging
from typing import Dict

logger = logging.getLogger("watch-engine.refs")

async def init_ref_table(db_path: str):
    """Creates the target_prices table if it doesn't exist."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS target_prices (
                ref_number TEXT PRIMARY KEY,
                market_price INTEGER NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()
    logger.info("Target prices table ensured.")

async def update_target_price_in_db(db_path: str, ref: str, price: int):
    """Inserts or updates a target price for a specific reference."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            INSERT INTO target_prices (ref_number, market_price, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(ref_number) DO UPDATE SET 
                market_price = excluded.market_price,
                updated_at = CURRENT_TIMESTAMP
        """, (ref.upper().replace(" ", ""), price))
        await db.commit()
    logger.info(f"Updated target price for {ref}: {price}")

async def get_all_targets_from_db(db_path: str) -> Dict[str, int]:
    """Fetches all targets as a dictionary."""
    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT ref_number, market_price FROM target_prices") as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}
