# API Documentation

Complete API reference for the Watch Trading Engine v10.2

## Base URL

```
Production: https://your-domain.com
Development: http://localhost:8000
```

## Authentication

Most endpoints are public, but some require authentication via the `admin_secret` parameter.

### Admin Endpoints

Pass `admin_secret` as a query parameter or in request body:

```bash
curl -X POST http://localhost:8000/admin/update-target \
  -H "Content-Type: application/json" \
  -d '{"ref_number": "126610LN", "market_price": 14000, "admin_secret": "your-secret"}'
```

## Endpoints

### Health & Status

#### GET /health

Health check endpoint with system diagnostics.

**Response:**
```json
{
  "status": "online",
  "database": "connected",
  "cache_size": 176,
  "uptime": 86400.5,
  "timestamp": "2024-01-15T10:30:00"
}
```

**Status Codes:**
- `200 OK` - System healthy
- `503 Service Unavailable` - System degraded

---

### Core Processing

#### POST /parse-watch

Parse and analyze a watch listing from text and/or images.

**Rate Limit:** 20 requests/minute

**Request:**
```json
{
  "text": "WTS Rolex Submariner 126610LN, 2023, Full Set, $13,500",
  "imageBase64": "base64_encoded_image_data_optional",
  "groupName": "Watch Dealers NYC",
  "senderId": "1234567890@s.whatsapp.net",
  "messageId": "unique_message_id",
  "timestamp": 1705323456
}
```

**Response (Success):**
```json
{
  "status": "success",
  "ref": "126610LN",
  "price": 13500,
  "market_price": 13800,
  "score": 22,
  "tier": "NORMAL",
  "drift": false,
  "sentiment": "WTS",
  "hash": "a1b2c3d4"
}
```

**Response (Ignored):**
```json
{
  "status": "ignore",
  "code": "UNKNOWN_REFERENCE"
}
```

**Response (Duplicate):**
```json
{
  "status": "error",
  "code": "DuplicateError",
  "detail": "Message already processed"
}
```

**Status Codes:**
- `200 OK` - Successfully processed
- `400 Bad Request` - Invalid input or duplicate
- `429 Too Many Requests` - Rate limit exceeded

**Alert Tiers:**
- `URGENT` - Score ≥ 350 (35%+ below market)
- `PUSH` - Score ≥ 200 (20%+ below market)
- `NORMAL` - Score < 200

---

### Analytics & Metrics

#### GET /metrics

System metrics and statistics.

**Parameters:**
- `admin_secret` (optional) - For detailed metrics

**Response (Basic):**
```json
{
  "status": "basic_metrics_only",
  "cache_size": 176,
  "timestamp": "2024-01-15T10:30:00",
  "message": "Provide admin_secret for detailed metrics"
}
```

**Response (Detailed - with admin_secret):**
```json
{
  "detailed_metrics": true,
  "daily_activity": {
    "URGENT": 5,
    "PUSH": 23,
    "NORMAL": 142
  },
  "top_references": {
    "126610LN": 45,
    "5711/1A-010": 23,
    "15500ST": 19
  },
  "hourly_stats": {
    "14": {"listings": 12, "avg_score": 45.2},
    "15": {"listings": 18, "avg_score": 38.7}
  },
  "cache_size": 176,
  "database": "trade_desk.db",
  "uptime": 86400.5,
  "timestamp": "2024-01-15T10:30:00"
}
```

---

#### GET /recent-trades

Get recent trade listings for dashboard display.

**Parameters:**
- `limit` (optional, default: 50) - Number of results
- `offset` (optional, default: 0) - Pagination offset

**Response:**
```json
[
  {
    "id": 123,
    "brand": "Rolex",
    "model": "Submariner",
    "ref_number": "126610LN",
    "price_usd": 13500,
    "deal_score": 22,
    "alert_tier": "NORMAL",
    "sentiment": "WTS",
    "group_name": "Watch Dealers NYC",
    "sender_id": "1234567890@s.wha...",
    "timestamp": "2024-01-15 10:30:00",
    "drift": false
  }
]
```

---

#### GET /stats/ref/{ref_number}

Get detailed statistics for a specific watch reference.

**Parameters:**
- `ref_number` (path) - Watch reference number
- `days` (optional, default: 7) - Historical period

**Example:**
```bash
GET /stats/ref/126610LN?days=30
```

**Response:**
```json
{
  "ref_number": "126610LN",
  "market_price": 13800,
  "stats": {
    "min_price": 12500,
    "max_price": 14800,
    "avg_price": 13650.50,
    "total_listings": 45,
    "avg_score": 31.20
  },
  "recent_listings": [
    {
      "price_usd": 13500,
      "deal_score": 22,
      "alert_tier": "NORMAL",
      "sentiment": "WTS",
      "timestamp": "2024-01-15 10:30:00"
    }
  ]
}
```

**Status Codes:**
- `200 OK` - Statistics found
- `404 Not Found` - No data for reference

---

### Data Export

#### GET /export/trades

Export trade data in various formats.

**Authentication:** Required (`admin_secret`)

**Parameters:**
- `format` - Export format (`json` or `csv`)
- `days` (default: 7) - Historical period
- `admin_secret` - Admin authentication

**Example (JSON):**
```bash
GET /export/trades?format=json&days=30&admin_secret=your-secret
```

**Response (JSON):**
```json
{
  "trades": [
    {
      "id": 123,
      "brand": "Rolex",
      "model": "Submariner",
      "ref_number": "126610LN",
      "price_usd": 13500,
      "deal_score": 22,
      "alert_tier": "NORMAL",
      "sentiment": "WTS",
      "group_name": "Watch Dealers NYC",
      "timestamp": "2024-01-15 10:30:00",
      "raw_text": "WTS Rolex Sub..."
    }
  ],
  "count": 1
}
```

