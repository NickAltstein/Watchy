# WhatsApp Luxury Watch Scraper System

Production-ready system for automatically scraping, parsing, and analyzing luxury watch listings from WhatsApp groups using Baileys and OpenAI GPT-4o Vision.

## System Architecture

```
WhatsApp Groups
       ↓
┌──────────────────┐
│  Node.js Server  │  ← Baileys WebSocket connection
│   (server.js)    │  ← Downloads images, extracts text
└────────┬─────────┘
         │ HTTP POST
         ↓
┌──────────────────┐
│  Python FastAPI  │  ← OpenAI GPT-4o Vision
│    (main.py)     │  ← Deduplication logic
│                  │  ← SQLite storage
└──────────────────┘
```

## Features

✅ **Real-time WhatsApp monitoring** with Baileys (native protocol, not browser automation)  
✅ **AI Vision analysis** using GPT-4o for text + images  
✅ **Automatic deduplication** - ignores duplicate listings within 4 hours  
✅ **Deal scoring** - compares prices against reference targets  
✅ **Advanced multi-factor scoring engine** - comprehensive analysis with risk assessment  
✅ **Arbitrage detection** - identify cross-platform profit opportunities  
✅ **SQLite storage** - saves all WTS listings  
✅ **Multi-group support** - filter specific groups or monitor all  
✅ **Robust reconnection** - handles WhatsApp disconnections automatically  
✅ **Watch terminology expert** - understands NIB, B+P, stickered, etc.

## Advanced Deal Scoring Engine

The system includes a sophisticated scoring engine that analyzes deals across multiple dimensions:

### Scoring Formula

```
Base Score = ((market_price - listing_price) / market_price) * 1000

Adjustments:
+ Condition bonus (0-20 points for NIB, unworn, excellent, etc.)
+ Inclusions bonus (0-15 points for full set, box, papers)
+ Seller reputation (0-10 points for verified dealers, high ratings)
+ Urgency signals (0-5 points for quick sales, price reductions)
+ Market trend (±20 points for rising/falling markets)
+ Rarity factor (0-30 points for hard-to-find pieces)
- Risk penalty (0-50 points for red flags)

Final Score = clamp(Base Score + Adjustments, -500, 500)
```

### Deal Tier Classification

- **URGENT (350+)**: Exceptional deal, act immediately
- **PUSH (200-349)**: Good deal, worth pursuing
- **NORMAL (100-199)**: Fair deal, acceptable
- **SKIP (0-99)**: Near market price, not compelling
- **OVERPRICED (<0)**: Above market, avoid

### Risk Assessment

The engine automatically detects red flags:
- Price too good to be true (>40% below market)
- New seller with no transaction history
- Suspicious payment methods (wire only, crypto)
- Vague or stock photos
- Contradictory information

Risk levels: **LOW**, **MEDIUM**, **HIGH**, **CRITICAL**

### Arbitrage Detection

Calculate profit potential across platforms:
- Compare prices on WhatsApp, Chrono24, eBay, etc.
- Account for platform fees (Chrono24: 6.5%, eBay: 12.9%)
- Include PayPal fees, shipping, and insurance
- Calculate net profit and ROI percentage

### Scoring API Endpoint

**POST /score-deal**

Score any watch deal with comprehensive analysis:

```bash
curl -X POST http://localhost:8000/score-deal \
  -H "Content-Type: application/json" \
  -d '{
    "ref_number": "126610LN",
    "listing_price": 16800,
    "condition": "NIB",
    "has_box": true,
    "has_papers": true,
    "is_full_set": true,
    "seller_type": "VERIFIED_DEALER",
    "seller_rating": 4.8,
    "market_trend": "STABLE",
    "comparable_count": 47
  }'
```

**Response:**

```json
{
  "status": "success",
  "ref_number": "126610LN",
  "listing_price": 16800,
  "market_price": 21500,
  "score": 265,
  "tier": "PUSH",
  "discount_percentage": 21.86,
  "confidence": 94,
  "breakdown": {
    "base_score": 218,
    "condition_bonus": 20,
    "inclusions_bonus": 15,
    "seller_bonus": 10,
    "urgency_bonus": 0,
    "market_trend_adjustment": 0,
    "rarity_bonus": 0,
    "risk_penalty": 0,
    "final_score": 265
  },
  "explanation": "PUSH DEAL: 21.9% below market ($16,800 vs $21,500 market). NIB condition (+20), full set (+15), verified dealer (+10). Market stable. High confidence (47 recent comps).",
  "risk_level": "LOW",
  "risk_score": 0,
  "red_flags": [],
  "concerns": [],
  "recommendations": ["Verified dealer - transaction should be safe"],
  "timestamp": "2024-01-16T03:00:00"
}
```

**Parameters:**

Required:
- `ref_number`: Watch reference (e.g., "126610LN")
- `listing_price`: Asking price in USD

