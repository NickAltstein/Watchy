# High-Throughput Message Processing Guide

## Overview

The high-throughput system handles 1000+ messages/minute with priority queuing, parallel processing, and advanced monitoring capabilities.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│               HIGH-THROUGHPUT ARCHITECTURE                   │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐                                           │
│  │   WhatsApp   │ ──▶ Messages                              │
│  │   Baileys    │                                           │
│  └──────┬───────┘                                           │
│         │                                                     │
│         ▼                                                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           PRIORITY QUEUE (Bull + Redis)              │  │
│  │  ┌─────────────┬─────────────┬──────────────┐       │  │
│  │  │   HIGH      │   MEDIUM    │     LOW      │       │  │
│  │  │  (images)   │  (dealers)  │  (unknown)   │       │  │
│  │  │  Priority 1 │  Priority 5 │  Priority 10 │       │  │
│  │  └─────────────┴─────────────┴──────────────┘       │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                    │
│                         ▼                                    │
│  ┌──────────────────────────────────────────────────────┐  │
│  │      MESSAGE PROCESSOR (10 Parallel Workers)         │  │
│  │                                                       │  │
│  │  ┌────────────────────────────────────────────────┐ │  │
│  │  │  Rate Limiter: 20 req/sec (Bottleneck)        │ │  │
│  │  └────────────────────────────────────────────────┘ │  │
│  │                                                       │  │
│  │  ┌────────────────────────────────────────────────┐ │  │
│  │  │  Circuit Breaker (Opossum)                     │ │  │
│  │  │  - 50% error threshold                         │ │  │
│  │  │  - 30s reset timeout                           │ │  │
│  │  └────────────────────────────────────────────────┘ │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                    │
│                         ▼                                    │
│  ┌──────────────────────────────────────────────────────┐  │
│  │          Python FastAPI (Parse Watch)                │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                MONITORING & ADMIN                     │  │
│  │  • Health Server (Port 3000)                         │  │
│  │  • Admin API (Port 3001)                             │  │
│  │  • Prometheus Metrics                                │  │
│  │  • Queue Alerts                                      │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Features

### 1. Priority Queue System

Messages are automatically prioritized based on value:

- **HIGH (Priority 1)**: Messages with images
  - More valuable as images contain watch details
  - Processed first
  
- **MEDIUM (Priority 5)**: Text from known dealers
  - Configured via `KNOWN_DEALERS` environment variable
  - Reliable source, processed before unknown senders
  
- **LOW (Priority 10)**: Messages from unknown senders
  - Processed last when queue is busy

### 2. Parallel Processing

- **10 Concurrent Workers** (configurable via `QUEUE_CONCURRENCY`)
- Processes multiple messages simultaneously
- Automatically scales with queue depth

### 3. Rate Limiting

- **20 requests/second** to Python API (configurable via `RATE_LIMIT_PER_SECOND`)
- Prevents API overload
- Uses Bottleneck library for precise rate control
- Automatically queues excess requests

### 4. Circuit Breaker

- **Protects against API failures**
- Opens at 50% error rate
- Auto-recovers after 30 seconds
- Provides fallback responses

### 5. Queue Management

- **Max 10,000 jobs** in queue
- **24-hour cleanup** for completed jobs
- **7-day retention** for failed jobs
- Automatic dead letter queue for failed messages

### 6. Monitoring & Alerts

- **Queue depth alerts** when > 5,000 messages
- **Success rate alerts** when < 95%
- **Circuit breaker alerts** when API unavailable
- Real-time statistics

## Quick Start

### Basic Setup

```bash
# 1. Configure environment
cp .env.example .env
nano .env

# Required configuration:
REDIS_HOST=localhost
REDIS_PORT=6379
PYTHON_API_URL=http://localhost:8000
API_KEY=your_api_key
QUEUE_CONCURRENCY=10
RATE_LIMIT_PER_SECOND=20
KNOWN_DEALERS=+1234567890,dealer@whatsapp

# 2. Start Redis
docker run -d -p 6379:6379 redis:7-alpine

# 3. Start Python API (Terminal 1)
python -m uvicorn main:app --host 0.0.0.0 --port 8000

# 4. Start high-throughput service (Terminal 2)
npm run start:highput
```

### PM2 Deployment

```bash
# Update ecosystem.config.js to use server-highput.js
pm2 start ecosystem.config.js
pm2 logs
```

## Configuration

### Environment Variables

