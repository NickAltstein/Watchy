-- ============================================================================
-- WATCHY - Luxury Watch Marketplace Database Schema
-- Migration: 001_initial.sql
-- ============================================================================
-- This migration creates the complete database schema for the watch marketplace
-- including core tables, indexes, triggers, and extensions.

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS pgvector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- CORE TABLES
-- ============================================================================

-- Listings: Watch listings from WhatsApp groups
CREATE TABLE listings (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID DEFAULT uuid_generate_v4() UNIQUE NOT NULL,
    
    -- Watch details
    brand VARCHAR(100) NOT NULL,
    model VARCHAR(200) NOT NULL,
    ref_number VARCHAR(50),
    year INTEGER,
    condition VARCHAR(50),
    condition_score DECIMAL(3,1) CHECK (condition_score >= 0 AND condition_score <= 10),
    
    -- Pricing
    price_usd INTEGER,
    asking_price_usd INTEGER,
    market_price_usd INTEGER,
    deal_score INTEGER DEFAULT 0,
    discount_percent DECIMAL(5,2),
    
    -- Classification
    sentiment VARCHAR(10) CHECK (sentiment IN ('WTS', 'WTB', 'WTT')),
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'sold', 'expired', 'removed')),
    
    -- Metadata
    description TEXT,
    has_box BOOLEAN DEFAULT false,
    has_papers BOOLEAN DEFAULT false,
    is_full_set BOOLEAN DEFAULT false,
    
    -- AI processing
    ai_confidence DECIMAL(3,2) CHECK (ai_confidence >= 0 AND ai_confidence <= 1),
    ai_model VARCHAR(50),
    embedding vector(1536),  -- For semantic search with OpenAI embeddings
    
    -- Source tracking (will add FK constraint later)
    whatsapp_group_id BIGINT,
    sender_phone VARCHAR(20),
    sender_name VARCHAR(200),
    message_id VARCHAR(100),
    original_text TEXT,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    posted_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,
    
    -- Search
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('english', 
            COALESCE(brand, '') || ' ' || 
            COALESCE(model, '') || ' ' || 
            COALESCE(ref_number, '') || ' ' ||
            COALESCE(description, '')
        )
    ) STORED
);

-- Listing images
CREATE TABLE listing_images (
    id BIGSERIAL PRIMARY KEY,
    listing_id BIGINT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    image_url TEXT NOT NULL,
    thumbnail_url TEXT,
    is_primary BOOLEAN DEFAULT false,
    width INTEGER,
    height INTEGER,
    file_size INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT unique_primary_per_listing UNIQUE (listing_id, is_primary) DEFERRABLE INITIALLY DEFERRED
);

