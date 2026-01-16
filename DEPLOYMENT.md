# Deployment Guide - Production-Grade WhatsApp Scraper

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Architecture Overview](#architecture-overview)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Deployment Options](#deployment-options)
6. [Monitoring](#monitoring)
7. [Troubleshooting](#troubleshooting)

## Prerequisites

### System Requirements
- **Node.js**: 18.0.0 or higher
- **Python**: 3.10 or higher
- **Redis**: 7.0 or higher (optional, for multi-instance support)
- **Memory**: Minimum 2GB RAM
- **Storage**: 10GB free space

### API Keys
- OpenAI API key with GPT-4o access
- DeepSeek API key (optional)

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                   WHATSAPP SCRAPER                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐     ┌──────────────┐    ┌─────────────┐ │
│  │   Baileys    │────▶│  Bull Queue  │───▶│   Python    │ │
│  │   Client     │     │   (Redis)    │    │     API     │ │
│  └──────────────┘     └──────────────┘    └─────────────┘ │
│         │                     │                    │        │
│         │                     │                    │        │
│  ┌──────▼─────────────────────▼────────────────────▼─────┐ │
│  │           Redis (Session + Queue Storage)             │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌──────────────┐     ┌──────────────┐                     │
│  │   Health     │     │  Prometheus  │                     │
│  │   Server     │     │   Metrics    │                     │
│  │  (Port 3000) │     │  (/metrics)  │                     │
│  └──────────────┘     └──────────────┘                     │
└─────────────────────────────────────────────────────────────┘
```

## Installation

### Option 1: Local Development

```bash
# 1. Clone the repository
git clone https://github.com/NickAiNYC/Watchy.git
cd Watchy

# 2. Install Node.js dependencies
npm install

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Install and start Redis (if using session storage)
# On Ubuntu/Debian:
sudo apt-get install redis-server
sudo systemctl start redis-server

# On macOS:
brew install redis
brew services start redis

# On Docker:
docker run -d -p 6379:6379 redis:7-alpine

# 5. Copy and configure environment file
cp .env.example .env
nano .env  # Edit with your configuration

# 6. Start the services
# Terminal 1 - Python API:
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 - WhatsApp Scraper:
node server-enhanced.js
```

### Option 2: Using PM2 (Recommended for Production)

```bash
# 1. Install PM2 globally
npm install -g pm2

# 2. Configure environment
cp .env.example .env
nano .env  # Edit configuration

# 3. Start both services with PM2
pm2 start ecosystem.config.js

# 4. View logs
pm2 logs

# 5. Monitor processes
pm2 monit

# 6. Save PM2 configuration
pm2 save

# 7. Setup PM2 to start on boot
pm2 startup
# Follow the instructions displayed
```

### Option 3: Using Docker (Easiest)

```bash
# 1. Create environment file
cp .env.example .env
nano .env  # Add your API keys

# 2. Build and start containers
docker-compose up -d

# 3. View logs
docker-compose logs -f scraper

# 4. Stop containers
docker-compose down

# 5. Rebuild after changes
docker-compose up -d --build
```

## Configuration

### Environment Variables

#### Required Variables
```env
OPENAI_API_KEY=sk-...              # Your OpenAI API key
ADMIN_SECRET=your-secret-key       # Admin API secret
```

#### Redis Configuration
```env
REDIS_HOST=localhost               # Redis host
REDIS_PORT=6379                    # Redis port
REDIS_PASSWORD=                    # Redis password (if any)
USE_FILE_AUTH=false                # Set to true to use file-based auth
```

#### WhatsApp Configuration
```env
SESSION_ID=default                 # Unique session ID
WATCHED_GROUPS=Group1,Group2       # Filter specific groups (optional)
MAX_IMAGE_SIZE_MB=5                # Maximum image size
MAX_RECONNECT_ATTEMPTS=10          # Max reconnection attempts
```

#### Performance Tuning
```env
QUEUE_CONCURRENCY=1                # Concurrent message processing
API_TIMEOUT=10000                  # API timeout in ms
LOG_LEVEL=info                     # Logging level
```

### Group Filtering

You can filter groups using:

1. **Exact names**: `WATCHED_GROUPS=Watch Dealers NYC,Luxury Watches`
2. **All groups**: Leave `WATCHED_GROUPS` empty
3. **Regex patterns**: Modify `groupFilters` in code to use regex

## Deployment Options

### PM2 Deployment

PM2 provides process management, auto-restart, and log rotation.

```bash
# Start services
pm2 start ecosystem.config.js

# View status
pm2 status

# View logs
pm2 logs whatsapp-scraper
pm2 logs python-api

# Restart services
pm2 restart all

# Stop services
pm2 stop all

# Delete processes
pm2 delete all
```

### Docker Deployment

Docker provides isolation and easy deployment.

```bash
# Start services
docker-compose up -d

# Scale scraper instances (if using Redis)
docker-compose up -d --scale scraper=3

# View logs
docker-compose logs -f

# Restart services
docker-compose restart

# Stop services
docker-compose down

# Update and restart
git pull
docker-compose down
docker-compose up -d --build
```

### Kubernetes Deployment

For large-scale deployments, use Kubernetes:

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: whatsapp-scraper
spec:
  replicas: 3
  selector:
    matchLabels:
      app: whatsapp-scraper
  template:
    metadata:
      labels:
        app: whatsapp-scraper
    spec:
      containers:
      - name: scraper
        image: yourregistry/whatsapp-scraper:latest
        env:
        - name: REDIS_HOST
          value: "redis-service"
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: api-keys
              key: openai
        resources:
          limits:
            memory: "2Gi"
            cpu: "1000m"
          requests:
            memory: "512Mi"
            cpu: "250m"
```

## Monitoring

### Health Checks

The health server runs on port 3000 and provides several endpoints:

```bash
# Overall health status
curl http://localhost:3000/health

# Readiness check (for Kubernetes)
curl http://localhost:3000/ready

# Liveness check
curl http://localhost:3000/live

# Application statistics
curl http://localhost:3000/stats

# Prometheus metrics
curl http://localhost:3000/metrics
```

### Prometheus Integration

Add this job to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'whatsapp-scraper'
    static_configs:
      - targets: ['localhost:3000']
    metrics_path: '/metrics'
    scrape_interval: 15s
```

### Grafana Dashboard

Key metrics to monitor:
- `whatsapp_messages_received_total` - Total messages received
- `whatsapp_messages_processed_total` - Successfully processed messages
- `whatsapp_connection_status` - Connection status (1 = connected)
- `api_latency_seconds` - API call latency
- `queue_size` - Current queue size
- `circuit_breaker_status` - Circuit breaker state

### Logging

Logs are stored in the `logs/` directory:
- `combined-YYYY-MM-DD.log` - All logs
- `error-YYYY-MM-DD.log` - Error logs only
- Console output with colors and timestamps

View logs:
```bash
# Tail all logs
tail -f logs/combined-*.log

# Tail errors only
tail -f logs/error-*.log

# With PM2
pm2 logs whatsapp-scraper --lines 100
```

## Troubleshooting

### WhatsApp Connection Issues

**Problem**: QR code not appearing
```bash
# Solution: Clear session and reconnect
rm -rf auth_info_baileys/
# Restart the service
pm2 restart whatsapp-scraper
```

**Problem**: Connection keeps dropping
```bash
# Check network connectivity
ping api.whatsapp.com

# Increase reconnect attempts
# In .env:
MAX_RECONNECT_ATTEMPTS=20
RECONNECT_INTERVAL=15000
```

### Redis Connection Issues

**Problem**: Redis connection refused
```bash
# Check if Redis is running
redis-cli ping

# If not running, start it
sudo systemctl start redis-server

# Or use file-based auth instead
# In .env:
USE_FILE_AUTH=true
```

### High Memory Usage

**Problem**: Memory usage exceeds 2GB
```bash
# Reduce image size limit
# In .env:
MAX_IMAGE_SIZE_MB=3

# Reduce queue concurrency
QUEUE_CONCURRENCY=1

# Restart with PM2 memory limit
pm2 restart whatsapp-scraper --max-memory-restart 2G
```

### API Timeouts

**Problem**: API calls timing out
```bash
# Increase timeout
# In .env:
API_TIMEOUT=30000

# Check Python API health
curl http://localhost:8000/health

# Check circuit breaker status
curl http://localhost:3000/stats
```

### Zero Messages Being Processed

**Problem**: No messages are being captured
```bash
# Check if groups are being filtered
# In .env, ensure WATCHED_GROUPS is empty or correct
WATCHED_GROUPS=

# Check WhatsApp connection
curl http://localhost:3000/health

# View logs for errors
pm2 logs whatsapp-scraper --lines 50
```

## Performance Optimization

### For High Message Volume (1000+ messages/minute)

1. **Enable Redis and Bull Queue**:
   ```env
   ENABLE_QUEUE=true
   QUEUE_CONCURRENCY=5
   ```

2. **Increase API timeout**:
   ```env
   API_TIMEOUT=15000
   ```

3. **Use multiple scraper instances**:
   ```bash
   # With Docker
   docker-compose up -d --scale scraper=3
   ```

4. **Monitor metrics**:
   - Check queue size regularly
   - Monitor API latency
   - Watch for circuit breaker openings

### For Low Resource Environments

1. **Disable unnecessary features**:
   ```env
   ENABLE_METRICS=false
   ENABLE_QUEUE=false
   ```

2. **Reduce image quality**:
   ```env
   MAX_IMAGE_SIZE_MB=2
   ```

3. **Use file-based auth**:
   ```env
   USE_FILE_AUTH=true
   ```

## Security Best Practices

1. **Never commit `.env` file**
2. **Rotate API keys regularly**
3. **Use strong admin secrets**
4. **Restrict access to health endpoints in production**
5. **Enable Redis authentication**
6. **Use HTTPS for API calls**
7. **Run containers as non-root user**
8. **Keep dependencies updated**

## Backup and Recovery

### Backup Session Data

```bash
# With Redis
redis-cli SAVE
cp /var/lib/redis/dump.rdb backup/

# With file-based auth
tar -czf backup/auth_$(date +%Y%m%d).tar.gz auth_info_baileys/
```

### Restore Session

```bash
# With Redis
cp backup/dump.rdb /var/lib/redis/
sudo systemctl restart redis-server

# With file-based auth
tar -xzf backup/auth_20240116.tar.gz
```

## Support

For issues, questions, or feature requests:
- GitHub Issues: https://github.com/NickAiNYC/Watchy/issues
- Documentation: README.md

## License

MIT License - See LICENSE file for details
