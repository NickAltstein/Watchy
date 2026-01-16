#!/usr/bin/env python3
"""
Database Migration Helper
Migrates data from SQLite to PostgreSQL + TimescaleDB
"""

import sqlite3
import asyncio
import asyncpg
from datetime import datetime
import sys
import os

# Configuration
SQLITE_DB = "watch_listings.db"
POSTGRES_DSN = os.getenv("DATABASE_URL", "postgresql://localhost/watchy_trading")


async def migrate_data():
    """Migrate data from SQLite to PostgreSQL"""
    
    print("🔄 Starting migration from SQLite to PostgreSQL...")
    
    # Connect to SQLite
    print(f"📂 Connecting to SQLite: {SQLITE_DB}")
    if not os.path.exists(SQLITE_DB):
        print(f"❌ SQLite database not found: {SQLITE_DB}")
        return False
    
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()
    
    # Connect to PostgreSQL
    print(f"🐘 Connecting to PostgreSQL...")
    try:
        pg_conn = await asyncpg.connect(POSTGRES_DSN)
    except Exception as e:
        print(f"❌ Failed to connect to PostgreSQL: {e}")
        return False
    
    print("✅ Connected to both databases")
    
    # Migrate sources
    print("\n📊 Migrating sources...")
    sqlite_cur.execute("SELECT DISTINCT group_name FROM trades WHERE group_name IS NOT NULL")
    sources = {}
    for row in sqlite_cur.fetchall():
        group_name = row['group_name']
        source_id = await pg_conn.fetchval(
            """INSERT INTO sources (name, source_type, description) 
               VALUES ($1, 'WHATSAPP', 'Migrated from SQLite')
               ON CONFLICT DO NOTHING
               RETURNING id""",
            group_name
        )
        if source_id:
            sources[group_name] = source_id
            print(f"  ✓ Created source: {group_name}")
    
    # Get existing sources
    existing_sources = await pg_conn.fetch("SELECT id, name FROM sources")
    for source in existing_sources:
        sources[source['name']] = source['id']
    
    print(f"✅ Migrated {len(sources)} sources")
    
    # Migrate sellers
    print("\n👥 Migrating sellers...")
    sqlite_cur.execute("SELECT DISTINCT sender_id FROM trades WHERE sender_id IS NOT NULL")
    sellers = {}
    for row in sqlite_cur.fetchall():
        sender_id = row['sender_id']
        seller_id = await pg_conn.fetchval(
            """INSERT INTO sellers (seller_identifier, seller_type) 
               VALUES ($1, 'UNKNOWN')
               ON CONFLICT (seller_identifier) DO NOTHING
               RETURNING id""",
            sender_id
        )
        if seller_id:
            sellers[sender_id] = seller_id
            print(f"  ✓ Created seller: {sender_id[:20]}...")
    
    # Get existing sellers
    existing_sellers = await pg_conn.fetch("SELECT id, seller_identifier FROM sellers")
    for seller in existing_sellers:
        sellers[seller['seller_identifier']] = seller['id']
    
    print(f"✅ Migrated {len(sellers)} sellers")
    
    # Migrate trades
    print("\n📈 Migrating trades...")
    sqlite_cur.execute("""
        SELECT * FROM trades 
        ORDER BY timestamp DESC
    """)
    
    migrated = 0
    skipped = 0
    
    for row in sqlite_cur.fetchall():
        try:
            # Map fields
            source_id = sources.get(row['group_name'])
            seller_id = sellers.get(row['sender_id'])
            
            # Determine sentiment
            sentiment = 'WTS'
            if row.get('sentiment'):
                sentiment = row['sentiment']
            
            # Insert trade
            await pg_conn.execute("""
                INSERT INTO trades (
                    ref_number, brand, model, price_usd, sentiment,
                    deal_score, alert_tier,
                    source_id, seller_id, message_id, group_name, sender_id,
                    raw_text, unique_hash, timestamp, created_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16
                )
                ON CONFLICT (unique_hash) DO NOTHING
            """,
                row.get('ref_number'),
                row.get('brand'),
                row.get('model'),
                row.get('price_usd'),
                sentiment,
                row.get('deal_score'),
                row.get('alert_tier', 'NORMAL'),
                source_id,
                seller_id,
                row.get('message_id'),
                row.get('group_name'),
                row.get('sender_id'),
                row.get('raw_text'),
                row.get('unique_hash'),
                row.get('timestamp', datetime.now()),
                row.get('created_at', datetime.now())
            )
            
            # Insert into price_history if we have a valid price
            if row.get('price_usd') and row.get('ref_number'):
                await pg_conn.execute("""
                    INSERT INTO price_history (time, ref_number, price, sentiment, source_id, seller_id)
                    VALUES ($1, $2, $3, $4, $5, $6)
                """,
                    row.get('timestamp', datetime.now()),
                    row.get('ref_number'),
                    row.get('price_usd'),
                    sentiment,
                    source_id,
                    seller_id
                )
            
            migrated += 1
            if migrated % 100 == 0:
                print(f"  ⏳ Migrated {migrated} trades...")
        
        except Exception as e:
            skipped += 1
            if skipped % 10 == 0:
                print(f"  ⚠️  Skipped {skipped} trades (duplicates or errors)")
    
    print(f"✅ Migrated {migrated} trades, skipped {skipped}")
    
    # Calculate market prices
    print("\n💰 Calculating market prices...")
    await pg_conn.execute("""
        INSERT INTO market_prices (ref_number, market_price, avg_price, min_price, max_price, sample_size)
        SELECT 
            ref_number,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_usd)::INTEGER AS market_price,
            AVG(price_usd)::INTEGER AS avg_price,
            MIN(price_usd) AS min_price,
            MAX(price_usd) AS max_price,
            COUNT(*) AS sample_size
        FROM trades
        WHERE deleted_at IS NULL 
            AND price_usd > 0
            AND timestamp > NOW() - INTERVAL '90 days'
        GROUP BY ref_number
        ON CONFLICT (ref_number) DO UPDATE SET
            market_price = EXCLUDED.market_price,
            avg_price = EXCLUDED.avg_price,
            min_price = EXCLUDED.min_price,
            max_price = EXCLUDED.max_price,
            sample_size = EXCLUDED.sample_size,
            last_calculated_at = NOW()
    """)
    
    market_count = await pg_conn.fetchval("SELECT COUNT(*) FROM market_prices")
    print(f"✅ Calculated prices for {market_count} references")
    
    # Close connections
    sqlite_conn.close()
    await pg_conn.close()
    
    print("\n🎉 Migration completed successfully!")
    print(f"   Trades: {migrated}")
    print(f"   Sources: {len(sources)}")
    print(f"   Sellers: {len(sellers)}")
    print(f"   Market Prices: {market_count}")
    
    return True


