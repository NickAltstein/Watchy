-- PostgreSQL + TimescaleDB Schema for Watch Trading Platform
-- Optimized for time-series price data with full-text search and analytics
-- Version: 1.0
-- Last Updated: 2026-01-16

-- =============================================================================
-- EXTENSIONS
-- =============================================================================

-- Enable TimescaleDB for time-series data
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Enable fuzzy text search (for reference number matching)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Enable full-text search
CREATE EXTENSION IF NOT EXISTS btree_gin;

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- ENUMS
-- =============================================================================

CREATE TYPE sentiment_type AS ENUM ('WTS', 'WTB', 'WTT');
CREATE TYPE alert_tier AS ENUM ('URGENT', 'PUSH', 'NORMAL', 'SKIP', 'OVERPRICED');
CREATE TYPE risk_level AS ENUM ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL');
CREATE TYPE condition_grade AS ENUM ('NIB', 'UNWORN', 'EXCELLENT', 'GOOD', 'FAIR', 'POOR', 'UNKNOWN');
CREATE TYPE seller_type AS ENUM ('VERIFIED_DEALER', 'ESTABLISHED_DEALER', 'PRIVATE_TRUSTED', 'PRIVATE_NEW', 'UNKNOWN');
CREATE TYPE source_type AS ENUM ('WHATSAPP', 'TELEGRAM', 'DISCORD', 'FORUM', 'API', 'MANUAL');
CREATE TYPE subscription_tier AS ENUM ('FREE', 'BASIC', 'PRO', 'ENTERPRISE');
CREATE TYPE alert_status AS ENUM ('ACTIVE', 'PAUSED', 'TRIGGERED', 'EXPIRED');
CREATE TYPE notification_channel AS ENUM ('EMAIL', 'WEBHOOK', 'SMS', 'PUSH');

-- =============================================================================
-- TABLES
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. USERS TABLE
-- User accounts and authentication
-- -----------------------------------------------------------------------------
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    api_key VARCHAR(64) UNIQUE,
    
    -- Profile
    full_name VARCHAR(255),
    subscription_tier subscription_tier DEFAULT 'FREE',
    subscription_expires_at TIMESTAMPTZ,
    
    -- Rate limiting
    rate_limit_per_minute INTEGER DEFAULT 100,
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    last_login_at TIMESTAMPTZ,
    
    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    
    -- Constraints
    CONSTRAINT valid_email CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'),
    CONSTRAINT valid_username CHECK (username ~* '^[a-zA-Z0-9_-]{3,50}$')
);

CREATE INDEX idx_users_email ON users(email) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_api_key ON users(api_key) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_subscription ON users(subscription_tier, subscription_expires_at);

-- -----------------------------------------------------------------------------
-- 2. SOURCES TABLE
-- Data sources (WhatsApp groups, Telegram channels, etc.)
-- -----------------------------------------------------------------------------
CREATE TABLE sources (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    source_type source_type NOT NULL,
    
    -- Metadata
    description TEXT,
    external_id VARCHAR(255), -- Group/Channel ID
    member_count INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Configuration
    config JSONB DEFAULT '{}',
    
    -- Stats
    total_messages INTEGER DEFAULT 0,
    total_trades INTEGER DEFAULT 0,
    
    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    
    UNIQUE(source_type, external_id)
);

CREATE INDEX idx_sources_type ON sources(source_type) WHERE deleted_at IS NULL;
CREATE INDEX idx_sources_active ON sources(is_active) WHERE deleted_at IS NULL;
CREATE INDEX idx_sources_config ON sources USING GIN(config);