Optional condition factors:
- `condition`: NIB, UNWORN, EXCELLENT, GOOD, FAIR, POOR, UNKNOWN
- `has_box`, `has_papers`, `has_warranty`, `is_full_set`: boolean

Optional seller factors:
- `seller_type`: VERIFIED_DEALER, ESTABLISHED_DEALER, PRIVATE_TRUSTED, PRIVATE_NEW, UNKNOWN
- `seller_rating`: 0-5.0 rating
- `seller_transaction_count`: number of transactions

Optional signals:
- `quick_sale`, `price_reduced`, `motivated_seller`: boolean urgency flags
- `market_trend`: RISING, STABLE, FALLING, UNKNOWN
- `comparable_count`: number of recent comparable sales
- `rarity_score`: 0-30 for hard-to-find pieces

Optional risk factors:
- `vague_photos`, `new_seller_suspicious`, `payment_red_flags`, `contradictory_info`: boolean

Optional arbitrage:
- `calculate_arbitrage`: Dict of platform: price for arbitrage calculation

### Example Scenarios

**Urgent Deal (35% off, rare piece):**
```json
{
  "ref_number": "5711/1A-010",
  "listing_price": 70000,
  "market_price": 108000,
  "score": 420,
  "tier": "URGENT",
  "explanation": "URGENT DEAL: 35% below market. Rising market makes this exceptional. Act fast!"
}
```

**High Risk (too cheap, suspicious seller):**
```json
{
  "ref_number": "126610LN", 
  "listing_price": 10000,
  "market_price": 21500,
  "score": 300,
  "tier": "PUSH",
  "risk_level": "CRITICAL",
  "red_flags": ["Price is 53% below market - too good to be true", "Brand new seller with no transaction history"],
  "recommendations": ["DO NOT PROCEED - High probability of fraud"]
}
```


## Installation

### Prerequisites

- Node.js 18+ 
- Python 3.10+
- OpenAI API key with GPT-4o access

### Step 1: Install Node.js Dependencies

```bash
npm install
```

### Step 2: Install Python Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Configure Environment

```bash
cp .env.template .env
```

Edit `.env` and set:
- `OPENAI_API_KEY` - Your OpenAI API key
- `WATCHED_GROUPS` - Comma-separated list of group names (optional, leave empty to monitor all)

### Step 4: Customize Target Prices

Edit `target_prices.json` to add your reference prices for deal scoring. Format:

```json
{
  "126610LN": 12500,
  "5711/1A-010": 85000
}
```

## Usage

### Start the Python API (Terminal 1)

```bash
uvicorn main:app --reload
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
✅ Database initialized
```

### Start the WhatsApp Listener (Terminal 2)

```bash
npm start
```

**First time setup:**
1. A QR code will appear in your terminal
2. Open WhatsApp on your phone
3. Go to: Settings → Linked Devices → Link a Device
4. Scan the QR code
5. Once connected, it will say: `✅ Connected to WhatsApp successfully`

**Subsequent runs:** The session is saved in `auth_info_baileys/` folder, no QR needed.

## How It Works

### Message Flow

1. **WhatsApp receives message** → Baileys captures it
2. **Text extraction** → Pulls message text + image caption
3. **Image download** → Converts to Base64 if image present
4. **HTTP POST to Python** → Sends data to `/parse-watch` endpoint
5. **AI analysis** → GPT-4o Vision parses the content
6. **Deduplication check** → Queries SQLite for recent duplicates
7. **Deal scoring** → Compares price to `target_prices.json`
8. **Storage** → Saves WTS listings to database

### AI Parsing Logic

The AI understands:
- **Watch shorthand**: NIB, B+P, stickered, papers only, naked
- **Condition scales**: 1-10 or descriptive (unworn, mint, etc.)
- **Reference numbers**: Rolex 6-digit, Patek dash format, etc.
- **Price formats**: "17.5k" → 17500, "17500++" → 17500
- **Sentiment**: WTS (Want to Sell) vs WTB (Want to Buy)

### Deduplication

Listings are considered duplicates if:
- Same `ref_number` AND same `price_usd`
- Within last 4 hours (configurable via `DEDUPLICATION_HOURS`)

### Deal Scoring

Formula:
```
discount = (target_price - actual_price) / target_price * 100
deal_score = 50 + (discount * 2.5)

Score = 100: 20%+ below market (HOT DEAL!)
Score = 50:  At market price
Score = 0:   20%+ above market
```

Scores 80+ are flagged as hot deals in the logs.

## API Endpoints

### POST `/parse-watch`

Parses a watch listing from text and/or image.

**Request:**
```json
{
  "text": "WTS Rolex Sub 126610LN. 2023. Unworn. B+P. $12,000 firm.",
  "imageBase64": "base64_encoded_image_data",
  "groupName": "Watch Dealers NYC",
  "senderId": "1234567890@s.whatsapp.net",
  "messageId": "msg_12345",
  "timestamp": 1705089600
}
```