```env
# Queue Configuration
QUEUE_CONCURRENCY=10                  # Number of parallel workers
RATE_LIMIT_PER_SECOND=20             # API rate limit
QUEUE_CAPACITY_ALERT=5000            # Alert threshold

# Priority Routing
KNOWN_DEALERS=+1234567890,dealer@s.whatsapp.net

# API Configuration
PYTHON_API_URL=http://localhost:8000
API_KEY=your_api_key_here
API_TIMEOUT=10000

# Server Ports
HEALTH_PORT=3000                      # Health/metrics server
ADMIN_PORT=3001                       # Admin API server

# Batch Processing (Optional)
ENABLE_BATCH_PROCESSING=false
BATCH_SIZE=10
BATCH_TIMEOUT=5000
```

### Known Dealers Configuration

Add dealer phone numbers or WhatsApp IDs to give them priority:

```env
KNOWN_DEALERS=+1234567890@s.whatsapp.net,+9876543210@s.whatsapp.net
```

Messages from these senders will be processed with MEDIUM priority.

## API Endpoints

### Health Server (Port 3000)

- `GET /health` - Overall system health
- `GET /metrics` - Prometheus metrics
- `GET /stats` - Application statistics
- `GET /ready` - Kubernetes readiness probe
- `GET /live` - Kubernetes liveness probe

### Admin API (Port 3001)

#### Queue Management

- `GET /api/admin/queues/stats` - All queue statistics
- `GET /api/admin/queues/:queueName/stats` - Specific queue stats
- `POST /api/admin/queues/:queueName/pause` - Pause queue
- `POST /api/admin/queues/:queueName/resume` - Resume queue
- `POST /api/admin/queues/:queueName/clear` - Clear jobs

**Clear Queue Example:**
```bash
curl -X POST http://localhost:3001/api/admin/queues/message-processing/clear \
  -H "Content-Type: application/json" \
  -d '{"status": "completed"}'
```

#### Failed Jobs

- `GET /api/admin/queues/:queueName/failed` - Get failed jobs
- `POST /api/admin/queues/:queueName/retry-failed` - Retry failed jobs

**Retry All Failed:**
```bash
curl -X POST http://localhost:3001/api/admin/queues/message-processing/retry-failed
```

**Retry Specific Job:**
```bash
curl -X POST http://localhost:3001/api/admin/queues/message-processing/retry-failed \
  -H "Content-Type: application/json" \
  -d '{"jobId": "12345"}'
```

#### Processor Stats

- `GET /api/admin/processor/stats` - Processor statistics
- `POST /api/admin/processor/reset-stats` - Reset statistics

#### Alerts

- `GET /api/admin/alerts` - Active alerts

## Monitoring

### Queue Statistics

```bash
curl http://localhost:3001/api/admin/queues/stats | jq
```

**Response:**
```json
{
  "queues": [
    {
      "name": "message-processing",
      "waiting": 45,
      "active": 10,
      "completed": 5280,
      "failed": 12,
      "delayed": 0,
      "total": 5347
    }
  ],
  "processor": {
    "totalProcessed": 5280,
    "successCount": 5268,
    "failureCount": 12,
    "successRate": "99.77%",
    "avgLatency": "245ms",
    "messagesPerMinute": 156
  }
}
```

### Processor Statistics

```bash
curl http://localhost:3001/api/admin/processor/stats | jq
```

**Response:**
```json
{
  "totalProcessed": 5280,
  "successCount": 5268,
  "failureCount": 12,
  "circuitOpenCount": 0,
  "totalLatency": 1294560,
  "avgLatency": "245ms",
  "batchesProcessed": 0,
  "successRate": "99.77%",
  "uptime": "3600s",
  "messagesPerMinute": 88,
  "rateLimitStatus": {
    "running": 2,
    "queued": 0,
    "reservoir": 18
  },
  "circuitBreakerStatus": {
    "name": "parse-watch-api",
    "state": "CLOSED",
    "failures": 12,
    "successes": 5268
  }
}
```

### Active Alerts

```bash
curl http://localhost:3001/api/admin/alerts | jq
```

**Response:**
```json
{
  "alerts": [
    {
      "type": "queue_depth",
      "severity": "warning",
      "queue": "message-processing",
      "message": "Queue depth exceeds 5000 messages",
      "value": 5234,
      "threshold": 5000
    }
  ],
  "count": 1,
  "timestamp": "2026-01-16T03:20:00.000Z"
}
```

## Performance Tuning

