import json
import asyncio
import aiosqlite
from dotenv import load_dotenv
import os

load_dotenv()

async def update_target_prices_from_json():
    # Load target prices from JSON
    with open('target_prices.json', 'r') as f:
        target_prices = json.load(f)
    
    # Connect to database
    async with aiosqlite.connect(os.getenv('DATABASE_URL', 'trade_desk.db')) as db:
        for ref, price in target_prices.items():
            await db.execute("""
                INSERT INTO target_prices (ref_number, market_price, description)
                VALUES (?, ?, ?)
                ON CONFLICT(ref_number) DO UPDATE SET 
                    market_price = excluded.market_price,
                    last_updated = CURRENT_TIMESTAMP
            """, (ref.upper(), price, f"Auto-updated from JSON"))
        
        await db.commit()
        print(f"✅ Updated {len(target_prices)} target prices")

if __name__ == "__main__":
    asyncio.run(update_target_prices_from_json())