**Response (valid listing):**
```json
{
  "status": "parsed",
  "brand": "Rolex",
  "model": "Submariner",
  "ref_number": "126610LN",
  "year": "2023",
  "condition": "Unworn",
  "condition_score": 10,
  "inclusions": "Box and Papers",
  "is_full_set": true,
  "price_usd": 12000,
  "sentiment": "WTS",
  "deal_score": 54,
  "raw_text": "WTS Rolex Sub 126610LN...",
  "has_image": true
}
```

**Response (ignored message):**
```json
{
  "status": "ignore",
  "reason": "Not a watch listing"
}
```

**Response (duplicate):**
```json
{
  "status": "duplicate",
  "message": "Listing already seen in last 4 hours"
}
```

### POST `/score-deal`

**NEW!** Advanced multi-factor deal scoring with risk assessment.

See the [Advanced Deal Scoring Engine](#advanced-deal-scoring-engine) section above for full documentation and examples.

### GET `/stats`

Get database statistics.

**Response:**
```json
{
  "total_listings": 247,
  "by_sentiment": {
    "WTS": 198,
    "WTB": 49
  },
  "top_brands": [
    {"brand": "Rolex", "count": 156},
    {"brand": "Patek Philippe", "count": 34}
  ]
}
```

### GET `/health`

Health check endpoint.

## Database Schema

```sql
CREATE TABLE listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT UNIQUE,
    brand TEXT,
    model TEXT,
    ref_number TEXT,
    price_usd INTEGER,
    sentiment TEXT,
    group_name TEXT,
    sender_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    raw_json TEXT
);
```

Access the database:
```bash
sqlite3 watch_listings.db
```

Query examples:
```sql
-- All Rolex listings today
SELECT * FROM listings 
WHERE brand = 'Rolex' 
AND date(created_at) = date('now');

-- Best deals (lowest prices for ref)
SELECT ref_number, MIN(price_usd) as best_price, COUNT(*) as count
FROM listings
WHERE sentiment = 'WTS'
GROUP BY ref_number
ORDER BY count DESC;
```

## Troubleshooting

### "Connection closed" errors

**Solution:** WhatsApp may have logged you out. Delete `auth_info_baileys/` folder and scan QR again.

### "Python API not running"

**Solution:** Make sure FastAPI is running:
```bash
uvicorn main:app --reload
```

### "Invalid JSON from AI"

**Cause:** Occasionally GPT-4o may return malformed JSON.  
**Solution:** The system will log the error. Check OpenAI API status.

### Images not downloading

**Solution:** Ensure you have latest Baileys version:
```bash
npm update @whiskeysockets/baileys
```

### Too many duplicates detected

**Solution:** Adjust `DEDUPLICATION_HOURS` in `.env`. Set to `0` to disable.

### Group messages not captured

**Solution:** Check group name spelling in `WATCHED_GROUPS`. Leave empty to capture all groups.

## Advanced Customization

### Add Custom Watch Brands

Edit the system prompt in `main.py` to teach the AI about new brands:

```python
WATCH_EXPERT_PROMPT = """
...
REFERENCE NUMBER KNOWLEDGE:
- Rolex: 6 digits (e.g., 126610LN)
- YourBrand: Format here
"""
```

### Alerting on Hot Deals

Add webhook integration in `main.py`:

```python
if result.get("deal_score", 0) >= 85:
    # Send to Discord/Slack/Email
    await send_alert(result)
```

### Export to Excel

```python
import pandas as pd
import sqlite3

conn = sqlite3.connect('watch_listings.db')
df = pd.read_sql_query("SELECT * FROM listings", conn)
df.to_excel('watch_export.xlsx', index=False)
```

## Production Deployment

### Using PM2 (Process Manager)

```bash
# Install PM2
npm install -g pm2

# Start services
pm2 start server.js --name whatsapp-scraper
pm2 start "uvicorn main:app --host 0.0.0.0 --port 8000" --name watch-api

# Save configuration
pm2 save
pm2 startup
```

### Docker Support

Create `docker-compose.yml`:

```yaml
version: '3.8'
services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - ./watch_listings.db:/app/watch_listings.db
  
  scraper:
    build: .
    command: node server.js
    depends_on:
      - api
    volumes:
      - ./auth_info_baileys:/app/auth_info_baileys
```

## Security Best Practices

1. **Never commit `.env`** - Add to `.gitignore`
2. **Rotate OpenAI keys** regularly
3. **Use environment secrets** in production
4. **Restrict API access** - Add authentication middleware
5. **Monitor API costs** - Set OpenAI usage limits

## License

MIT

## Support

For issues, questions, or feature requests, please open a GitHub issue.