async def verify_migration():
    """Verify migration was successful"""
    print("\n🔍 Verifying migration...")
    
    pg_conn = await asyncpg.connect(POSTGRES_DSN)
    
    # Count records
    trade_count = await pg_conn.fetchval("SELECT COUNT(*) FROM trades WHERE deleted_at IS NULL")
    price_count = await pg_conn.fetchval("SELECT COUNT(*) FROM price_history")
    source_count = await pg_conn.fetchval("SELECT COUNT(*) FROM sources WHERE deleted_at IS NULL")
    seller_count = await pg_conn.fetchval("SELECT COUNT(*) FROM sellers WHERE deleted_at IS NULL")
    
    print(f"  📊 Trades: {trade_count}")
    print(f"  📈 Price History: {price_count}")
    print(f"  📂 Sources: {source_count}")
    print(f"  👥 Sellers: {seller_count}")
    
    # Sample query
    recent = await pg_conn.fetch("""
        SELECT ref_number, brand, model, price_usd, timestamp
        FROM trades
        WHERE deleted_at IS NULL
        ORDER BY timestamp DESC
        LIMIT 5
    """)
    
    print("\n  📝 Recent trades:")
    for trade in recent:
        print(f"    • {trade['ref_number']} - {trade['brand']} {trade['model']} - ${trade['price_usd']}")
    
    await pg_conn.close()
    print("\n✅ Verification complete")


if __name__ == "__main__":
    print("=" * 60)
    print("  Watch Trading Platform - Database Migration")
    print("=" * 60)
    
    try:
        # Run migration
        success = asyncio.run(migrate_data())
        
        if success:
            # Verify
            asyncio.run(verify_migration())
            sys.exit(0)
        else:
            print("\n❌ Migration failed")
            sys.exit(1)
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Migration error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
