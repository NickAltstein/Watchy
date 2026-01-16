import os
import json
import asyncio
import aiosqlite
import logging
import re
import hashlib
import threading
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response, status, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings
from openai import AsyncOpenAI
from thefuzz import process, fuzz
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# --- Custom Module Import ---
from ref_manager import init_ref_table, update_target_price_in_db, get_all_targets_from_db
from notifications import send_deal_notification
from deal_scorer import (
    DealScorer,
    DealFactors,
    DealTier as ScorerDealTier,
    RiskLevel,
    ConditionGrade,
    SellerType,
    MarketTrend,
    score_watch_deal,
)
from price_history import (
    PriceHistoryAnalyzer,
    PricePoint,
    ConditionCategory,
    MAX_REFERENCES_COMPARISON,
)

# --- Custom Exceptions ---
class WatchEngineError(Exception):
    """Base exception for watch engine"""
    pass

class OverpricedError(WatchEngineError):
    """When price is too high"""
    pass

class DuplicateError(WatchEngineError):
    """Duplicate listing"""
    pass

class AIProcessingError(WatchEngineError):
    """AI processing failed"""
    pass

# --- CONFIGURATION ---
class Settings(BaseSettings):
    OPENAI_API_KEY: str
    DEEPSEEK_API_KEY: str
    ADMIN_SECRET: str  # No default - must be provided via env var
    DATABASE_URL: str = "trade_desk.db"
    DEBUG: bool = False
    
    # Security Constraints
    MAX_TEXT_LENGTH: int = 2000
    MAX_IMAGE_SIZE_BYTES: int = int(5 * 1024 * 1024 * 1.37)  # 5MB base64 encoded
    
    # Performance & Logic
    AI_TIMEOUT: float = 18.0
    DEDUPE_HOURS: int = 4
    SCORE_MULTIPLIER: int = 1000
    DRIFT_MIN_PERCENT: float = 2.0
    REFRESH_CACHE_INTERVAL: int = 600  # 10 minutes
    
    # Alert Thresholds
    URGENT_ALERT_MIN: int = 350
    PUSH_ALERT_MIN: int = 200
    
    # Database Connection Pool
    DB_POOL_MINSIZE: int = 1
    DB_POOL_MAXSIZE: int = 10
    
    # CORS - IMPORTANT: Configure specific origins in production!
    # Default uses wildcard for development - MUST change for production
    CORS_ORIGINS: List[str] = ["*"]  # Change to specific domains in production
    
    # Rate Limits
    PARSE_RATE_LIMIT: str = "20/minute"
    METRICS_RATE_LIMIT: str = "10/minute"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    @validator('ADMIN_SECRET')
    def validate_admin_secret(cls, v):
        if len(v) < 16:
            raise ValueError('Admin secret must be at least 16 characters')
        return v
    
    @validator('DATABASE_URL')
    def validate_db_url(cls, v):
        # Handle SQLite URL format
        if v.startswith('sqlite:///'):
            return v.replace('sqlite:///', '')
        return v

