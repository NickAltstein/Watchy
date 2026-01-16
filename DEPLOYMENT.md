<<<<<<< HEAD
# Deployment Guide

This guide covers various deployment strategies for the Watch Trading Engine in production environments.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Environment Setup](#environment-setup)
- [Deployment Options](#deployment-options)
  - [Docker Compose](#docker-compose)
  - [AWS Deployment](#aws-deployment)
  - [Google Cloud Platform](#google-cloud-platform)
  - [Azure Deployment](#azure-deployment)
  - [Heroku Deployment](#heroku-deployment)
- [SSL/TLS Setup](#ssltls-setup)
- [Monitoring & Logging](#monitoring--logging)
- [Backup Strategy](#backup-strategy)
- [Performance Tuning](#performance-tuning)

## Prerequisites

- Domain name (optional but recommended)
- SSL certificate (Let's Encrypt recommended)
- Server with minimum specifications:
  - 2 CPU cores
  - 4GB RAM
  - 20GB storage
  - Ubuntu 22.04 LTS or similar

## Environment Setup

### 1. Server Preparation

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker and Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verify installation
docker --version
docker-compose --version
```

### 2. Clone Repository

```bash
git clone https://github.com/YOUR_USERNAME/Watchy.git
cd Watchy
```

### 3. Configure Environment

```bash
cp .env.template .env
nano .env  # Edit with your configuration
```

**Important environment variables:**

```bash
# API Keys
OPENAI_API_KEY=sk-your-key-here
DEEPSEEK_API_KEY=sk-your-key-here
ADMIN_SECRET=$(openssl rand -hex 32)

# Production settings
DEBUG=false
LOG_LEVEL=info
DATABASE_URL=trade_desk.db

# Security
CORS_ORIGINS=https://your-domain.com
```

## Deployment Options

### Docker Compose (Recommended for Quick Start)

#### Basic Deployment

```bash
# Build and start services
docker-compose up -d

# View logs
docker-compose logs -f

# Check status
docker-compose ps

# Stop services
docker-compose down
```

#### With Nginx Reverse Proxy

```bash
# Start with nginx profile
docker-compose --profile with-nginx up -d

# This includes:
# - API service on port 8000
# - WhatsApp service
# - Nginx reverse proxy on port 80/443
```

#### With Automated Backups

```bash
# Start with backup profile
docker-compose --profile with-backup up -d

# Backups are stored in ./backups/
# Old backups (>7 days) are automatically deleted
```

#### Production-Ready Stack

```bash
# Start all services
docker-compose --profile with-nginx --profile with-backup up -d
```

### AWS Deployment

#### Option 1: EC2 with Docker

1. **Launch EC2 Instance**
   ```bash
   # Use t3.medium or larger
   # Ubuntu 22.04 LTS AMI
   # Open ports: 22, 80, 443
   ```

2. **Install and Configure**
   ```bash
   ssh ubuntu@your-ec2-ip
   
   # Follow "Server Preparation" steps above
   # Clone repository and configure
   
   docker-compose up -d
   ```

3. **Set Up Elastic IP** (optional)
   - Associate an Elastic IP for stable addressing

#### Option 2: ECS Fargate

1. **Create ECR Repository**
   ```bash
   aws ecr create-repository --repository-name watch-trading-engine
   ```

2. **Build and Push Image**
   ```bash
   # Build
   docker build -t watch-trading-engine .
   
   # Tag
   docker tag watch-trading-engine:latest \
     AWS_ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/watch-trading-engine:latest
   
   # Login to ECR
   aws ecr get-login-password --region REGION | \
     docker login --username AWS --password-stdin \
     AWS_ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com
   
   # Push
   docker push AWS_ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/watch-trading-engine:latest
   ```

3. **Create ECS Cluster and Service**
   - Use AWS Console or CLI to create:
     - ECS Cluster (Fargate)
     - Task Definition
     - Service with desired count
     - Application Load Balancer

4. **Configure Secrets**
   - Use AWS Secrets Manager for API keys
   - Reference in task definition

#### Option 3: Lambda + API Gateway

For serverless deployment (API only):

```python
# Use AWS Lambda with FastAPI adapter
# Note: WhatsApp service requires long-running process
```

### Google Cloud Platform

#### Cloud Run Deployment

1. **Build and Push to GCR**
   ```bash
   # Configure gcloud
   gcloud init
   
   # Build
   gcloud builds submit --tag gcr.io/PROJECT_ID/watch-trading-engine
   ```

2. **Deploy to Cloud Run**
   ```bash
   gcloud run deploy watch-trading-api \
     --image gcr.io/PROJECT_ID/watch-trading-engine \
     --platform managed \
     --region us-central1 \
     --allow-unauthenticated \
     --set-env-vars OPENAI_API_KEY=your-key \
     --memory 2Gi \
     --cpu 2
   ```

#### GCE VM Instance

Similar to EC2 deployment:

```bash
# Create VM
gcloud compute instances create watch-trading \
  --image-family ubuntu-2204-lts \
  --image-project ubuntu-os-cloud \
  --machine-type e2-medium \
  --zone us-central1-a

# SSH and configure
gcloud compute ssh watch-trading --zone us-central1-a
```

### Azure Deployment

#### Azure Container Instances

```bash
# Create resource group
az group create --name watch-trading-rg --location eastus

# Create container
az container create \
  --resource-group watch-trading-rg \
  --name watch-trading-api \
  --image your-registry/watch-trading-engine:latest \
  --dns-name-label watch-trading \
  --ports 8000 \
  --environment-variables OPENAI_API_KEY=your-key \
  --cpu 2 --memory 4
```

#### Azure App Service

```bash
# Create App Service Plan
az appservice plan create \
  --name watch-trading-plan \
  --resource-group watch-trading-rg \
  --is-linux \
  --sku B1

# Create Web App
az webapp create \
  --resource-group watch-trading-rg \
  --plan watch-trading-plan \
  --name watch-trading-api \
  --deployment-container-image-name your-image
```

### Heroku Deployment

1. **Create Heroku App**
   ```bash
   heroku create watch-trading-engine
   ```

2. **Add PostgreSQL Add-on** (optional)
   ```bash
   heroku addons:create heroku-postgresql:hobby-dev
   ```

3. **Set Environment Variables**
   ```bash
   heroku config:set OPENAI_API_KEY=your-key
   heroku config:set DEEPSEEK_API_KEY=your-key
   heroku config:set ADMIN_SECRET=$(openssl rand -hex 32)
   ```

4. **Deploy**
   ```bash
   git push heroku main
   ```

5. **Scale**
   ```bash
   heroku ps:scale web=1
   ```

## SSL/TLS Setup

### Let's Encrypt with Certbot

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# Auto-renewal is configured automatically
# Test renewal
sudo certbot renew --dry-run
```

### Manual Certificate Configuration

If using custom certificates, update `nginx.conf`:

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    
    # ... rest of config
}
```

## Monitoring & Logging

### Prometheus + Grafana

1. **Add monitoring services to docker-compose.yml**:

```yaml
prometheus:
  image: prom/prometheus:latest
  volumes:
    - ./prometheus.yml:/etc/prometheus/prometheus.yml
  ports:
    - "9090:9090"

grafana:
  image: grafana/grafana:latest
  ports:
    - "3000:3000"
  environment:
    - GF_SECURITY_ADMIN_PASSWORD=your-password
```

2. **Configure Prometheus** (`prometheus.yml`):

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'watch-trading-api'
    static_configs:
      - targets: ['api:8000']
```

### Centralized Logging

#### ELK Stack

```yaml
elasticsearch:
  image: elasticsearch:8.5.0
  environment:
    - discovery.type=single-node
  ports:
    - "9200:9200"

kibana:
  image: kibana:8.5.0
  ports:
    - "5601:5601"
  depends_on:
    - elasticsearch

logstash:
  image: logstash:8.5.0
  volumes:
    - ./logstash.conf:/usr/share/logstash/pipeline/logstash.conf
  depends_on:
    - elasticsearch
```

#### Cloud Logging

**AWS CloudWatch:**
```bash
# Install CloudWatch agent
aws configure
```

**Google Cloud Logging:**
```bash
# Logs automatically collected in Cloud Run/GCE
```

**Azure Monitor:**
```bash
# Enable Application Insights
```

## Backup Strategy

### Database Backups

#### Automated Backup Script

```bash
#!/bin/bash
# backup.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups"
DB_FILE="/data/trade_desk.db"

# Create backup
cp "$DB_FILE" "$BACKUP_DIR/trade_desk_$DATE.db"

# Compress
gzip "$BACKUP_DIR/trade_desk_$DATE.db"

# Delete old backups (keep 30 days)
find "$BACKUP_DIR" -name "trade_desk_*.db.gz" -mtime +30 -delete

echo "Backup completed: trade_desk_$DATE.db.gz"
```

#### Cron Schedule

```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * /path/to/backup.sh
```

### Cloud Backup

**AWS S3:**
```bash
aws s3 sync /backups/ s3://your-bucket/backups/
```

**Google Cloud Storage:**
```bash
gsutil -m rsync -r /backups/ gs://your-bucket/backups/
```

**Azure Blob Storage:**
```bash
az storage blob upload-batch \
  -d backups \
  -s /backups/ \
  --account-name youraccount
```

## Performance Tuning

### Database Optimization

```sql
-- Enable WAL mode (already done in code)
PRAGMA journal_mode=WAL;

-- Increase cache size
PRAGMA cache_size=-64000;  -- 64MB

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_timestamp ON trades(timestamp);
CREATE INDEX IF NOT EXISTS idx_ref_score ON trades(ref_number, deal_score);
```

### Python API Optimization

```python
# In main.py, increase worker count
# Start with: uvicorn main:app --workers 4 --host 0.0.0.0 --port 8000
```

### Nginx Optimization

```nginx
# In nginx.conf
worker_processes auto;
worker_connections 1024;

# Enable compression
gzip on;
gzip_types text/plain application/json application/javascript text/css;

# Caching
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=api_cache:10m max_size=100m;
```

### Resource Limits

```yaml
# In docker-compose.yml
services:
  api:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
```

## Health Checks

### Kubernetes Health Probes

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
```

### Docker Health Check

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1
```

## Security Checklist

- [ ] Change all default passwords
- [ ] Use strong ADMIN_SECRET (32+ characters)
- [ ] Enable HTTPS/TLS
- [ ] Configure firewall rules
- [ ] Use environment variables for secrets
- [ ] Enable rate limiting
- [ ] Keep dependencies updated
- [ ] Regular security audits
- [ ] Backup encryption
- [ ] Access logging enabled
- [ ] CORS properly configured

## Troubleshooting

### Common Issues

**Database locked:**
```bash
# Check for WAL mode
sqlite3 trade_desk.db "PRAGMA journal_mode;"
```

**Out of memory:**
```bash
# Check Docker stats
docker stats

# Increase memory limit
docker-compose up -d --scale api=1 --memory="4g"
```

**Connection timeout:**
```bash
# Check network connectivity
docker-compose exec api curl -v http://localhost:8000/health
=======
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
>>>>>>> origin/main
```

## Support

<<<<<<< HEAD
For deployment assistance:
- GitHub Issues: https://github.com/YOUR_USERNAME/Watchy/issues
- Documentation: https://github.com/YOUR_USERNAME/Watchy/wiki
- Community: Discord/Slack (if available)
=======
For issues, questions, or feature requests:
- GitHub Issues: https://github.com/NickAiNYC/Watchy/issues
- Documentation: README.md

## License

MIT License - See LICENSE file for details
>>>>>>> origin/main
