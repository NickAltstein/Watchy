# Grafana Dashboards

This directory contains pre-configured Grafana dashboards that are automatically loaded when the Grafana service starts.

## Available Dashboards

### Watchy System Monitoring (`watchy-system-monitoring.json`)

Comprehensive monitoring dashboard for the Watch Trading Platform with 10 key panels and 6 alert rules.

**Panels:**

1. **Request Rate (req/sec)** - HTTP request rate by method and path
2. **Response Time (p50, p95, p99)** - Response time percentiles with threshold indicators
3. **Error Rate (%)** - 5xx error rate as percentage of total requests
4. **Active WebSocket Connections** - Real-time WebSocket connection count
5. **Database Query Performance** - Average query duration by operation type
6. **Cache Hit Rate** - Redis cache hit percentage
7. **Celery Queue Depth** - Number of pending background tasks
8. **WhatsApp Messages Processed** - Message processing rate by source
9. **AI API Costs ($/hour)** - Hourly API costs by provider
10. **Deal Score Distribution** - Pie chart showing distribution across URGENT/PUSH/NORMAL/SKIP/OVERPRICED tiers

**Alert Rules (configured in `prometheus/alerts.yml`):**

- ⚠️ **Error Rate > 1%** - Triggers when 5xx error rate exceeds 1% for 5 minutes
- ⚠️ **Response Time p95 > 500ms** - Triggers when 95th percentile exceeds 500ms for 5 minutes
- ⚠️ **Queue Depth > 5000** - Triggers when Celery queue has more than 5000 pending tasks
- ⚠️ **Database Connections > 80%** - Triggers when connection pool usage exceeds 80%
- ⚠️ **API Costs > $100/hour** - Triggers when AI API costs exceed $100/hour
- ⚠️ **No Messages Received in 5 minutes** - Triggers when no WhatsApp messages processed

## Usage

### Docker Compose

The dashboard is automatically loaded when you start Grafana with Docker Compose:

```bash
docker-compose up -d grafana
```

Access Grafana at http://localhost:3001 (default credentials: admin/admin)

### Kubernetes

The dashboard is automatically loaded when you deploy Grafana to Kubernetes:

```bash
kubectl apply -f k8s/grafana-deployment.yaml
```

Port-forward to access: `kubectl port-forward svc/grafana 3000:3000 -n watchy`

### Manual Import

If you need to manually import the dashboard:

1. Navigate to Grafana UI
2. Go to Dashboards → Import
3. Upload `watchy-system-monitoring.json`
4. Select the Prometheus datasource
5. Click Import

## Customization

To customize the dashboard:

1. Edit the dashboard in the Grafana UI
2. Export the updated JSON
3. Replace the file in this directory
4. Restart Grafana to apply changes

### Adding New Panels

To add metrics for new features:

1. Ensure your backend exports the metrics to the `/metrics` endpoint
2. Configure Prometheus to scrape the metrics (see `prometheus/prometheus.yml`)
3. Add the new panel to the dashboard JSON or via the Grafana UI
4. Export and save the updated dashboard

## Metrics Requirements

The dashboard expects the following Prometheus metrics to be available:

**HTTP Metrics:**
- `http_requests_total` - Counter with labels: `method`, `path`, `status`
- `http_request_duration_seconds_bucket` - Histogram for response times

**WebSocket Metrics:**
- `websocket_connections_active` - Gauge for active connections

**Database Metrics:**
- `database_query_duration_seconds_sum` - Counter for total query time
- `database_query_duration_seconds_count` - Counter for query count
- `pg_stat_database_numbackends` - Gauge for active connections
- `pg_settings_max_connections` - Gauge for max connections

**Cache Metrics:**
- `cache_hits` - Counter for cache hits
- `cache_misses` - Counter for cache misses

**Celery Metrics:**
- `celery_queue_length` - Gauge for queue depth

**Application Metrics:**
- `whatsapp_messages_processed_total` - Counter with label: `source`
- `ai_api_cost_total` - Counter with label: `provider`
- `deal_score_distribution` - Gauge with label: `tier`

## Troubleshooting

**Dashboard shows "No data":**
- Verify Prometheus is scraping metrics: http://localhost:9090/targets
- Check that your backend is exporting metrics: http://localhost:8000/metrics
- Ensure the Prometheus datasource is configured correctly in Grafana

**Panels show incorrect data:**
- Verify the metric names match your backend implementation
- Check the time range selector (top right)
- Review query syntax in panel edit mode

**Alerts not firing:**
- Verify alert rules in Prometheus: http://localhost:9090/alerts
- Check alert configuration in `prometheus/alerts.yml`
- Ensure metrics are being collected correctly

## Dashboard Refresh

The dashboard auto-refreshes every 30 seconds. You can change this in the dashboard settings (top right gear icon).

Time range options: 6h (default), 12h, 24h, 7d, 30d

## References

- [Grafana Documentation](https://grafana.com/docs/)
- [Prometheus Query Language](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Dashboard Best Practices](https://grafana.com/docs/grafana/latest/best-practices/)
