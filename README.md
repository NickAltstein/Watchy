# Watch Trading Engine 🚀⌚

> **Production-ready AI-powered luxury watch trading system**  
> Automatically scrape, analyze, and score watch listings from WhatsApp groups using GPT-4o Vision and advanced deal detection algorithms.

[![CI/CD Pipeline](https://github.com/NickAiNYC/Watchy/workflows/CI/CD%20Pipeline/badge.svg)](https://github.com/NickAiNYC/Watchy/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Node.js 18+](https://img.shields.io/badge/node-18+-green.svg)](https://nodejs.org/)

---

## 📋 Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Documentation](#api-documentation)
- [Dashboard](#dashboard)
- [Notifications](#notifications)
- [Deployment](#deployment)
- [Contributing](#contributing)
- [Security](#security)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## 🎯 Overview

Watch Trading Engine is an enterprise-grade system for monitoring luxury watch marketplaces via WhatsApp groups. It combines:

- **AI Vision Analysis** - GPT-4o processes text + images
- **Smart Deal Detection** - Algorithmic scoring based on market data
- **Multi-Channel Alerts** - Discord, Slack, Telegram, Email
- **Real-Time Dashboard** - Live trade monitoring interface
- **Production Infrastructure** - Docker, CI/CD, monitoring

Perfect for watch dealers, collectors, and trading desks looking to gain competitive advantage through automation.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    WhatsApp Groups                          │
│              (Luxury Watch Trading Channels)                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ↓
        ┌────────────────────────────────┐
        │   Node.js WhatsApp Service     │
        │        (server.js)             │
        │                                │
        │  • Baileys WebSocket           │
        │  • Message capture             │
        │  • Image download              │
        │  • Content extraction          │
        └────────────┬───────────────────┘
                     │ HTTP POST
                     ↓
        ┌────────────────────────────────┐
        │   Python FastAPI Backend       │
        │         (main.py)              │
        │                                │
        │  • GPT-4o Vision AI            │
        │  • Deal score calculation      │
        │  • Deduplication logic         │
        │  • SQLite database             │
        │  • Cache management            │
        └────────────┬───────────────────┘
                     │
                     ├──────────┐
                     ↓          ↓
        ┌──────────────────┐  ┌──────────────────┐
        │  Dashboard UI    │  │  Notification     │
        │  (dash.html)     │  │  Service          │
        │                  │  │                   │
        │  • Real-time     │  │  • Discord        │
        │    updates       │  │  • Slack          │
        │  • Filtering     │  │  • Telegram       │
        │  • Analytics     │  │  • Email          │
        └──────────────────┘  └──────────────────┘
```

### Technology Stack

**Backend:**
- Python 3.10+ with FastAPI
- SQLite with WAL mode
- AsyncIO for concurrency
- Connection pooling

**Frontend:**
- Alpine.js for reactivity
- Tailwind CSS for styling
- Server-Sent Events for updates

**Infrastructure:**
- Docker & Docker Compose
- GitHub Actions CI/CD
- Nginx reverse proxy
- Let's Encrypt SSL

---

## ✨ Key Features

### Core Functionality

✅ **Real-time WhatsApp Monitoring**  
Native protocol integration with Baileys (no browser automation required)

✅ **AI Vision Analysis**  
GPT-4o processes both text and images for accurate listing extraction

✅ **Intelligent Deal Scoring**  
Algorithmic scoring system compares prices against market data

✅ **Smart Deduplication**  
Prevents duplicate alerts using temporal and hash-based detection

✅ **Multi-Channel Notifications**  
Instant alerts via Discord, Slack, Telegram, and Email

✅ **Live Dashboard**  
Real-time web interface with automatic updates and filtering

### Advanced Features

🔐 **Enterprise Security**  
- Admin secret authentication
- Rate limiting on all endpoints
- Input validation and sanitization
- CORS configuration

📊 **Analytics & Reporting**  
- Historical price tracking
- Reference statistics
- Deal performance metrics
- Data export (CSV, JSON)

🚀 **Production Ready**  
- Docker containerization
- CI/CD pipeline with GitHub Actions
- Health checks and monitoring
- Database connection pooling
- Automated backups

🔔 **Flexible Notifications**  
- Configurable alert thresholds
- Multiple channel support
- Rich formatting (embeds, cards)
- Deal tier classification (URGENT, PUSH, NORMAL)

---

## 🚀 Quick Start

Get up and running in under 5 minutes:

```bash
# 1. Clone repository
git clone https://github.com/NickAiNYC/Watchy.git
cd Watchy

# 2. Configure environment
cp .env.template .env
# Edit .env with your API keys

# 3. Start with Docker (recommended)
docker-compose up -d

# 4. Access dashboard
open http://localhost/dash.html

# 5. First-time WhatsApp setup
# Scan QR code in terminal to link your WhatsApp account
```

That's it! The system will now monitor your WhatsApp groups and display deals on the dashboard.

---

## 💻 Usage

### Running the System

#### Option 1: Docker Compose (Production)

```bash
# Start all services
docker-compose up -d

# View real-time logs
docker-compose logs -f

# Stop services
docker-compose down
```

#### Option 2: Manual (Development)

**Terminal 1 - Python API:**
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 - WhatsApp Service:**
```bash
npm start
# or for development with auto-reload:
npm run dev
```

**Terminal 3 - Full Stack:**
```bash
npm run dev:full
# This runs both services concurrently
```

### First-Time WhatsApp Setup

1. Start the WhatsApp service
2. A QR code will appear in your terminal
3. Open WhatsApp on your phone
4. Go to: **Settings → Linked Devices → Link a Device**
5. Scan the QR code
6. Wait for confirmation: `✅ Connected to WhatsApp successfully`

**Subsequent runs:** Session is saved in `auth_info_baileys/` - no QR needed.

### Accessing the Dashboard

Open your browser to:
- Local: `http://localhost:8000/dash.html`
- Docker: `http://localhost/dash.html`

The dashboard provides:
- Real-time trade listings
- Deal score visualization
- Filtering by tier/sentiment
- Reference statistics
- Admin console access

---

## 📚 API Documentation

### Interactive Documentation

Once running, access interactive API docs:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

### Quick API Examples

**Check system health:**
```bash
curl http://localhost:8000/health
```

**Get recent trades:**
```bash
curl http://localhost:8000/recent-trades?limit=20
```

**Get reference statistics:**
```bash
curl http://localhost:8000/stats/ref/126610LN?days=30
```

**Export data (requires admin secret):**
```bash
curl "http://localhost:8000/export/trades?format=csv&admin_secret=YOUR_SECRET" -o export.csv
```

For complete API documentation, see [API.md](./API.md)

---
---

## 🔔 Notifications

The system supports multiple notification channels for hot deal alerts.

### Setup Instructions

#### Discord

1. Create a webhook in your Discord server
2. Copy the webhook URL
3. Add to `.env`: `DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...`

Notifications include:
- Colored embeds based on tier
- Deal details and calculations
- Source group information

#### Slack

1. Create an incoming webhook in your Slack workspace
2. Copy the webhook URL
3. Add to `.env`: `SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...`

Notifications use Slack blocks for rich formatting.

#### Telegram

1. Create a bot via @BotFather
2. Get your chat ID (use @userinfobot)
3. Add to `.env`:
   ```
   TELEGRAM_BOT_TOKEN=your-token
   TELEGRAM_CHAT_ID=your-chat-id
   ```

#### Email

Configure SMTP settings in `.env`:
```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
ALERT_EMAIL_TO=recipient@example.com
```

For Gmail, use an [App Password](https://support.google.com/accounts/answer/185833).

### Alert Tiers

- **URGENT** (Score ≥ 350): 35%+ below market - immediate action
- **PUSH** (Score ≥ 200): 20%+ below market - strong opportunity
- **NORMAL** (Score < 200): Tracked but not urgent

---

## 🚢 Deployment

### Quick Deploy Options

**Heroku (1-Click):**
```bash
heroku create watch-trading
heroku config:set OPENAI_API_KEY=sk-...
git push heroku main
```

**AWS ECS (via Docker):**
See [DEPLOYMENT.md](./DEPLOYMENT.md) for complete AWS setup

**Google Cloud Run:**
```bash
gcloud builds submit --tag gcr.io/PROJECT_ID/watch-trading
gcloud run deploy --image gcr.io/PROJECT_ID/watch-trading
```

**DigitalOcean App Platform:**
- Connect your GitHub repository
- Configure environment variables
- Deploy with one click

For detailed deployment guides, see [DEPLOYMENT.md](./DEPLOYMENT.md)

### Production Checklist

- [ ] Set strong `ADMIN_SECRET` (32+ characters)
- [ ] Configure HTTPS/SSL certificate
- [ ] Set `DEBUG=false` in production
- [ ] Configure CORS for your domain
- [ ] Set up automated backups
- [ ] Configure monitoring and logging
- [ ] Enable rate limiting
- [ ] Set up firewall rules
- [ ] Configure notification channels
- [ ] Test disaster recovery procedures

---

---

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

Quick start for contributors:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes and add tests
4. Run linting: `npm run lint`
5. Commit with conventional commits: `git commit -m "feat: add amazing feature"`
6. Push and create a Pull Request

---

## 🔒 Security

### Security Best Practices

1. **Never commit secrets** - Use `.env` for all sensitive data
2. **Rotate API keys regularly** - Set up key rotation schedule
3. **Use strong admin secrets** - Minimum 32 characters, cryptographically random
4. **Enable HTTPS** - Always use SSL/TLS in production
5. **Restrict API access** - Use firewall rules and rate limiting
6. **Monitor for anomalies** - Set up alerts for unusual activity
7. **Keep dependencies updated** - Run `npm audit` and `pip audit` regularly
8. **Backup database** - Automated daily backups with encryption

### Reporting Security Issues

Please report security vulnerabilities to: [security@example.com](mailto:security@example.com)

Do not create public GitHub issues for security vulnerabilities.

---

## 🔧 Troubleshooting

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

## 🔧 Troubleshooting

### Common Issues

**WhatsApp Connection Issues**

```bash
# Problem: "Connection closed" errors
# Solution: Delete session and re-authenticate
rm -rf auth_info_baileys/
npm start  # Scan QR code again
```

**Database Locked Error**

```bash
# Problem: Database locked
# Solution: Check WAL mode and close other connections
sqlite3 trade_desk.db "PRAGMA journal_mode;"
# Should return: wal
```

**Python API Not Running**

```bash
# Problem: Node.js can't connect to API
# Solution: Start FastAPI service
uvicorn main:app --host 0.0.0.0 --port 8000

# Check if running:
curl http://localhost:8000/health
```

**Out of Memory**

```bash
# Problem: Container crashes with OOM
# Solution: Increase Docker memory limit
docker-compose down
# Edit docker-compose.yml, add resources limits
docker-compose up -d
```

### Getting Help

- 📖 **Documentation:** [Full docs](./API.md)
- 🐛 **Bug Reports:** [GitHub Issues](https://github.com/NickAiNYC/Watchy/issues)
- 💬 **Discussions:** [GitHub Discussions](https://github.com/NickAiNYC/Watchy/discussions)

---

<div align="center">

**Made with ⌚ by watch enthusiasts, for watch enthusiasts**

⭐ Star us on GitHub — it helps!

[Report Bug](https://github.com/NickAiNYC/Watchy/issues) · [Request Feature](https://github.com/NickAiNYC/Watchy/issues) · [Documentation](./API.md)

</div>
