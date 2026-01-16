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
✅ **SQLite storage** - saves all WTS listings  
✅ **Multi-group support** - filter specific groups or monitor all  
✅ **Robust reconnection** - handles WhatsApp disconnections automatically  
✅ **Watch terminology expert** - understands NIB, B+P, stickered, etc.

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

---

## 🚀 Production-Grade Enhanced Server

A new production-grade implementation is available at `server-enhanced.js` with advanced features:

### ✨ Key Enhancements

1. **Redis Session Storage** - Multi-instance support with persistent sessions
2. **Bull Queue Processing** - Reliable message queuing with dead letter queue
3. **Winston Logging** - Structured logging with daily rotation
4. **Prometheus Metrics** - `/metrics` endpoint for monitoring
5. **Circuit Breaker** - Graceful degradation when API is down
6. **Image Compression** - Automatic compression using Sharp
7. **Health Checks** - `/health`, `/ready`, `/live` endpoints
8. **Docker Support** - Full docker-compose setup with Redis
9. **PM2 Ready** - Production process management

### 📖 Quick Start (Enhanced Version)

```bash
# 1. Install dependencies (if not done)
npm install

# 2. Setup Redis (required for enhanced features)
docker run -d -p 6379:6379 redis:7-alpine

# Or use file-based auth (single instance):
# Set USE_FILE_AUTH=true in .env

# 3. Configure environment
cp .env.example .env
nano .env  # Add your OPENAI_API_KEY

# 4. Start with PM2 (recommended)
pm2 start ecosystem.config.js
pm2 logs
pm2 monit

# Or start directly
node server-enhanced.js

# 5. Check health
curl http://localhost:3000/health
curl http://localhost:3000/metrics
```

### 📊 Monitoring

Access these endpoints for monitoring:

- **Health Check**: http://localhost:3000/health
- **Metrics**: http://localhost:3000/metrics
- **Stats**: http://localhost:3000/stats
- **Readiness**: http://localhost:3000/ready
- **Liveness**: http://localhost:3000/live

### 🐳 Docker Deployment

```bash
# Start full stack (scraper + Redis + Python API)
docker-compose up -d

# View logs
docker-compose logs -f scraper

# Scale instances
docker-compose up -d --scale scraper=3
```

### 📚 Documentation

- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Complete deployment guide
- **[.env.example](.env.example)** - Configuration template
- **[ecosystem.config.js](ecosystem.config.js)** - PM2 configuration
- **[docker-compose.yml](docker-compose.yml)** - Docker setup

### 🔄 Migration from Basic Server

The enhanced server (`server-enhanced.js`) is fully backward compatible. To migrate:

1. Copy `.env.example` to `.env` and configure
2. Start Redis or set `USE_FILE_AUTH=true`
3. Replace `npm start` with `node server-enhanced.js`
4. Or use PM2: `pm2 start ecosystem.config.js`

The basic `server.js` remains available for simple deployments.