-- WhatsApp connections (linked phone numbers)
CREATE TABLE whatsapp_connections (
    id BIGSERIAL PRIMARY KEY,
    team_id INTEGER NOT NULL,  -- Will add FK constraint after teams table exists
    phone_number VARCHAR(20) NOT NULL UNIQUE,
    display_name VARCHAR(200),
    status VARCHAR(20) DEFAULT 'disconnected' CHECK (status IN ('connected', 'disconnected', 'qr_pending', 'error')),
    session_data JSONB,  -- Baileys session credentials
    last_connected_at TIMESTAMP WITH TIME ZONE,
    last_error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Watched WhatsApp groups
CREATE TABLE watched_groups (
    id BIGSERIAL PRIMARY KEY,
    connection_id BIGINT NOT NULL REFERENCES whatsapp_connections(id) ON DELETE CASCADE,
    group_jid VARCHAR(100) NOT NULL,  -- WhatsApp group ID
    group_name VARCHAR(200),
    is_active BOOLEAN DEFAULT true,
    total_messages INTEGER DEFAULT 0,
    total_listings INTEGER DEFAULT 0,
    last_message_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT unique_group_per_connection UNIQUE (connection_id, group_jid)
);

-- Transactions (escrow payments)
CREATE TABLE transactions (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID DEFAULT uuid_generate_v4() UNIQUE NOT NULL,
    
    -- Parties
    buyer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    seller_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    listing_id BIGINT NOT NULL REFERENCES listings(id) ON DELETE RESTRICT,
    
    -- Payment details
    amount_usd INTEGER NOT NULL,
    platform_fee_usd INTEGER NOT NULL,
    seller_payout_usd INTEGER NOT NULL,
    
    -- Status
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN (
        'pending', 'authorized', 'shipped', 'delivered', 
        'completed', 'disputed', 'refunded', 'cancelled'
    )),
    
    -- Stripe integration
    stripe_payment_intent_id VARCHAR(100) UNIQUE,
    stripe_transfer_id VARCHAR(100),
    stripe_refund_id VARCHAR(100),
    
    -- Shipping
    tracking_number VARCHAR(100),
    carrier VARCHAR(50),
    shipped_at TIMESTAMP WITH TIME ZONE,
    auto_release_at TIMESTAMP WITH TIME ZONE,  -- Auto-complete 7 days after delivery
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Dealer profiles (reputation system)
CREATE TABLE dealer_profiles (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    sender_phone VARCHAR(20) UNIQUE,  -- For non-registered dealers
    
    -- Statistics
    total_listings INTEGER DEFAULT 0,
    total_sales INTEGER DEFAULT 0,
    total_purchases INTEGER DEFAULT 0,
    total_value_usd BIGINT DEFAULT 0,
    
    -- Reputation
    reliability_score DECIMAL(3,2) DEFAULT 0.5 CHECK (reliability_score >= 0 AND reliability_score <= 1),
    positive_reviews INTEGER DEFAULT 0,
    negative_reviews INTEGER DEFAULT 0,
    response_time_hours DECIMAL(5,2),
    
    -- Verification
    is_verified BOOLEAN DEFAULT false,
    verified_at TIMESTAMP WITH TIME ZONE,
    verification_notes TEXT,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Price history (time-series data)
CREATE TABLE price_history (
    time TIMESTAMP WITH TIME ZONE NOT NULL,
    ref_number VARCHAR(50) NOT NULL,
    
    -- Aggregated statistics
    avg_price INTEGER,
    min_price INTEGER,
    max_price INTEGER,
    median_price INTEGER,
    count INTEGER,
    
    -- Market indicators
    volatility DECIMAL(5,2),
    trend VARCHAR(10) CHECK (trend IN ('rising', 'falling', 'stable')),
    
    PRIMARY KEY (time, ref_number)
);

-- Convert to TimescaleDB hypertable for efficient time-series queries
SELECT create_hypertable('price_history', 'time', if_not_exists => TRUE);

-- Saved searches (user alerts)
CREATE TABLE saved_searches (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    
    -- Filter criteria (JSONB for flexibility)
    filters JSONB NOT NULL,
    
    -- Notification preferences
    notification_channels JSONB DEFAULT '["email"]'::jsonb,
    min_deal_score INTEGER DEFAULT 200,
    is_active BOOLEAN DEFAULT true,
    
    -- Statistics
    total_matches INTEGER DEFAULT 0,
    last_match_at TIMESTAMP WITH TIME ZONE,
    last_notified_at TIMESTAMP WITH TIME ZONE,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Conversations (between buyers and sellers)
CREATE TABLE conversations (
    id BIGSERIAL PRIMARY KEY,
    listing_id BIGINT REFERENCES listings(id) ON DELETE SET NULL,
    buyer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    seller_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Status
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'archived', 'blocked')),
    
    -- Metadata
    last_message_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT unique_conversation UNIQUE (listing_id, buyer_id, seller_id)
);

-- Messages (conversation history)
CREATE TABLE messages (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Content
    content TEXT NOT NULL,
    attachments JSONB,  -- Array of attachment URLs
    
    -- Status
    is_read BOOLEAN DEFAULT false,
    read_at TIMESTAMP WITH TIME ZONE,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

-- Listings indexes
CREATE INDEX idx_listings_status_deal_score ON listings (status, deal_score DESC, created_at DESC) 
    WHERE status = 'active';
CREATE INDEX idx_listings_ref_number ON listings (ref_number, created_at DESC);
CREATE INDEX idx_listings_brand_model ON listings (brand, model);
CREATE INDEX idx_listings_price ON listings (price_usd) WHERE price_usd IS NOT NULL;
CREATE INDEX idx_listings_created_at ON listings (created_at DESC);
CREATE INDEX idx_listings_search_vector ON listings USING GIN (search_vector);
CREATE INDEX idx_listings_embedding ON listings USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Listing images
CREATE INDEX idx_listing_images_listing_id ON listing_images (listing_id);

-- WhatsApp connections
CREATE INDEX idx_whatsapp_connections_team_id ON whatsapp_connections (team_id);
CREATE INDEX idx_whatsapp_connections_status ON whatsapp_connections (status);

-- Watched groups
CREATE INDEX idx_watched_groups_connection_id ON watched_groups (connection_id);
CREATE INDEX idx_watched_groups_active ON watched_groups (is_active) WHERE is_active = true;

-- Transactions
CREATE INDEX idx_transactions_buyer_id ON transactions (buyer_id, created_at DESC);
CREATE INDEX idx_transactions_seller_id ON transactions (seller_id, created_at DESC);
CREATE INDEX idx_transactions_status ON transactions (status);
CREATE INDEX idx_transactions_stripe_payment_intent ON transactions (stripe_payment_intent_id);

-- Dealer profiles
CREATE INDEX idx_dealer_profiles_user_id ON dealer_profiles (user_id);
CREATE INDEX idx_dealer_profiles_sender_phone ON dealer_profiles (sender_phone);
CREATE INDEX idx_dealer_profiles_reliability_score ON dealer_profiles (reliability_score DESC);

-- Price history (TimescaleDB automatically creates time index)
CREATE INDEX idx_price_history_ref_number ON price_history (ref_number, time DESC);

-- Saved searches
CREATE INDEX idx_saved_searches_user_id ON saved_searches (user_id);
CREATE INDEX idx_saved_searches_active ON saved_searches (is_active) WHERE is_active = true;

-- Conversations
CREATE INDEX idx_conversations_buyer_id ON conversations (buyer_id, last_message_at DESC);
CREATE INDEX idx_conversations_seller_id ON conversations (seller_id, last_message_at DESC);
CREATE INDEX idx_conversations_listing_id ON conversations (listing_id);

-- Messages
CREATE INDEX idx_messages_conversation_id ON messages (conversation_id, created_at DESC);
CREATE INDEX idx_messages_sender_id ON messages (sender_id);

-- ============================================================================
-- TRIGGERS
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply updated_at trigger to relevant tables
CREATE TRIGGER update_listings_updated_at BEFORE UPDATE ON listings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_whatsapp_connections_updated_at BEFORE UPDATE ON whatsapp_connections
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_watched_groups_updated_at BEFORE UPDATE ON watched_groups
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_transactions_updated_at BEFORE UPDATE ON transactions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_dealer_profiles_updated_at BEFORE UPDATE ON dealer_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_saved_searches_updated_at BEFORE UPDATE ON saved_searches
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to auto-calculate deal_score
CREATE OR REPLACE FUNCTION calculate_deal_score()
RETURNS TRIGGER AS $$
BEGIN
    -- Simple deal score calculation (can be enhanced)
    IF NEW.price_usd IS NOT NULL AND NEW.market_price_usd IS NOT NULL THEN
        NEW.discount_percent := ((NEW.market_price_usd - NEW.price_usd)::DECIMAL / NEW.market_price_usd) * 100;
        NEW.deal_score := FLOOR(NEW.discount_percent * 10);
        
        -- Cap deal score at 1000
        IF NEW.deal_score > 1000 THEN
            NEW.deal_score := 1000;
        END IF;
        
        -- Floor at 0
        IF NEW.deal_score < 0 THEN
            NEW.deal_score := 0;
        END IF;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER calculate_listing_deal_score BEFORE INSERT OR UPDATE ON listings
    FOR EACH ROW EXECUTE FUNCTION calculate_deal_score();

-- Function to update dealer profile statistics
CREATE OR REPLACE FUNCTION update_dealer_stats()
RETURNS TRIGGER AS $$
DECLARE
    dealer_user_id INTEGER;
BEGIN
    -- Find dealer by sender_phone if not registered
    SELECT user_id INTO dealer_user_id 
    FROM dealer_profiles 
    WHERE sender_phone = NEW.sender_phone;
    
    -- Update or create dealer profile
    INSERT INTO dealer_profiles (sender_phone, total_listings)
    VALUES (NEW.sender_phone, 1)
    ON CONFLICT (sender_phone) 
    DO UPDATE SET 
        total_listings = dealer_profiles.total_listings + 1,
        updated_at = CURRENT_TIMESTAMP;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_dealer_stats_on_listing AFTER INSERT ON listings
    FOR EACH ROW EXECUTE FUNCTION update_dealer_stats();

-- ============================================================================
-- VIEWS
-- ============================================================================

-- Active hot deals view
CREATE VIEW hot_deals AS
SELECT 
    l.*,
    li.image_url as primary_image,
    dp.reliability_score as dealer_score
FROM listings l
LEFT JOIN listing_images li ON l.id = li.listing_id AND li.is_primary = true
LEFT JOIN dealer_profiles dp ON l.sender_phone = dp.sender_phone
WHERE l.status = 'active' 
  AND l.deal_score >= 200
  AND l.sentiment = 'WTS'
ORDER BY l.deal_score DESC, l.created_at DESC;

-- User transaction summary view
CREATE VIEW user_transaction_summary AS
SELECT 
    user_id,
    SUM(CASE WHEN buyer_id = user_id THEN 1 ELSE 0 END) as total_purchases,
    SUM(CASE WHEN seller_id = user_id THEN 1 ELSE 0 END) as total_sales,
    SUM(CASE WHEN buyer_id = user_id THEN amount_usd ELSE 0 END) as total_spent_usd,
    SUM(CASE WHEN seller_id = user_id THEN seller_payout_usd ELSE 0 END) as total_earned_usd
FROM (
    SELECT buyer_id as user_id, amount_usd, 0 as seller_payout_usd, buyer_id, seller_id FROM transactions WHERE status = 'completed'
    UNION ALL
    SELECT seller_id as user_id, 0 as amount_usd, seller_payout_usd, buyer_id, seller_id FROM transactions WHERE status = 'completed'
) t
GROUP BY user_id;

-- ============================================================================
-- SAMPLE DATA (for development)
-- ============================================================================

-- Insert sample reference prices for testing
-- (In production, this would be populated from actual market data)

COMMENT ON TABLE listings IS 'Watch listings parsed from WhatsApp messages';
COMMENT ON TABLE listing_images IS 'Images associated with watch listings';
COMMENT ON TABLE whatsapp_connections IS 'Linked WhatsApp phone numbers for monitoring';
COMMENT ON TABLE watched_groups IS 'WhatsApp groups being monitored for listings';
COMMENT ON TABLE transactions IS 'Escrow transactions between buyers and sellers';
COMMENT ON TABLE dealer_profiles IS 'Reputation and statistics for watch dealers';
COMMENT ON TABLE price_history IS 'Time-series price data for watch references';
COMMENT ON TABLE saved_searches IS 'User-saved search filters with alert notifications';
COMMENT ON TABLE conversations IS 'Direct message conversations between users';
COMMENT ON TABLE messages IS 'Messages within conversations';

-- ============================================================================
-- FOREIGN KEY CONSTRAINTS (added after all tables created)
-- ============================================================================

-- Add FK constraints that had forward references
ALTER TABLE listings 
    ADD CONSTRAINT fk_listings_whatsapp_group 
    FOREIGN KEY (whatsapp_group_id) REFERENCES watched_groups(id) ON DELETE SET NULL;

-- Note: teams table FK will need to be added if teams table is created from auth system
-- ALTER TABLE whatsapp_connections 
--     ADD CONSTRAINT fk_whatsapp_connections_team 
--     FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE;
