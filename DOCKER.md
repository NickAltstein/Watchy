# Docker Compose Setup - Watch Trading Platform

Complete local development environment with all services orchestrated via Docker Compose.

## Services Included

1. **PostgreSQL + TimescaleDB** - Time-series optimized database
2. **Redis** - Cache and message queue
3. **FastAPI Backend** - Python API server
4. **Next.js Frontend** - React application
5. **Celery Worker** - Background task processor
6. **Celery Beat** - Task scheduler
7. **Nginx** - Reverse proxy and load balancer
8. **Prometheus** - Metrics collection
9. **Grafana** - Monitoring dashboards

## Quick Start

### 1. Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- 8GB+ RAM recommended

### 2. Setup Environment

```bash
# Copy environment template
cp .env.template .env

# Edit .env and add your API keys
nano .env  # or use your preferred editor
```

**Required Variables:**
- `OPENAI_API_KEY` - Your OpenAI API key
- `DEEPSEEK_API_KEY` - Your DeepSeek API key
- `ADMIN_SECRET` - Admin password (change default!)

### 3. Start All Services

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f backend
```

### 4. Verify Services

```bash
# Check service status
docker-compose ps

# All services should show "Up" and healthy
```

**Service URLs:**
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3001 (admin/admin)
- Nginx: http://localhost

### 5. Initialize Database

```bash
# Database schema is auto-loaded from schema.sql
# Verify it's working
docker-compose exec postgres psql -U watchy -d watchy_trading -c "\dt"

# Optional: Migrate existing data
docker-compose exec backend python migrate_to_postgres.py
```

## Service Management

### Start/Stop Services

```bash
# Start all services
docker-compose up -d

# Start specific services
docker-compose up -d postgres redis backend

# Stop all services
docker-compose down

# Stop and remove volumes (⚠️ deletes all data)
docker-compose down -v
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f celery_worker

# Last 100 lines
docker-compose logs --tail=100 backend
```

### Restart Services

```bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart backend
docker-compose restart nginx
```

### Scale Services

```bash
# Scale workers
docker-compose up -d --scale celery_worker=4

# Scale backend (behind nginx)
docker-compose up -d --scale backend=3
```

## Development Workflow

### Code Changes

The backend and frontend use volume mounts for live reloading:

```bash
# Backend changes are auto-reloaded (uvicorn --reload)
# Frontend changes trigger hot module replacement

# Rebuild after dependency changes
docker-compose up -d --build backend
docker-compose up -d --build frontend
```

### Database Operations

```bash
# Connect to database
docker-compose exec postgres psql -U watchy -d watchy_trading

# Run migrations
docker-compose exec backend python migrate_to_postgres.py

# Backup database
docker-compose exec postgres pg_dump -U watchy watchy_trading > backup.sql

# Restore database
docker-compose exec -T postgres psql -U watchy watchy_trading < backup.sql
```

### Redis Operations

```bash
# Connect to Redis CLI
docker-compose exec redis redis-cli

# View keys
docker-compose exec redis redis-cli KEYS '*'

# Flush cache
docker-compose exec redis redis-cli FLUSHALL
```

### Celery Operations

```bash
# View active tasks
docker-compose exec celery_worker celery -A tasks.celery inspect active

# View scheduled tasks
docker-compose exec celery_beat celery -A tasks.celery inspect scheduled

# Purge queue
docker-compose exec celery_worker celery -A tasks.celery purge
```

## Monitoring

### Prometheus

Access Prometheus at http://localhost:9090

**Useful Queries:**
```promql
# Request rate
rate(http_requests_total[5m])

# Error rate
rate(http_requests_total{status=~"5.."}[5m])

# Response time (95th percentile)
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
```

### Grafana

Access Grafana at http://localhost:3001
- Username: `admin`
- Password: `admin` (change in .env)

**Pre-configured Dashboards:**
- Application metrics
- Database performance
- System resources

### Health Checks

```bash
# Backend health
curl http://localhost:8000/health

# Frontend health
curl http://localhost:3000

# Via Nginx
curl http://localhost/health
```

## Troubleshooting

### Service Won't Start

```bash
# Check logs
docker-compose logs service_name

