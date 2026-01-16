# PostgreSQL + TimescaleDB Database Setup

This directory contains the database schema for the Watch Trading Platform, optimized for time-series price data with TimescaleDB.

## Prerequisites

- PostgreSQL 14+ 
- TimescaleDB 2.8+
- Extensions: `timescaledb`, `pg_trgm`, `btree_gin`, `uuid-ossp`

## Quick Start

### 1. Install PostgreSQL and TimescaleDB

```bash
# Ubuntu/Debian
sudo apt install postgresql-14 postgresql-14-timescaledb

# macOS
brew install postgresql timescaledb

# Enable TimescaleDB
sudo timescaledb-tune
```

### 2. Create Database

```bash
# Create database
createdb watchy_trading

# Enable TimescaleDB
psql watchy_trading -c "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"
```

### 3. Run Schema

```bash
psql watchy_trading < schema.sql
```

## Database Structure

### Core Tables

1. **users** - User accounts with authentication and subscriptions
2. **sources** - Data sources (WhatsApp, Telegram, etc.)
3. **sellers** - Seller reputation tracking
4. **trades** - Main table for trade listings (partitioned by date)
5. **market_prices** - Calculated market prices for references
6. **price_history** - TimescaleDB hypertable for time-series data
7. **alerts** - User price alerts
8. **watchlist** - User saved references

### Key Features

#### Time-Series Optimization
- **TimescaleDB Hypertable**: `price_history` table optimized for time-series queries
- **Continuous Aggregates**: Pre-computed hourly and daily stats
- **Retention Policy**: Automatic data cleanup (2 years)
- **Compression**: Automatic compression of old data

#### Partitioning
- **trades** table partitioned by month for performance
- Automatic partition creation for future months
- Efficient querying by date range

#### Full-Text Search
- `pg_trgm` extension for fuzzy reference matching
- Full-text search vectors on trade descriptions
- Optimized GIN indexes

#### Indexing Strategy
- B-tree indexes for exact lookups (ref_number, price)
- GIN indexes for JSONB columns and arrays
- Composite indexes for common query patterns
- Partial indexes for active records only

## Usage Examples

### Query Recent Trades
```sql
SELECT * FROM active_trades 
WHERE ref_number = '126610LN' 
ORDER BY timestamp DESC 
LIMIT 10;
```

### Get Price Statistics
```sql
SELECT * FROM get_price_stats('126610LN', 90);
```

### Full-Text Search
```sql
SELECT * FROM search_trades('rolex submariner blue', 20);
```

### Get Trending References
```sql
SELECT * FROM trending_references;
```

### Query Time-Series Data
```sql
-- Get hourly price stats for last 7 days
SELECT * FROM price_history_hourly
WHERE ref_number = '126610LN'
  AND bucket > NOW() - INTERVAL '7 days'
ORDER BY bucket DESC;

-- Get daily stats
SELECT * FROM price_history_daily
WHERE ref_number = '126610LN'
ORDER BY bucket DESC
LIMIT 30;
```

### Get Seller Performance
```sql
SELECT * FROM seller_performance
WHERE recent_listings > 5
ORDER BY avg_deal_score DESC;
```

## Performance Tuning

### Recommended Settings

Add to `postgresql.conf`:

```conf
# TimescaleDB settings
shared_preload_libraries = 'timescaledb'

# Memory settings (adjust based on available RAM)
shared_buffers = 4GB
effective_cache_size = 12GB
maintenance_work_mem = 1GB
work_mem = 50MB

# Connection settings
max_connections = 200
max_worker_processes = 8

# Query performance
random_page_cost = 1.1
effective_io_concurrency = 200
```

### Indexes

All key indexes are created in `schema.sql`. Monitor query performance with:

```sql
-- Find slow queries
SELECT * FROM pg_stat_statements 
ORDER BY total_exec_time DESC 
LIMIT 10;

-- Check index usage
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
ORDER BY idx_scan ASC;
```

## Maintenance

### Vacuum and Analyze

```bash
# Run nightly
vacuumdb -z -d watchy_trading
```

### Partition Management

Partitions are created automatically for future months. To create manually:

```sql
SELECT create_next_partition();
```

### Backup

```bash
# Full backup
pg_dump watchy_trading > backup_$(date +%Y%m%d).sql

# Schema only
pg_dump --schema-only watchy_trading > schema_backup.sql

# Data only
pg_dump --data-only watchy_trading > data_backup.sql
```

### Restore

```bash
psql watchy_trading < backup_20260116.sql
```

## Monitoring

### Key Metrics

```sql
-- Database size
SELECT pg_size_pretty(pg_database_size('watchy_trading'));

-- Table sizes
SELECT 
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename))
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Hypertable stats
SELECT * FROM timescaledb_information.hypertables;

-- Chunk info
SELECT * FROM timescaledb_information.chunks
WHERE hypertable_name = 'price_history';
```

## Security

### User Roles

Two roles are created:
- `analytics_readonly` - Read-only access for analytics
- `app_user` - Read/write for application

### Create Application User

```sql
CREATE USER myapp WITH PASSWORD 'secure_password';
GRANT app_user TO myapp;
```

### Connection String

```
postgresql://myapp:secure_password@localhost:5432/watchy_trading
```

## Migration from SQLite

If migrating from the existing SQLite database:

```bash
# Export from SQLite
sqlite3 watch_listings.db .dump > sqlite_dump.sql

# Import to PostgreSQL (after adapting schema)
psql watchy_trading < sqlite_migration.sql
```

## Troubleshooting

### TimescaleDB Not Loaded

```sql
-- Check if loaded
SELECT * FROM pg_extension WHERE extname = 'timescaledb';

-- If not, enable it
CREATE EXTENSION timescaledb CASCADE;
```

### Partition Not Found

```sql
-- Check existing partitions
SELECT tablename FROM pg_tables 
WHERE tablename LIKE 'trades_%';

-- Create missing partition
SELECT create_next_partition();
```

### Slow Queries

```sql
-- Enable query logging
ALTER DATABASE watchy_trading SET log_min_duration_statement = 1000;

-- Analyze table
ANALYZE trades;
```

## Development

### Reset Database

```bash
# Drop and recreate
dropdb watchy_trading
createdb watchy_trading
psql watchy_trading < schema.sql
```

### Test Data

Sample data is included in `schema.sql`. To add more:

```sql
-- Generate 1000 random price points
INSERT INTO price_history (time, ref_number, price, sentiment)
SELECT 
    NOW() - (random() * INTERVAL '180 days'),
    '126610LN',
    20000 + (random() * 4000)::INTEGER,
    'WTS'
FROM generate_series(1, 1000);
```

## Support

For issues or questions:
- Check PostgreSQL logs: `/var/log/postgresql/postgresql-14-main.log`
- Check TimescaleDB docs: https://docs.timescale.com/
- Run EXPLAIN ANALYZE on slow queries

## Version History

- **1.0** (2026-01-16) - Initial schema with TimescaleDB support