**Example (CSV):**
```bash
GET /export/trades?format=csv&days=30&admin_secret=your-secret
```

**Response:** CSV file download

**Status Codes:**
- `200 OK` - Export successful
- `400 Bad Request` - Invalid format
- `403 Forbidden` - Invalid admin secret

**Rate Limit:** 5 requests/minute

---

### Admin Operations

#### POST /admin/update-target

Update market price for a watch reference.

**Authentication:** Required

**Request:**
```json
{
  "ref_number": "126610LN",
  "market_price": 14000,
  "admin_secret": "your-admin-secret"
}
```

**Response:**
```json
{
  "status": "success",
  "ref": "126610LN",
  "price": 14000,
  "cache_size": 176
}
```

**Status Codes:**
- `200 OK` - Update successful
- `403 Forbidden` - Invalid admin secret
- `422 Unprocessable Entity` - Validation error

---

## Error Responses

All errors follow this format:

```json
{
  "status": "error",
  "code": "ErrorClassName",
  "detail": "Human-readable error message"
}
```

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `DuplicateError` | 400 | Listing already processed recently |
| `OverpricedError` | 400 | Price significantly above market |
| `AIProcessingError` | 400 | AI analysis failed |
| `WatchEngineError` | 400 | General engine error |
| `ValidationError` | 422 | Input validation failed |
| `RateLimitExceeded` | 429 | Too many requests |

---

## Rate Limiting

Rate limits are applied per IP address:

| Endpoint | Limit |
|----------|-------|
| `/parse-watch` | 20/minute |
| `/metrics` | 10/minute |
| `/export/trades` | 5/minute |
| All others | 60/minute |

**Rate Limit Headers:**
```
X-RateLimit-Limit: 20
X-RateLimit-Remaining: 15
X-RateLimit-Reset: 1705323500
```

---

## Webhooks (Optional)

Configure webhooks to receive notifications for high-value deals.

### Configuration

Set environment variables:

```bash
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

### Webhook Payload

```json
{
  "event": "hot_deal_detected",
  "data": {
    "ref_number": "126610LN",
    "price_usd": 12000,
    "market_price": 13800,
    "deal_score": 130,
    "alert_tier": "URGENT",
    "group_name": "Watch Dealers NYC",
    "timestamp": "2024-01-15T10:30:00Z"
  }
}
```

---

## WebSocket API (Future)

Real-time updates via WebSocket connection.

### Connect

```javascript
const ws = new WebSocket('ws://localhost:8000/ws');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('New trade:', data);
};
```

### Events

- `trade.created` - New trade listing
- `trade.updated` - Price changed
- `deal.urgent` - Hot deal detected
- `system.status` - System status change

---

## SDK Examples

### Python

```python
import requests

class WatchTradingClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
    
    def parse_watch(self, text, image_base64=None, group_name=""):
        response = requests.post(
            f"{self.base_url}/parse-watch",
            json={
                "text": text,
                "imageBase64": image_base64,
                "groupName": group_name,
                "senderId": "api_client",
                "messageId": f"api_{int(time.time())}"
            }
        )
        return response.json()
    
    def get_recent_trades(self, limit=50):
        response = requests.get(
            f"{self.base_url}/recent-trades",
            params={"limit": limit}
        )
        return response.json()
    
    def get_ref_stats(self, ref_number, days=7):
        response = requests.get(
            f"{self.base_url}/stats/ref/{ref_number}",
            params={"days": days}
        )
        return response.json()

# Usage
client = WatchTradingClient()
result = client.parse_watch("WTS Rolex Sub 126610LN $13,500")
print(result)
```

### JavaScript/Node.js

```javascript
const axios = require('axios');

class WatchTradingClient {
  constructor(baseURL = 'http://localhost:8000') {
    this.client = axios.create({ baseURL });
  }

  async parseWatch(text, imageBase64 = null, groupName = '') {
    const response = await this.client.post('/parse-watch', {
      text,
      imageBase64,
      groupName,
      senderId: 'api_client',
      messageId: `api_${Date.now()}`
    });
    return response.data;
  }

  async getRecentTrades(limit = 50) {
    const response = await this.client.get('/recent-trades', {
      params: { limit }
    });
    return response.data;
  }

  async getRefStats(refNumber, days = 7) {
    const response = await this.client.get(`/stats/ref/${refNumber}`, {
      params: { days }
    });
    return response.data;
  }
}

// Usage
const client = new WatchTradingClient();
const result = await client.parseWatch('WTS Rolex Sub 126610LN $13,500');
console.log(result);
```

### cURL Examples

```bash
# Parse watch listing
curl -X POST http://localhost:8000/parse-watch \
  -H "Content-Type: application/json" \
  -d '{
    "text": "WTS Rolex Sub 126610LN $13,500",
    "groupName": "Test Group",
    "senderId": "test@example.com",
    "messageId": "test_123"
  }'

# Get recent trades
curl http://localhost:8000/recent-trades?limit=10

# Get reference statistics
curl http://localhost:8000/stats/ref/126610LN?days=30

# Update target price (requires admin secret)
curl -X POST http://localhost:8000/admin/update-target \
  -H "Content-Type: application/json" \
  -d '{
    "ref_number": "126610LN",
    "market_price": 14000,
    "admin_secret": "your-secret"
  }'

# Export data (requires admin secret)
curl "http://localhost:8000/export/trades?format=csv&days=30&admin_secret=your-secret" \
  -o trades_export.csv
```

---

## Interactive API Documentation

Once the server is running, visit:

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

These provide interactive API exploration and testing.

---

## Support

- **GitHub Issues:** Report bugs and request features
- **Documentation:** https://github.com/YOUR_USERNAME/Watchy
- **Email:** support@example.com