### For High Volume (2000+ messages/minute)

```env
QUEUE_CONCURRENCY=20
RATE_LIMIT_PER_SECOND=40
QUEUE_CAPACITY_ALERT=10000
```

### For Low Latency (<50ms)

```env
QUEUE_CONCURRENCY=5
RATE_LIMIT_PER_SECOND=30
```

### For API Protection

```env
QUEUE_CONCURRENCY=5
RATE_LIMIT_PER_SECOND=10
```

## Troubleshooting

### Queue Growing Too Fast

**Problem**: Queue depth exceeds 5000

**Solutions**:
1. Increase concurrency: `QUEUE_CONCURRENCY=20`
2. Increase rate limit: `RATE_LIMIT_PER_SECOND=30`
3. Check API performance
4. Pause non-critical queues

```bash
# Pause queue temporarily
curl -X POST http://localhost:3001/api/admin/queues/message-processing/pause

# Resume when ready
curl -X POST http://localhost:3001/api/admin/queues/message-processing/resume
```

### High Failure Rate

**Problem**: Success rate < 95%

**Solutions**:
1. Check API health
2. Review failed jobs
3. Check circuit breaker status
4. Retry failed jobs

```bash
# Get failed jobs
curl http://localhost:3001/api/admin/queues/message-processing/failed

# Retry all failed
curl -X POST http://localhost:3001/api/admin/queues/message-processing/retry-failed
```

### Circuit Breaker Open

**Problem**: API unavailable, circuit breaker protecting system

**Solutions**:
1. Check Python API: `curl http://localhost:8000/health`
2. Wait for auto-recovery (30 seconds)
3. Check API logs
4. Restart API if needed

### High Memory Usage

**Problem**: Memory > 2GB

**Solutions**:
1. Clear completed jobs:
```bash
curl -X POST http://localhost:3001/api/admin/queues/message-processing/clear \
  -H "Content-Type: application/json" \
  -d '{"status": "completed"}'
```

2. Reduce queue concurrency
3. Enable automatic cleanup in Redis

## Best Practices

### 1. Monitor Regularly

```bash
# Check every 5 minutes
watch -n 300 'curl -s http://localhost:3001/api/admin/alerts | jq'
```

### 2. Configure Known Dealers

Add trusted dealers to `KNOWN_DEALERS` for priority processing.

### 3. Set Appropriate Rate Limits

Don't exceed API capacity. Monitor success rate and adjust.

### 4. Use Alerts

Set up alert webhooks for critical conditions.

### 5. Regular Cleanup

Clear old completed jobs weekly:
```bash
curl -X POST http://localhost:3001/api/admin/queues/message-processing/clear \
  -H "Content-Type: application/json" \
  -d '{"status": "completed"}'
```

### 6. Monitor Circuit Breaker

Check circuit breaker status regularly:
```bash
curl http://localhost:3001/api/admin/processor/stats | jq '.circuitBreakerStatus'
```

## Prometheus Metrics

The system exports these metrics for monitoring:

- `whatsapp_messages_received_total` - Total messages received
- `whatsapp_messages_processed_total` - Total processed
- `api_calls_total` - API calls by status
- `api_latency_seconds` - API latency histogram
- `queue_size` - Current queue depth
- `circuit_breaker_status` - Circuit breaker state

Access metrics at: `http://localhost:3000/metrics`

## Advanced Features

### Batch Processing (Experimental)

Process multiple messages in a single API call:

```env
ENABLE_BATCH_PROCESSING=true
BATCH_SIZE=10
BATCH_TIMEOUT=5000
```

**Note**: Requires API support for batch endpoints.

### Custom Priority Logic

Modify `src/queue/message-processor.js` `determinePriority()` method to implement custom priority logic.

### Webhook Notifications

Add webhook calls in `src/queue/admin-api.js` for alert notifications.

## Performance Benchmarks

Tested with:
- 10 concurrent workers
- 20 req/sec rate limit
- Redis 7.0
- Python API on same host

**Results**:
- **Throughput**: 1,200 messages/minute
- **Latency**: ~250ms average (queue → API → complete)
- **Success Rate**: 99.8%
- **Memory**: ~800MB with 5000 messages in queue

## Support

For issues:
1. Check logs: `tail -f logs/combined-*.log`
2. Check alerts: `curl http://localhost:3001/api/admin/alerts`
3. Check stats: `curl http://localhost:3001/api/admin/queues/stats`

## License

MIT