# Check if port is in use
lsof -i :8000  # or netstat -an | grep 8000

# Remove and recreate
docker-compose down
docker-compose up -d
```

### Database Connection Issues

```bash
# Verify Postgres is healthy
docker-compose ps postgres

# Check logs
docker-compose logs postgres

# Test connection
docker-compose exec backend python -c "import asyncpg; print('OK')"
```

### Out of Memory

```bash
# Check resource usage
docker stats

# Increase Docker memory limit in Docker Desktop settings
# Or adjust resource limits in docker-compose.yml
```

### Permission Issues

```bash
# Fix volume permissions
docker-compose down
sudo chown -R $USER:$USER ./

docker-compose up -d
```

### Reset Everything

```bash
# Stop and remove everything
docker-compose down -v

# Remove images
docker-compose down --rmi all

# Start fresh
docker-compose up -d --build
```

## Production Deployment

### 1. Update Environment

```bash
cp .env.template .env.production

# Update for production:
# - Set DEBUG=false
# - Use strong passwords
# - Set NODE_ENV=production
# - Configure proper CORS_ORIGINS
# - Use HTTPS
```

### 2. Build Production Images

```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml build
```

### 3. Use Secrets Management

Don't store secrets in .env files in production. Use:
- Docker secrets
- AWS Secrets Manager
- HashiCorp Vault
- Kubernetes secrets

### 4. Enable HTTPS

Update nginx configuration with SSL certificates:

```nginx
server {
    listen 443 ssl http2;
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    # ... rest of config
}
```

### 5. Resource Limits

Adjust resource limits in docker-compose.yml based on your hardware.

### 6. Monitoring

- Set up external monitoring (Datadog, New Relic, etc.)
- Configure alerting (PagerDuty, OpsGenie, etc.)
- Enable centralized logging (ELK, Splunk, etc.)

## Maintenance

### Update Images

```bash
# Pull latest images
docker-compose pull

# Recreate containers
docker-compose up -d
```

### Clean Up

```bash
# Remove unused images
docker image prune -a

# Remove unused volumes
docker volume prune

# Remove everything unused
docker system prune -a --volumes
```

### Backup Strategy

**Automated Backups:**

```bash
# Add to crontab
0 2 * * * cd /path/to/project && docker-compose exec -T postgres pg_dump -U watchy watchy_trading | gzip > backup_$(date +\%Y\%m\%d).sql.gz
```

**Restore from Backup:**

```bash
gunzip < backup_20260116.sql.gz | docker-compose exec -T postgres psql -U watchy watchy_trading
```

## Architecture

```
┌─────────────┐
│   Nginx     │  Port 80/443 (Reverse Proxy)
└──────┬──────┘
       │
       ├─────────────────────────┬──────────────────┐
       │                         │                  │
┌──────▼──────┐          ┌──────▼──────┐   ┌──────▼──────┐
│   Frontend  │          │   Backend   │   │ Prometheus  │
│  (Next.js)  │          │  (FastAPI)  │   │             │
│  Port 3000  │          │  Port 8000  │   │  Port 9090  │
└─────────────┘          └──────┬──────┘   └──────┬──────┘
                                │                  │
                    ┌───────────┼──────────────────┘
                    │           │
             ┌──────▼──────┐   │   ┌─────────────┐
             │  PostgreSQL │◄──┼───│   Grafana   │
             │ TimescaleDB │   │   │  Port 3001  │
             │  Port 5432  │   │   └─────────────┘
             └─────────────┘   │
                               │
                    ┌──────────▼──────────┐
                    │       Redis         │
                    │  Cache + Queue      │
                    │     Port 6379       │
                    └──────────┬──────────┘
                               │
                    ┌──────────┴──────────┐
                    │                     │
             ┌──────▼──────┐      ┌──────▼──────┐
             │   Celery    │      │   Celery    │
             │   Worker    │      │    Beat     │
             └─────────────┘      └─────────────┘
```

## Support

For issues:
1. Check logs: `docker-compose logs -f`
2. Verify health: `docker-compose ps`
3. Review documentation above
4. Check GitHub issues

## License

See LICENSE file in repository.