-- -----------------------------------------------------------------------------
-- 3. SELLERS TABLE
-- Seller reputation and performance tracking
-- -----------------------------------------------------------------------------
CREATE TABLE sellers (
    id SERIAL PRIMARY KEY,
    seller_identifier VARCHAR(255) UNIQUE NOT NULL, -- Phone, username, etc.
    seller_type seller_type DEFAULT 'UNKNOWN',
    
    -- Reputation
    rating DECIMAL(3,2) CHECK (rating >= 0 AND rating <= 5),
    total_transactions INTEGER DEFAULT 0,
    successful_transactions INTEGER DEFAULT 0,
    
    -- Performance metrics
    avg_response_time_hours DECIMAL(10,2),
    avg_deal_score INTEGER,
    
    -- Profile
    name VARCHAR(255),
    location VARCHAR(255),
    verified_at TIMESTAMPTZ,
    
    -- Notes
    notes TEXT,
    metadata JSONB DEFAULT '{}',
    
    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_sellers_identifier ON sellers(seller_identifier) WHERE deleted_at IS NULL;
CREATE INDEX idx_sellers_type ON sellers(seller_type);
CREATE INDEX idx_sellers_rating ON sellers(rating DESC NULLS LAST);
CREATE INDEX idx_sellers_metadata ON sellers USING GIN(metadata);

-- -----------------------------------------------------------------------------
-- 4. TRADES TABLE (Main table - Partitioned by date)
-- All parsed trade listings
-- -----------------------------------------------------------------------------
CREATE TABLE trades (
    id BIGSERIAL,
    
    -- Core trade data
    ref_number VARCHAR(50) NOT NULL,
    brand VARCHAR(100),
    model VARCHAR(255),
    price_usd INTEGER NOT NULL CHECK (price_usd > 0),
    sentiment sentiment_type DEFAULT 'WTS',
    
    -- Scoring
    deal_score INTEGER,
    alert_tier alert_tier,
    discount_percentage DECIMAL(5,2),
    
    -- Condition
    condition condition_grade DEFAULT 'UNKNOWN',
    has_box BOOLEAN DEFAULT FALSE,
    has_papers BOOLEAN DEFAULT FALSE,
    has_warranty BOOLEAN DEFAULT FALSE,
    is_full_set BOOLEAN DEFAULT FALSE,
    
    -- Risk assessment
    risk_level risk_level,
    risk_score INTEGER,
    red_flags JSONB DEFAULT '[]',
    
    -- Source tracking
    source_id INTEGER REFERENCES sources(id),
    seller_id INTEGER REFERENCES sellers(id),
    message_id VARCHAR(255),
    group_name VARCHAR(255),
    sender_id VARCHAR(255),
    
    -- Content
    raw_text TEXT,
    description TEXT,
    image_url VARCHAR(500),
    
    -- Deduplication
    unique_hash VARCHAR(64) UNIQUE,
    
    -- Full-text search
    search_vector tsvector,
    
    -- Additional data
    metadata JSONB DEFAULT '{}',
    
    -- Audit
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    
    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

-- Create partitions for current and future months
CREATE TABLE trades_2026_01 PARTITION OF trades
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
CREATE TABLE trades_2026_02 PARTITION OF trades
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
CREATE TABLE trades_2026_03 PARTITION OF trades
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

-- Indexes on trades
CREATE INDEX idx_trades_ref_number ON trades(ref_number, timestamp DESC);
CREATE INDEX idx_trades_brand ON trades(brand) WHERE deleted_at IS NULL;
CREATE INDEX idx_trades_price ON trades(price_usd);
CREATE INDEX idx_trades_sentiment ON trades(sentiment);
CREATE INDEX idx_trades_alert_tier ON trades(alert_tier);
CREATE INDEX idx_trades_timestamp ON trades(timestamp DESC);
CREATE INDEX idx_trades_source ON trades(source_id, timestamp DESC);
CREATE INDEX idx_trades_seller ON trades(seller_id, timestamp DESC);
CREATE INDEX idx_trades_unique_hash ON trades(unique_hash);
CREATE INDEX idx_trades_search ON trades USING GIN(search_vector);
CREATE INDEX idx_trades_metadata ON trades USING GIN(metadata);

-- Full-text search trigger
CREATE OR REPLACE FUNCTION trades_search_trigger() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := 
        setweight(to_tsvector('english', COALESCE(NEW.ref_number, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.brand, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.model, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.description, '')), 'C') ||
        setweight(to_tsvector('english', COALESCE(NEW.raw_text, '')), 'D');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trades_search_update
    BEFORE INSERT OR UPDATE OF ref_number, brand, model, description, raw_text
    ON trades
    FOR EACH ROW
    EXECUTE FUNCTION trades_search_trigger();

-- -----------------------------------------------------------------------------
-- 5. MARKET_PRICES TABLE
-- Current calculated market prices for each reference
-- -----------------------------------------------------------------------------
CREATE TABLE market_prices (
    id SERIAL PRIMARY KEY,
    ref_number VARCHAR(50) UNIQUE NOT NULL,
    
    -- Price data
    market_price INTEGER NOT NULL CHECK (market_price > 0),
    min_price INTEGER,
    max_price INTEGER,
    avg_price INTEGER,
    median_price INTEGER,
    
    -- Statistics
    sample_size INTEGER DEFAULT 0,
    confidence_score DECIMAL(5,2) CHECK (confidence_score >= 0 AND confidence_score <= 100),
    volatility DECIMAL(10,2),
    
    -- Trend analysis
    trend_direction VARCHAR(10) CHECK (trend_direction IN ('up', 'down', 'stable', 'unknown')),
    trend_strength DECIMAL(5,2),
    price_change_30d DECIMAL(5,2),
    price_change_90d DECIMAL(5,2),
    
    -- Metadata
    description TEXT,
    metadata JSONB DEFAULT '{}',
    
    -- Audit
    last_calculated_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_market_prices_ref ON market_prices(ref_number) WHERE deleted_at IS NULL;
CREATE INDEX idx_market_prices_price ON market_prices(market_price);
CREATE INDEX idx_market_prices_trend ON market_prices(trend_direction);
CREATE INDEX idx_market_prices_updated ON market_prices(last_calculated_at DESC);
CREATE INDEX idx_market_prices_metadata ON market_prices USING GIN(metadata);

-- -----------------------------------------------------------------------------
-- 6. PRICE_HISTORY TABLE (TimescaleDB Hypertable)
-- Time-series price data for analytics
-- -----------------------------------------------------------------------------
CREATE TABLE price_history (
    time TIMESTAMPTZ NOT NULL,
    ref_number VARCHAR(50) NOT NULL,
    
    -- Price data
    price INTEGER NOT NULL CHECK (price > 0),
    deal_score INTEGER,
    
    -- Context
    sentiment sentiment_type DEFAULT 'WTS',
    condition condition_grade DEFAULT 'UNKNOWN',
    source_id INTEGER,
    seller_id INTEGER,
    trade_id BIGINT,
    
    -- Metadata
    metadata JSONB DEFAULT '{}'
);

-- Convert to hypertable (time-series optimized)
SELECT create_hypertable('price_history', 'time', 
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

-- Indexes on price_history
CREATE INDEX idx_price_history_ref_time ON price_history(ref_number, time DESC);
CREATE INDEX idx_price_history_source ON price_history(source_id, time DESC);
CREATE INDEX idx_price_history_metadata ON price_history USING GIN(metadata);

-- Continuous aggregate for hourly stats
CREATE MATERIALIZED VIEW price_history_hourly
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', time) AS bucket,
    ref_number,
    COUNT(*) AS trade_count,
    AVG(price)::INTEGER AS avg_price,
    MIN(price) AS min_price,
    MAX(price) AS max_price,
    STDDEV(price)::INTEGER AS price_stddev
FROM price_history
GROUP BY bucket, ref_number
WITH NO DATA;

-- Refresh policy for continuous aggregate
SELECT add_continuous_aggregate_policy('price_history_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour'
);

-- Retention policy (keep 2 years)
SELECT add_retention_policy('price_history', INTERVAL '2 years');

-- Continuous aggregate for daily stats
CREATE MATERIALIZED VIEW price_history_daily
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 day', time) AS bucket,
    ref_number,
    COUNT(*) AS trade_count,
    AVG(price)::INTEGER AS avg_price,
    MIN(price) AS min_price,
    MAX(price) AS max_price,
    STDDEV(price)::INTEGER AS price_stddev,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price)::INTEGER AS median_price
FROM price_history
GROUP BY bucket, ref_number
WITH NO DATA;

SELECT add_continuous_aggregate_policy('price_history_daily',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day'
);

-- -----------------------------------------------------------------------------
-- 7. ALERTS TABLE
-- User price alerts and notifications
-- -----------------------------------------------------------------------------
CREATE TABLE alerts (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Alert configuration
    ref_number VARCHAR(50) NOT NULL,
    target_price INTEGER CHECK (target_price > 0),
    condition VARCHAR(20) CHECK (condition IN ('below', 'above', 'at')),
    
    -- Notification settings
    notification_channels notification_channel[] DEFAULT ARRAY['EMAIL']::notification_channel[],
    webhook_url VARCHAR(500),
    
    -- Status
    status alert_status DEFAULT 'ACTIVE',
    trigger_count INTEGER DEFAULT 0,
    last_triggered_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    
    -- Metadata
    notes TEXT,
    metadata JSONB DEFAULT '{}',
    
    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    
    CONSTRAINT valid_expiry CHECK (expires_at IS NULL OR expires_at > created_at)
);

CREATE INDEX idx_alerts_user ON alerts(user_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_alerts_ref ON alerts(ref_number) WHERE status = 'ACTIVE';
CREATE INDEX idx_alerts_status ON alerts(status) WHERE deleted_at IS NULL;
CREATE INDEX idx_alerts_expires ON alerts(expires_at) WHERE status = 'ACTIVE';

-- -----------------------------------------------------------------------------
-- 8. WATCHLIST TABLE
-- User's saved references with custom notes
-- -----------------------------------------------------------------------------
CREATE TABLE watchlist (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ref_number VARCHAR(50) NOT NULL,
    
    -- Custom data
    target_price INTEGER,
    notes TEXT,
    tags VARCHAR(50)[],
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Metadata
    metadata JSONB DEFAULT '{}',
    
    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    
    UNIQUE(user_id, ref_number)
);

CREATE INDEX idx_watchlist_user ON watchlist(user_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_watchlist_ref ON watchlist(ref_number) WHERE is_active = TRUE;
CREATE INDEX idx_watchlist_tags ON watchlist USING GIN(tags);

-- =============================================================================
-- TRIGGERS
-- =============================================================================

-- Generic updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply updated_at trigger to all tables
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_sources_updated_at BEFORE UPDATE ON sources
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_sellers_updated_at BEFORE UPDATE ON sellers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_trades_updated_at BEFORE UPDATE ON trades
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_market_prices_updated_at BEFORE UPDATE ON market_prices
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_alerts_updated_at BEFORE UPDATE ON alerts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_watchlist_updated_at BEFORE UPDATE ON watchlist
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- VIEWS
-- =============================================================================

-- View for active trades with enriched data
CREATE VIEW active_trades AS
SELECT 
    t.id,
    t.ref_number,
    t.brand,
    t.model,
    t.price_usd,
    t.sentiment,
    t.deal_score,
    t.alert_tier,
    t.discount_percentage,
    t.condition,
    t.risk_level,
    t.timestamp,
    s.name AS source_name,
    s.source_type,
    sel.name AS seller_name,
    sel.rating AS seller_rating,
    mp.market_price,
    mp.trend_direction
FROM trades t
LEFT JOIN sources s ON t.source_id = s.id
LEFT JOIN sellers sel ON t.seller_id = sel.id
LEFT JOIN market_prices mp ON t.ref_number = mp.ref_number
WHERE t.deleted_at IS NULL
    AND t.sentiment = 'WTS'
ORDER BY t.timestamp DESC;

-- View for trending references
CREATE VIEW trending_references AS
SELECT 
    ref_number,
    COUNT(*) AS listing_count_24h,
    AVG(price_usd)::INTEGER AS avg_price_24h,
    MIN(price_usd) AS min_price_24h,
    MAX(price_usd) AS max_price_24h,
    COUNT(DISTINCT source_id) AS source_count
FROM trades
WHERE timestamp > NOW() - INTERVAL '24 hours'
    AND deleted_at IS NULL
    AND sentiment = 'WTS'
GROUP BY ref_number
HAVING COUNT(*) >= 3
ORDER BY listing_count_24h DESC, avg_price_24h DESC;

-- View for seller performance
CREATE VIEW seller_performance AS
SELECT 
    sel.id,
    sel.seller_identifier,
    sel.seller_type,
    sel.rating,
    sel.total_transactions,
    COUNT(t.id) AS recent_listings,
    AVG(t.deal_score)::INTEGER AS avg_deal_score,
    AVG(t.price_usd)::INTEGER AS avg_price,
    MIN(t.timestamp) AS first_listing,
    MAX(t.timestamp) AS last_listing
FROM sellers sel
LEFT JOIN trades t ON sel.id = t.seller_id 
    AND t.timestamp > NOW() - INTERVAL '90 days'
    AND t.deleted_at IS NULL
WHERE sel.deleted_at IS NULL
GROUP BY sel.id, sel.seller_identifier, sel.seller_type, sel.rating, sel.total_transactions;

-- =============================================================================
-- FUNCTIONS
-- =============================================================================

-- Function to get price statistics for a reference
CREATE OR REPLACE FUNCTION get_price_stats(
    p_ref_number VARCHAR(50),
    p_days INTEGER DEFAULT 90
)
RETURNS TABLE (
    ref_number VARCHAR(50),
    sample_size BIGINT,
    avg_price INTEGER,
    min_price INTEGER,
    max_price INTEGER,
    median_price INTEGER,
    std_dev INTEGER,
    price_change_pct DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    WITH stats AS (
        SELECT 
            ph.ref_number,
            COUNT(*) AS sample_size,
            AVG(ph.price)::INTEGER AS avg_price,
            MIN(ph.price) AS min_price,
            MAX(ph.price) AS max_price,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ph.price)::INTEGER AS median_price,
            STDDEV(ph.price)::INTEGER AS std_dev
        FROM price_history ph
        WHERE ph.ref_number = p_ref_number
            AND ph.time > NOW() - (p_days || ' days')::INTERVAL
        GROUP BY ph.ref_number
    ),
    first_last AS (
        SELECT 
            (SELECT price FROM price_history 
             WHERE ref_number = p_ref_number 
                AND time > NOW() - (p_days || ' days')::INTERVAL
             ORDER BY time ASC LIMIT 1) AS first_price,
            (SELECT price FROM price_history 
             WHERE ref_number = p_ref_number 
             ORDER BY time DESC LIMIT 1) AS last_price
    )
    SELECT 
        s.ref_number,
        s.sample_size,
        s.avg_price,
        s.min_price,
        s.max_price,
        s.median_price,
        s.std_dev,
        CASE 
            WHEN fl.first_price > 0 THEN 
                ((fl.last_price - fl.first_price)::DECIMAL / fl.first_price * 100)
            ELSE 0
        END AS price_change_pct
    FROM stats s
    CROSS JOIN first_last fl;
END;
$$ LANGUAGE plpgsql;

-- Function to search trades with full-text search
CREATE OR REPLACE FUNCTION search_trades(
    p_query TEXT,
    p_limit INTEGER DEFAULT 20
)
RETURNS TABLE (
    id BIGINT,
    ref_number VARCHAR(50),
    brand VARCHAR(100),
    model VARCHAR(255),
    price_usd INTEGER,
    timestamp TIMESTAMPTZ,
    rank REAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        t.id,
        t.ref_number,
        t.brand,
        t.model,
        t.price_usd,
        t.timestamp,
        ts_rank(t.search_vector, query) AS rank
    FROM trades t,
         plainto_tsquery('english', p_query) query
    WHERE t.search_vector @@ query
        AND t.deleted_at IS NULL
    ORDER BY rank DESC, t.timestamp DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- SAMPLE DATA
-- =============================================================================

-- Sample users
INSERT INTO users (email, username, password_hash, subscription_tier) VALUES
('demo@watchtrader.com', 'demo_user', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5I3fJ7J7J7J7J', 'PRO'),
('test@example.com', 'test_user', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5I3fJ7J7J7J7J', 'FREE');

-- Sample sources
INSERT INTO sources (name, source_type, description, external_id, member_count) VALUES
('Watch Dealers NYC', 'WHATSAPP', 'Premium watch dealers group', '120363123456789@g.us', 250),
('Rolex Trading', 'TELEGRAM', 'Rolex trading channel', '-1001234567890', 1500),
('Watch Talk Forum', 'FORUM', 'Community watch forum', 'watchtalk-main', 5000);

-- Sample sellers
INSERT INTO sellers (seller_identifier, seller_type, name, rating, total_transactions) VALUES
('+1234567890', 'VERIFIED_DEALER', 'Premium Watches Inc', 4.8, 150),
('+9876543210', 'PRIVATE_TRUSTED', 'John Collector', 4.5, 45),
('dealer@example.com', 'ESTABLISHED_DEALER', 'Watch Gallery', 4.7, 200);

-- Sample market prices
INSERT INTO market_prices (ref_number, market_price, min_price, max_price, avg_price, sample_size, confidence_score, trend_direction) VALUES
('126610LN', 21500, 20000, 23000, 21450, 47, 85.5, 'stable'),
('116500LN', 38000, 36000, 42000, 38500, 32, 78.2, 'up'),
('5711/1A-010', 85000, 80000, 95000, 87500, 15, 72.0, 'down'),
('126710BLRO', 24500, 23000, 26000, 24600, 38, 82.3, 'stable');

-- Sample trades
INSERT INTO trades (ref_number, brand, model, price_usd, sentiment, deal_score, alert_tier, condition, source_id, seller_id, raw_text, unique_hash, timestamp) VALUES
('126610LN', 'Rolex', 'Submariner Date', 21500, 'WTS', 50, 'NORMAL', 'EXCELLENT', 1, 1, 'WTS Rolex Sub 126610LN. 2023. Excellent condition. Full set.', md5('126610LN-21500-1'), NOW() - INTERVAL '2 hours'),
('116500LN', 'Rolex', 'Daytona', 36000, 'WTS', 220, 'PUSH', 'NIB', 1, 1, 'WTS Rolex Daytona 116500LN. Brand new in box. Papers dated 2024.', md5('116500LN-36000-1'), NOW() - INTERVAL '5 hours'),
('5711/1A-010', 'Patek Philippe', 'Nautilus', 82000, 'WTS', 180, 'NORMAL', 'GOOD', 2, 2, 'WTS PP Nautilus 5711. Good condition. Box and papers.', md5('5711-82000-1'), NOW() - INTERVAL '1 day');

-- Sample price history
INSERT INTO price_history (time, ref_number, price, deal_score, sentiment, condition, source_id, seller_id) 
SELECT 
    NOW() - (random() * INTERVAL '90 days'),
    '126610LN',
    20000 + (random() * 3000)::INTEGER,
    (random() * 300)::INTEGER,
    'WTS',
    'EXCELLENT',
    1,
    1
FROM generate_series(1, 100);

-- =============================================================================
-- PERMISSIONS
-- =============================================================================

-- Create read-only role for analytics
CREATE ROLE analytics_readonly;
GRANT CONNECT ON DATABASE postgres TO analytics_readonly;
GRANT USAGE ON SCHEMA public TO analytics_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analytics_readonly;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO analytics_readonly;

-- Create application role with read/write
CREATE ROLE app_user;
GRANT CONNECT ON DATABASE postgres TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;

-- =============================================================================
-- MAINTENANCE
-- =============================================================================

-- Function to create next month's partition
CREATE OR REPLACE FUNCTION create_next_partition()
RETURNS void AS $$
DECLARE
    next_month DATE;
    partition_name TEXT;
    start_date TEXT;
    end_date TEXT;
BEGIN
    next_month := date_trunc('month', NOW() + INTERVAL '2 months');
    partition_name := 'trades_' || to_char(next_month, 'YYYY_MM');
    start_date := to_char(next_month, 'YYYY-MM-DD');
    end_date := to_char(next_month + INTERVAL '1 month', 'YYYY-MM-DD');
    
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF trades FOR VALUES FROM (%L) TO (%L)',
        partition_name, start_date, end_date
    );
END;
$$ LANGUAGE plpgsql;

-- Schedule to run monthly (requires pg_cron extension)
-- SELECT cron.schedule('create-partitions', '0 0 1 * *', 'SELECT create_next_partition()');

-- =============================================================================
-- DOCUMENTATION
-- =============================================================================

COMMENT ON TABLE users IS 'User accounts with authentication and subscription data';
COMMENT ON TABLE sources IS 'Data sources like WhatsApp groups and Telegram channels';
COMMENT ON TABLE sellers IS 'Seller reputation and performance tracking';
COMMENT ON TABLE trades IS 'Main table for all parsed trade listings - partitioned by date';
COMMENT ON TABLE market_prices IS 'Current calculated market prices for each reference';
COMMENT ON TABLE price_history IS 'TimescaleDB hypertable for time-series price data';
COMMENT ON TABLE alerts IS 'User price alerts with notification preferences';
COMMENT ON TABLE watchlist IS 'User saved references with custom notes';

COMMENT ON VIEW active_trades IS 'Enriched view of active WTS trades with market data';
COMMENT ON VIEW trending_references IS 'References with high listing frequency in last 24h';
COMMENT ON VIEW seller_performance IS 'Seller metrics and recent activity';

COMMENT ON FUNCTION get_price_stats IS 'Calculate price statistics for a reference over time period';
COMMENT ON FUNCTION search_trades IS 'Full-text search across trade listings';
COMMENT ON FUNCTION create_next_partition IS 'Automatically create next month partition for trades table';

-- =============================================================================
-- END OF SCHEMA
-- =============================================================================