settings = Settings()

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("engine.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("watch-engine")

# --- DATABASE CONNECTION POOL ---
class DatabaseManager:
    """Manages database connections with pooling"""
    _instance = None
    _pool = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def init(self, db_path: str):
        """Initialize the connection pool"""
        if self._pool is None:
            self._pool = await aiosqlite.create_pool(
                db_path,
                minsize=settings.DB_POOL_MINSIZE,
                maxsize=settings.DB_POOL_MAXSIZE,
                # Enable WAL mode for better concurrency
                setup=lambda conn: conn.execute("PRAGMA journal_mode=WAL")
            )
            logger.info(f"Database pool initialized for {db_path}")
    
    async def acquire(self):
        """Get a connection from the pool"""
        if self._pool is None:
            raise RuntimeError("Database pool not initialized")
        return await self._pool.acquire()
    
    async def close(self):
        """Close the pool"""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("Database pool closed")

db_manager = DatabaseManager()

# --- Thread-safe cache with optimized reads ---
class AtomicCache:
    """Thread-safe cache with atomic updates and lock-free reads"""
    def __init__(self):
        self._cache: Dict[str, int] = {}
        self._lock = threading.Lock()  # Use threading.Lock for sync code
    
    def update(self, new_cache: Dict[str, int]):
        """Atomically update the entire cache (sync for background thread)"""
        with self._lock:
            self._cache = new_cache.copy()
    
    def get(self, key: str) -> Optional[int]:
        """Lock-free read (Python dict reads are atomic for single operations)"""
        # In CPython, dict reads are thread-safe for single operations
        # We copy the reference to avoid issues during concurrent updates
        cache = self._cache
        return cache.get(key)
    
    def get_all(self) -> Dict[str, int]:
        """Get a copy of the cache (safe for iteration)"""
        with self._lock:
            return self._cache.copy()
    
    def size(self) -> int:
        """Get cache size"""
        return len(self._cache)

TARGET_PRICES_CACHE = AtomicCache()

# --- LIFESPAN MANAGEMENT ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database
    db_path = ":memory:" if settings.DEBUG else settings.DATABASE_URL
    await init_ref_table(db_path)
    
    # Initialize connection pool
    await db_manager.init(db_path)
    
    # Create tables and indexes
    async with (await db_manager.acquire()) as conn:
        await conn.execute("""CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unique_hash TEXT UNIQUE,
            brand TEXT, model TEXT, ref_number TEXT,
            price_usd INTEGER, deal_score INTEGER, alert_tier TEXT,
            sentiment TEXT, group_name TEXT, sender_id TEXT,
            raw_text TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_dedupe ON trades (ref_number, price_usd, sender_id, timestamp)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_hash ON trades (unique_hash)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_ref_score ON trades (ref_number, deal_score)")
        await conn.commit()
    
    # Initial cache load
    initial_cache = await get_all_targets_from_db(db_path)
    TARGET_PRICES_CACHE.update(initial_cache)
    
    # Set start time for uptime tracking
    app.state.start_time = datetime.now()
    
    # Start background cache refresh
    app.state.cache_refresh_task = asyncio.create_task(
        background_cache_refresher(db_path)
    )
    
    logger.info(f"🚀 Watch Trading Engine v10.2 Online with connection pooling.")
    yield
    
    # Cleanup
    app.state.cache_refresh_task.cancel()
    await db_manager.close()

async def background_cache_refresher(db_path: str):
    """Background task to refresh cache periodically"""
    while True:
        try:
            await asyncio.sleep(settings.REFRESH_CACHE_INTERVAL)
            new_cache = await get_all_targets_from_db(db_path)
            TARGET_PRICES_CACHE.update(new_cache)
            logger.info(f"🔄 Cache Refreshed: {len(new_cache)} references.")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Cache Refresher Error: {e}")
            await asyncio.sleep(30)  # Backoff on error

# --- APP SETUP ---
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(
    title="Watch Trading Engine v10.2",
    description="Luxury Watch Deal Detection System",
    version="10.2.0",
    lifespan=lifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# AI Clients
openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
deepseek_client = AsyncOpenAI(
    api_key=settings.DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

# Patterns
IGNORE_PATTERN = re.compile(r'^(bump|ttt|up|available|pm sent|sold)\W*$', re.IGNORECASE)

# --- MODELS ---
class WatchMessage(BaseModel):
    text: str = Field("", max_length=settings.MAX_TEXT_LENGTH)
    imageBase64: Optional[str] = None
    groupName: str
    senderId: str
    messageId: str
    
    @validator('imageBase64')
    def validate_image_size(cls, v):
        if v and len(v) > settings.MAX_IMAGE_SIZE_BYTES:
            raise ValueError(f"Image exceeds maximum size of {settings.MAX_IMAGE_SIZE_BYTES} bytes")
        return v

class ParsedWatch(BaseModel):
    brand: Optional[str] = None
    model: Optional[str] = None
    ref_number: Optional[str] = None
    price_usd: int = Field(..., ge=1000)
    sentiment: str = "WTS"

class TargetUpdatePayload(BaseModel):
    ref_number: str
    market_price: int = Field(..., ge=1000)
    admin_secret: str

class HealthResponse(BaseModel):
    status: str
    database: str
    cache_size: int
    uptime: float
    timestamp: str


# --- ADVANCED SCORING MODELS ---
class ScoreDealRequest(BaseModel):
    """Request model for advanced deal scoring"""
    ref_number: str = Field(..., description="Reference number")
    listing_price: int = Field(..., gt=0, description="Listing price in USD")
    
    # Optional condition factors
    condition: Optional[str] = Field(default="UNKNOWN", description="NIB, UNWORN, EXCELLENT, GOOD, FAIR, POOR, UNKNOWN")
    has_box: bool = Field(default=False)
    has_papers: bool = Field(default=False)
    has_warranty: bool = Field(default=False)
    is_full_set: bool = Field(default=False)
    
    # Optional seller factors
    seller_type: Optional[str] = Field(default="UNKNOWN", description="VERIFIED_DEALER, ESTABLISHED_DEALER, PRIVATE_TRUSTED, PRIVATE_NEW, UNKNOWN")
    seller_rating: Optional[float] = Field(default=None, ge=0, le=5)
    seller_transaction_count: int = Field(default=0, ge=0)
    
    # Optional urgency signals
    quick_sale: bool = Field(default=False)
    price_reduced: bool = Field(default=False)
    motivated_seller: bool = Field(default=False)
    
    # Optional market context
    market_trend: Optional[str] = Field(default="UNKNOWN", description="RISING, STABLE, FALLING, UNKNOWN")
    comparable_count: int = Field(default=0, ge=0)
    rarity_score: int = Field(default=0, ge=0, le=30)
    
    # Optional risk factors
    vague_photos: bool = Field(default=False)
    new_seller_suspicious: bool = Field(default=False)
    payment_red_flags: bool = Field(default=False)
    contradictory_info: bool = Field(default=False)
    
    # Optional arbitrage calculation
    calculate_arbitrage: Optional[Dict[str, int]] = Field(default=None, description="Dict of platform: sell_price for arbitrage calc")


class ScoreDealResponse(BaseModel):
    """Response model for advanced deal scoring"""
    status: str
    ref_number: str
    listing_price: int
    market_price: int
    
    # Score details
    score: int
    tier: str
    discount_percentage: float
    confidence: int
    
    # Breakdown
    breakdown: Dict[str, int]
    
    # Explanation
    explanation: str
    
    # Risk assessment
    risk_level: str
    risk_score: int
    red_flags: List[str]
    concerns: List[str]
    recommendations: List[str]
    
    # Optional arbitrage
    arbitrage: Optional[Dict[str, Any]] = None
    
    timestamp: str


class PriceHistoryResponse(BaseModel):
    """Response model for price history endpoint"""
    status: str
    ref_number: str
    days: int
    data_points: List[Dict[str, Any]]
    trend_analysis: Dict[str, Any]
    bollinger_bands: Optional[Dict[str, List[float]]] = None
    predictions: Optional[List[Dict[str, Any]]] = None
    timestamp: str


class CompareReferencesResponse(BaseModel):
    """Response model for comparing multiple references"""
    status: str
    references: List[str]
    comparison_data: Dict[str, Dict[str, Any]]
    timestamp: str


# Initialize deal scorer and price history analyzer
deal_scorer = DealScorer()
price_analyzer = PriceHistoryAnalyzer()

# --- UTILS ---
async def get_clean_ref(raw: Optional[str]) -> Optional[str]:
    """Extract and clean reference number (ASYNC FIX)"""
    if not raw:
        return None
    
    # Get current cache snapshot - FIXED: No more asyncio.run()!
    cache = TARGET_PRICES_CACHE.get_all()
    if not cache:
        return None
    
    clean = raw.strip().upper().replace(" ", "")
    match, score = process.extractOne(
        clean,
        list(cache.keys()),
        scorer=fuzz.token_set_ratio
    )
    return match if score > 85 else None

def normalize_sentiment(s: str | None) -> str:
    """Normalize sentiment to WTS or WTB"""
    if not s:
        return "WTS"
    
    s_upper = s.upper()
    
    # Explicit sell indicators take precedence
    if "WTS" in s_upper:
        return "WTS"
    
    # Check for sell context
    if "SELL" in s_upper and "BUY" not in s_upper:
        return "WTS"
    
    # Buy indicators
    buy_keywords = ["WTB", "BUY", "LOOKING", "WANT", "LF", "SEARCHING"]
    if any(kw in s_upper for kw in buy_keywords):
        return "WTB"
    
    # Default to sell
    return "WTS"

async def get_db_connection():
    """Dependency for database connections - WITH PROPER CONTEXT MANAGEMENT"""
    async with (await db_manager.acquire()) as conn:
        yield conn

# --- ENDPOINTS ---
@app.exception_handler(WatchEngineError)
async def watch_engine_exception_handler(request: Request, exc: WatchEngineError):
    """Global exception handler for watch engine errors"""
    logger.error(f"WatchEngineError: {exc}")
    return JSONResponse(
        status_code=400,
        content={
            "status": "error",
            "code": exc.__class__.__name__,
            "detail": str(exc)
        }
    )

@app.post("/admin/update-target", tags=["admin"])
async def update_target(payload: TargetUpdatePayload):
    """Update target price for a reference number (admin only)"""
    # Use constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(payload.admin_secret, settings.ADMIN_SECRET):
        raise HTTPException(
            status_code=403,
            detail="Invalid admin secret"
        )
    
    await update_target_price_in_db(
        settings.DATABASE_URL,
        payload.ref_number.upper(),
        payload.market_price
    )
    
    # Refresh cache
    new_cache = await get_all_targets_from_db(settings.DATABASE_URL)
    TARGET_PRICES_CACHE.update(new_cache)
    
    logger.info(f"Target price updated: {payload.ref_number} = {payload.market_price}")
    
    return {
        "status": "success",
        "ref": payload.ref_number,
        "price": payload.market_price,
        "cache_size": len(new_cache)
    }

@app.post("/parse-watch", tags=["processing"])
@limiter.limit(settings.PARSE_RATE_LIMIT)
async def parse_watch(
    msg: WatchMessage,
    request: Request
):
    """Parse watch listing from text/image"""
    # Quick noise filter
    if msg.text and IGNORE_PATTERN.fullmatch(msg.text.strip().lower()):
        return {"status": "ignore", "code": "PURE_NOISE"}
    
    # Generate unique hash for deduplication
    unique_hash = hashlib.sha256(
        f"{msg.groupName}:{msg.messageId}".encode()
    ).hexdigest()
    
    # Process with proper connection context management
    async with (await db_manager.acquire()) as conn:
        # Check for duplicate hash
        async with conn.execute(
            "SELECT 1 FROM trades WHERE unique_hash = ?",
            (unique_hash,)
        ) as cursor:
            if await cursor.fetchone():
                raise DuplicateError("Message already processed")
        
        # Determine AI model to use
        is_vision = bool(msg.imageBase64)
        client = openai_client if is_vision else deepseek_client
        model = "gpt-4o-mini-vision" if is_vision else "deepseek-chat"
        
        # Prepare content for AI
        system_prompt = """Return ONLY valid JSON with keys:
brand, model, ref_number, price_usd, sentiment.
If not a watch sale listing, return {"status":"ignore"}.
Do not add commentary."""
        
        if is_vision:
            content = [
                {"type": "text", "text": system_prompt},
                {"type": "text", "text": f"Context: {msg.text}"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{msg.imageBase64}"}}
            ]
        else:
            content = msg.text
        
        # AI Processing
        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": content}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1  # Lower temperature for more consistent outputs
                ),
                timeout=settings.AI_TIMEOUT
            )
            data = json.loads(response.choices[0].message.content or "{}")
        except asyncio.TimeoutError:
            raise AIProcessingError("AI processing timeout")
        except Exception as e:
            logger.error(f"AI processing failed: {e}")
            raise AIProcessingError(f"AI processing failed: {str(e)}")
        
        # Check if AI ignored the message
        if data.get("status") == "ignore":
            return {"status": "ignore", "code": "AI_FILTERED"}
        
        # Parse and validate AI output
        try:
            data["sentiment"] = normalize_sentiment(data.get("sentiment"))
            watch = ParsedWatch(**data)
            
            # Clean and match reference number - FIXED: await the async function
            ref = await get_clean_ref(watch.ref_number)
            if not ref:
                return {"status": "ignore", "code": "UNKNOWN_REFERENCE"}
            
            # Get market price from cache
            market_price = TARGET_PRICES_CACHE.get(ref)
            if not market_price:
                return {"status": "ignore", "code": "NO_MARKET_PRICE"}
            
            # Temporal deduplication check
            cutoff = (datetime.now() - timedelta(hours=settings.DEDUPE_HOURS)).strftime('%Y-%m-%d %H:%M:%S')
            async with conn.execute(
                """SELECT id FROM trades 
                   WHERE ref_number = ? AND price_usd = ? AND sender_id = ? 
                   AND timestamp > ?""",
                (ref, watch.price_usd, msg.senderId, cutoff)
            ) as cursor:
                if await cursor.fetchone():
                    raise DuplicateError("Recent duplicate listing detected")
            
            # Check for price drift
            drift_detected = False
            async with conn.execute(
                """SELECT price_usd FROM trades 
                   WHERE ref_number = ? AND sender_id = ? 
                   ORDER BY timestamp DESC LIMIT 1""",
                (ref, msg.senderId)
            ) as cursor:
                last_row = await cursor.fetchone()
                if last_row and last_row[0]:
                    price_drop_pct = ((last_row[0] - watch.price_usd) / last_row[0]) * 100
                    if price_drop_pct >= settings.DRIFT_MIN_PERCENT:
                        drift_detected = True
                        logger.info(f"Price drift detected: {ref} dropped {price_drop_pct:.1f}%")
            
            # Calculate deal score
            score = max(
                -500,
                min(
                    500,
                    int(((market_price - watch.price_usd) / market_price) * settings.SCORE_MULTIPLIER)
                )
            )
            
            # Filter overpriced listings
            if score <= -300:
                raise OverpricedError(f"Price ${watch.price_usd} is significantly above market ${market_price}")
            
            # Determine alert tier
            if score >= settings.URGENT_ALERT_MIN:
                tier = "URGENT"
            elif score >= settings.PUSH_ALERT_MIN:
                tier = "PUSH"
            else:
                tier = "NORMAL"
            
            # Insert into database
            await conn.execute("""INSERT INTO trades 
                (unique_hash, brand, model, ref_number, price_usd, 
                 deal_score, alert_tier, sentiment, group_name, 
                 sender_id, raw_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (unique_hash, watch.brand, watch.model, ref, watch.price_usd,
                 score, tier, watch.sentiment, msg.groupName,
                 msg.senderId, msg.text))
            await conn.commit()
            
            logger.info(f"Processed listing: {ref} ${watch.price_usd} (Score: {score}, Tier: {tier})")
            
            # Send notifications for significant deals
            if tier in ["URGENT", "PUSH"]:
                try:
                    await send_deal_notification(
                        ref_number=ref,
                        price=watch.price_usd,
                        market_price=market_price,
                        deal_score=score,
                        alert_tier=tier,
                        group_name=msg.groupName,
                        sentiment=watch.sentiment,
                        raw_text=msg.text[:500] if msg.text else None
                    )
                except Exception as e:
                    logger.error(f"Failed to send notification: {e}")
            
            return {
                "status": "success",
                "ref": ref,
                "price": watch.price_usd,
                "market_price": market_price,
                "score": score,
                "tier": tier,
                "drift": drift_detected,
                "sentiment": watch.sentiment,
                "hash": unique_hash[:8]  # Return first 8 chars for debugging
            }
            
        except Exception as e:
            logger.error(f"Validation/processing error: {e}")
            raise

@app.post("/score-deal", response_model=ScoreDealResponse, tags=["scoring"])
@limiter.limit(settings.PARSE_RATE_LIMIT)
async def score_deal_endpoint(
    request: Request,
    req: ScoreDealRequest
):
    """
    Advanced deal scoring with multi-factor analysis.
    
    Scores a watch deal based on:
    - Price vs market value
    - Condition and inclusions
    - Seller reputation
    - Urgency signals
    - Market trends
    - Risk factors
    
    Returns comprehensive scoring with explanation, risk assessment, and optional arbitrage.
    """
    try:
        # Get market price from cache
        ref_clean = req.ref_number.upper().replace(" ", "").strip()
        market_price = TARGET_PRICES_CACHE.get(ref_clean)
        
        if not market_price:
            logger.warning(f"No market price found for {ref_clean}")
            raise HTTPException(
                status_code=404,
                detail=f"No market price found for reference {req.ref_number}"
            )
        
        # Build deal factors
        factors = DealFactors(
            market_price=market_price,
            listing_price=req.listing_price,
            condition=ConditionGrade(req.condition.upper()),
            has_box=req.has_box,
            has_papers=req.has_papers,
            has_warranty=req.has_warranty,
            is_full_set=req.is_full_set,
            seller_type=SellerType(req.seller_type.upper() if req.seller_type else "UNKNOWN"),
            seller_rating=req.seller_rating,
            seller_transaction_count=req.seller_transaction_count,
            quick_sale_indicated=req.quick_sale,
            price_reduced=req.price_reduced,
            motivated_seller=req.motivated_seller,
            market_trend=MarketTrend(req.market_trend.upper() if req.market_trend else "UNKNOWN"),
            comparable_count=req.comparable_count,
            rarity_score=req.rarity_score,
            vague_photos=req.vague_photos,
            new_seller_suspicious=req.new_seller_suspicious,
            payment_red_flags=req.payment_red_flags,
            contradictory_info=req.contradictory_info
        )
        
        # Score the deal
        result = deal_scorer.score_deal(factors, calculate_arbitrage_for=req.calculate_arbitrage)
        
        # Build response
        response = ScoreDealResponse(
            status="success",
            ref_number=ref_clean,
            listing_price=req.listing_price,
            market_price=market_price,
            score=result.score,
            tier=result.tier.value,
            discount_percentage=result.breakdown.discount_percentage,
            confidence=result.confidence,
            breakdown={
                "base_score": result.breakdown.base_score,
                "condition_bonus": result.breakdown.condition_bonus,
                "inclusions_bonus": result.breakdown.inclusions_bonus,
                "seller_bonus": result.breakdown.seller_bonus,
                "urgency_bonus": result.breakdown.urgency_bonus,
                "market_trend_adjustment": result.breakdown.market_trend_adjustment,
                "rarity_bonus": result.breakdown.rarity_bonus,
                "risk_penalty": result.breakdown.risk_penalty,
                "final_score": result.breakdown.final_score
            },
            explanation=result.explanation,
            risk_level=result.risk_assessment.level.value,
            risk_score=result.risk_assessment.score,
            red_flags=result.risk_assessment.red_flags,
            concerns=result.risk_assessment.concerns,
            recommendations=result.risk_assessment.recommendations,
            arbitrage=result.arbitrage.model_dump() if result.arbitrage else None,
            timestamp=datetime.now().isoformat()
        )
        
        logger.info(f"Scored deal: {ref_clean} ${req.listing_price} = {result.score} ({result.tier.value})")
        
        return response
        
    except HTTPException:
        # Re-raise HTTPExceptions so FastAPI handles them properly
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error scoring deal: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to score deal: {str(e)}")

@app.get("/price-history/{ref_number}", response_model=PriceHistoryResponse, tags=["analytics"])
@limiter.limit("30/minute")
async def get_price_history(
    request: Request,
    ref_number: str,
    days: int = 90,
    include_predictions: bool = True,
    include_bollinger: bool = True
):
    """
    Get price history and predictions for a watch reference.
    
    Args:
        ref_number: Watch reference (e.g., "126610LN")
        days: Number of days of history to retrieve (default: 90, max: 365)
        include_predictions: Include 30-day price predictions
        include_bollinger: Include Bollinger bands for volatility
    
    Returns:
        Price history data with trend analysis and optional predictions
    """
    try:
        # Validate and limit days
        days = min(max(1, days), 365)
        
        # Clean reference number
        ref_clean = ref_number.upper().replace(" ", "").strip()
        
        # Get historical data from database
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        
        async with (await db_manager.acquire()) as conn:
            async with conn.execute(
                """SELECT id, price_usd, deal_score, sentiment, timestamp, brand, model
                   FROM trades 
                   WHERE ref_number = ? AND timestamp > ?
                   ORDER BY timestamp ASC""",
                (ref_clean, cutoff_date)
            ) as cursor:
                rows = await cursor.fetchall()
        
        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"No price history found for reference {ref_number}"
            )
        
        # Convert to PricePoint objects
        price_points = []
        for row in rows:
            # Determine condition category from brand/model or default to UNKNOWN
            condition = "UNKNOWN"  # We don't store condition in trades table yet
            
            price_points.append(PricePoint(
                timestamp=row[4],
                price=row[1],
                deal_score=row[2],
                condition=condition,
                seller_type="UNKNOWN",  # Not stored yet
                has_box=False,  # Not stored yet
                has_papers=False,  # Not stored yet
                sentiment=row[3],
                trade_id=row[0]
            ))
        
        # Analyze trend
        trend_analysis = price_analyzer.analyze_history(price_points)
        
        # Calculate Bollinger bands if requested
        bollinger_bands = None
        if include_bollinger and len(price_points) >= 20:
            prices = [p.price for p in price_points]
            middle, upper, lower = price_analyzer.calculate_bollinger_bands(prices)
            bollinger_bands = {
                "middle": [round(v, 2) for v in middle],
                "upper": [round(v, 2) for v in upper],
                "lower": [round(v, 2) for v in lower]
            }
        
        # Generate predictions if requested
        predictions = None
        if include_predictions and len(price_points) >= 3:
            prices = [p.price for p in price_points]
            # Parse timestamps safely
            timestamps = []
            for p in price_points:
                ts_str = p.timestamp
                if ts_str.endswith('Z'):
                    ts_str = ts_str[:-1] + '+00:00'
                try:
                    timestamps.append(datetime.fromisoformat(ts_str))
                except ValueError:
                    timestamps.append(datetime.fromisoformat(ts_str.split('+')[0].split('Z')[0]))
            
            pred_list = price_analyzer.predict_prices(prices, timestamps, days_ahead=30)
            predictions = [p.to_dict() for p in pred_list]
        
        # Build response
        response = PriceHistoryResponse(
            status="success",
            ref_number=ref_clean,
            days=days,
            data_points=[p.to_dict() for p in price_points],
            trend_analysis=trend_analysis.to_dict(),
            bollinger_bands=bollinger_bands,
            predictions=predictions,
            timestamp=datetime.now().isoformat()
        )
        
        logger.info(f"Price history retrieved: {ref_clean}, {len(price_points)} points")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting price history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get price history: {str(e)}")

@app.get("/compare-references", response_model=CompareReferencesResponse, tags=["analytics"])
@limiter.limit("20/minute")
async def compare_references(
    request: Request,
    refs: str,  # Comma-separated list of references
    days: int = 90
):
    """
    Compare price history for multiple watch references.
    
    Args:
        refs: Comma-separated list of references (e.g., "126610LN,116500LN")
        days: Number of days of history to retrieve (default: 90, max: 365)
    
    Returns:
        Comparison data for multiple references
    """
    try:
        # Parse and validate references
        ref_list = [r.strip().upper().replace(" ", "") for r in refs.split(",")]
        ref_list = [r for r in ref_list if r]  # Remove empty strings
        
        if not ref_list:
            raise HTTPException(status_code=400, detail="No valid references provided")
        
        if len(ref_list) > MAX_REFERENCES_COMPARISON:
            raise HTTPException(
                status_code=400, 
                detail=f"Maximum {MAX_REFERENCES_COMPARISON} references can be compared"
            )
        
        # Validate and limit days
        days = min(max(1, days), 365)
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        
        # Fetch data for each reference
        comparison_data = {}
        
        async with (await db_manager.acquire()) as conn:
            for ref in ref_list:
                async with conn.execute(
                    """SELECT id, price_usd, deal_score, sentiment, timestamp
                       FROM trades 
                       WHERE ref_number = ? AND timestamp > ?
                       ORDER BY timestamp ASC""",
                    (ref, cutoff_date)
                ) as cursor:
                    rows = await cursor.fetchall()
                
                if rows:
                    price_points = []
                    for row in rows:
                        price_points.append({
                            "trade_id": row[0],
                            "price": row[1],
                            "deal_score": row[2],
                            "sentiment": row[3],
                            "timestamp": row[4]
                        })
                    
                    # Calculate basic stats
                    prices = [p["price"] for p in price_points]
                    
                    comparison_data[ref] = {
                        "data_points": price_points,
                        "count": len(price_points),
                        "avg_price": round(sum(prices) / len(prices), 2) if prices else 0,
                        "min_price": min(prices) if prices else 0,
                        "max_price": max(prices) if prices else 0,
                        "current_price": prices[-1] if prices else 0
                    }
        
        if not comparison_data:
            raise HTTPException(
                status_code=404,
                detail="No price history found for any of the provided references"
            )
        
        response = CompareReferencesResponse(
            status="success",
            references=list(comparison_data.keys()),
            comparison_data=comparison_data,
            timestamp=datetime.now().isoformat()
        )
        
        logger.info(f"Comparison retrieved for {len(comparison_data)} references")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing references: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to compare references: {str(e)}")

@app.get("/health", response_model=HealthResponse, tags=["monitoring"])
async def health():
    """Health check endpoint"""
    # Check database connectivity
    try:
        async with (await db_manager.acquire()) as conn:
            await conn.execute("SELECT 1")
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    # Get cache size
    cache_size = TARGET_PRICES_CACHE.size()
    
    # Get uptime from app state (fixed: now set in lifespan)
    uptime = (datetime.now() - app.state.start_time).total_seconds()
    
    return {
        "status": "online",
        "database": db_status,
        "cache_size": cache_size,
        "uptime": uptime,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/metrics", tags=["monitoring"])
@limiter.limit(settings.METRICS_RATE_LIMIT)  # Added rate limiting
async def metrics(request: Request, admin_secret: Optional[str] = None):
    """Metrics endpoint with optional authentication"""
    # Optional authentication for sensitive metrics - use constant-time comparison
    if not admin_secret or not secrets.compare_digest(admin_secret, settings.ADMIN_SECRET):
        # Return basic metrics only for unauthenticated requests
        return {
            "status": "basic_metrics_only",
            "cache_size": TARGET_PRICES_CACHE.size(),
            "timestamp": datetime.now().isoformat(),
            "message": "Provide admin_secret for detailed metrics"
        }
    
    # Detailed metrics for authenticated requests
    async with (await db_manager.acquire()) as conn:
        # Get counts by tier for last 24 hours
        async with conn.execute("""
            SELECT alert_tier, COUNT(*) as count 
            FROM trades 
            WHERE timestamp > datetime('now', '-1 day')
            GROUP BY alert_tier
        """) as cursor:
            daily_counts = await cursor.fetchall()
        
        # Get top references
        async with conn.execute("""
            SELECT ref_number, COUNT(*) as count 
            FROM trades 
            GROUP BY ref_number 
            ORDER BY count DESC 
            LIMIT 10
        """) as cursor:
            top_refs = await cursor.fetchall()
        
        # Get recent activity stats
        async with conn.execute("""
            SELECT 
                strftime('%H', timestamp) as hour,
                COUNT(*) as listings,
                AVG(deal_score) as avg_score
            FROM trades 
            WHERE timestamp > datetime('now', '-24 hours')
            GROUP BY strftime('%H', timestamp)
            ORDER BY hour
        """) as cursor:
            hourly_stats = await cursor.fetchall()
    
    return {
        "detailed_metrics": True,
        "daily_activity": dict(daily_counts),
        "top_references": dict(top_refs),
        "hourly_stats": dict(hourly_stats),
        "cache_size": TARGET_PRICES_CACHE.size(),
        "database": settings.DATABASE_URL,
        "uptime": (datetime.now() - app.state.start_time).total_seconds(),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/recent-trades", tags=["analytics"])
async def get_recent_trades(limit: int = 50, offset: int = 0):
    """Get recent trade listings for dashboard"""
    async with (await db_manager.acquire()) as conn:
        async with conn.execute("""
            SELECT 
                id, brand, model, ref_number, price_usd,
                deal_score, alert_tier, sentiment, group_name,
                sender_id, timestamp,
                CASE WHEN timestamp > datetime('now', '-5 minutes') THEN 1 ELSE 0 END as drift
            FROM trades
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """, (limit, offset)) as cursor:
            rows = await cursor.fetchall()
            
            trades = [
                {
                    "id": row[0],
                    "brand": row[1],
                    "model": row[2],
                    "ref_number": row[3],
                    "price_usd": row[4],
                    "deal_score": row[5],
                    "alert_tier": row[6],
                    "sentiment": row[7],
                    "group_name": row[8],
                    "sender_id": row[9][:16] + "...",  # Truncate for privacy
                    "timestamp": row[10],
                    "drift": bool(row[11])
                }
                for row in rows
            ]
    
    return trades

@app.get("/stats/ref/{ref_number}", tags=["analytics"])
async def get_ref_stats(ref_number: str, days: int = 7):
    """Get statistics for a specific reference number"""
    async with (await db_manager.acquire()) as conn:
        # Get price distribution
        async with conn.execute("""
            SELECT 
                MIN(price_usd) as min_price,
                MAX(price_usd) as max_price,
                AVG(price_usd) as avg_price,
                COUNT(*) as total_listings,
                AVG(deal_score) as avg_score
            FROM trades 
            WHERE ref_number = ? AND timestamp > datetime('now', ?)
        """, (ref_number.upper(), f"-{days} days")) as cursor:
            stats = await cursor.fetchone()
        
        # Get recent listings
        async with conn.execute("""
            SELECT price_usd, deal_score, alert_tier, sentiment, timestamp
            FROM trades 
            WHERE ref_number = ?
            ORDER BY timestamp DESC
            LIMIT 20
        """, (ref_number.upper(),)) as cursor:
            recent = await cursor.fetchall()
    
    if not stats or not stats[0]:
        raise HTTPException(status_code=404, detail="No data found for this reference")
    
    return {
        "ref_number": ref_number.upper(),
        "market_price": TARGET_PRICES_CACHE.get(ref_number.upper()),
        "stats": {
            "min_price": stats[0],
            "max_price": stats[1],
            "avg_price": round(stats[2], 2) if stats[2] else None,
            "total_listings": stats[3],
            "avg_score": round(stats[4], 2) if stats[4] else None
        },
        "recent_listings": recent
    }

@app.get("/export/trades", tags=["export"])
@limiter.limit("5/minute")
async def export_trades(
    request: Request,
    format: str = "json",
    days: int = 7,
    admin_secret: Optional[str] = None
):
    """Export trade data in various formats (requires authentication)"""
    # Use constant-time comparison to prevent timing attacks
    if not admin_secret or not secrets.compare_digest(admin_secret, settings.ADMIN_SECRET):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    
    async with (await db_manager.acquire()) as conn:
        async with conn.execute("""
            SELECT 
                id, brand, model, ref_number, price_usd,
                deal_score, alert_tier, sentiment, group_name,
                timestamp, raw_text
            FROM trades
            WHERE timestamp > datetime('now', ?)
            ORDER BY timestamp DESC
        """, (f"-{days} days",)) as cursor:
            rows = await cursor.fetchall()
    
    if format == "json":
        trades = [
            {
                "id": row[0],
                "brand": row[1],
                "model": row[2],
                "ref_number": row[3],
                "price_usd": row[4],
                "deal_score": row[5],
                "alert_tier": row[6],
                "sentiment": row[7],
                "group_name": row[8],
                "timestamp": row[9],
                "raw_text": row[10]
            }
            for row in rows
        ]
        return JSONResponse(content={"trades": trades, "count": len(trades)})
    
    elif format == "csv":
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            "ID", "Brand", "Model", "Reference", "Price USD",
            "Deal Score", "Alert Tier", "Sentiment", "Group",
            "Timestamp", "Raw Text"
        ])
        
        # Write data
        for row in rows:
            writer.writerow(row)
        
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=trades_export_{datetime.now().strftime('%Y%m%d')}.csv"
            }
        )
    
    else:
        raise HTTPException(status_code=400, detail="Invalid format. Use 'json' or 'csv'")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info" if settings.DEBUG else "warning"
    )
