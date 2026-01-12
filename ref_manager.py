import aiosqlite
import logging

logger = logging.getLogger("watch-engine.ref_manager")

async def init_ref_table(db_path: str):
    """Initializes the target_prices table for dynamic market tracking."""
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
    """Upserts a target price into the database."""
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
    """Returns a dictionary of all target prices for the memory cache."""
    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT ref_number, market_price FROM target_prices") as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}
