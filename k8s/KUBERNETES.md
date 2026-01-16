# Kubernetes Deployment Guide

Complete Kubernetes deployment for the Watchy Watch Trading Engine with high availability, auto-scaling, and production-ready configuration.

## Architecture

### Components

**Infrastructure (3 services):**
- PostgreSQL + TimescaleDB (1 replica, StatefulSet recommended)
- Redis (3 replicas for HA)
- Nginx (3 replicas, LoadBalancer)

**Application (5 services):**
- Backend API (3-10 replicas, HPA enabled)
- Frontend (3-10 replicas, HPA enabled)
- Celery Worker (3-20 replicas, HPA enabled)
- Celery Beat (1 replica, scheduler)
- Prometheus (1 replica, monitoring)
- Grafana (1 replica, dashboards)

**Total:** 9 services with auto-scaling and high availability

### Resource Requirements

**Minimum cluster size:**
- 3 nodes (for HA)
- 16 vCPUs total
- 32GB RAM total
- 100GB storage

**Recommended production:**
- 5-10 nodes
- 32+ vCPUs
- 64+ GB RAM
- 500GB+ storage with SSD

## Quick Start

### Automated Deployment

```bash
# Deploy everything
cd k8s
./deploy.sh production deploy

# Initialize database
./deploy.sh production init-db

# Check status
./deploy.sh production status
```

### Manual Deployment

See detailed steps in sections below.

## Prerequisites

1. **Kubernetes cluster** (v1.24+)
2. **kubectl** configured
3. **Storage classes** configured (`fast-ssd`, `standard`)
4. **Ingress controller** (nginx-ingress)
5. **Cert-manager** (for TLS)
6. **Prometheus Operator** (optional, for ServiceMonitor)

## Configuration Files

| File | Description |
|------|-------------|
| `namespace.yaml` | Namespace definition |
| `configmap.yaml` | Application configuration |
| `secrets.yaml` | Secrets template (DON'T commit with real values) |
| `pvc.yaml` | Persistent volume claims |
| `postgres-deployment.yaml` | PostgreSQL + TimescaleDB |
| `redis-deployment.yaml` | Redis cache/queue |
| `backend-deployment.yaml` | FastAPI backend with HPA |
| `frontend-deployment.yaml` | Next.js frontend with HPA |
| `celery-deployment.yaml` | Celery worker + beat with HPA |
| `nginx-deployment.yaml` | Nginx reverse proxy |
| `ingress.yaml` | Ingress with TLS |
| `prometheus-deployment.yaml` | Prometheus monitoring |
| `grafana-deployment.yaml` | Grafana dashboards |
| `network-policy.yaml` | Network security policies |
| `pod-disruption-budget.yaml` | PDB for high availability |
| `deploy.sh` | Automated deployment script |
| `KUBERNETES.md` | This documentation |

## Deployment Steps

### 1. Create Secrets

```bash
kubectl create secret generic watchy-secrets \
  --from-literal=POSTGRES_USER=watchy_user \
  --from-literal=POSTGRES_PASSWORD=$(openssl rand -base64 32) \
  --from-literal=REDIS_PASSWORD=$(openssl rand -base64 32) \
  --from-literal=SECRET_KEY=$(openssl rand -base64 64) \
  --from-literal=JWT_SECRET_KEY=$(openssl rand -base64 64) \
  -n watchy
```

### 2. Deploy Infrastructure

```bash
kubectl apply -f namespace.yaml
kubectl apply -f configmap.yaml
kubectl apply -f pvc.yaml
kubectl apply -f postgres-deployment.yaml
kubectl apply -f redis-deployment.yaml
```

### 3. Deploy Application

```bash
kubectl apply -f backend-deployment.yaml
kubectl apply -f frontend-deployment.yaml
kubectl apply -f celery-deployment.yaml
kubectl apply -f nginx-deployment.yaml
```

### 4. Deploy Monitoring & Networking

```bash
kubectl apply -f prometheus-deployment.yaml
kubectl apply -f grafana-deployment.yaml
kubectl apply -f ingress.yaml
kubectl apply -f network-policy.yaml
kubectl apply -f pod-disruption-budget.yaml
```

### 5. Initialize Database

```bash
POSTGRES_POD=$(kubectl get pod -n watchy -l app.kubernetes.io/component=postgres -o jsonpath='{.items[0].metadata.name}')
kubectl cp ../schema.sql watchy/$POSTGRES_POD:/tmp/schema.sql
kubectl exec -n watchy $POSTGRES_POD -- psql -U watchy_user -d watchy_trading -f /tmp/schema.sql
```

## Access Services

### Port Forwarding (Local Development)

```bash
# Frontend
kubectl port-forward -n watchy svc/frontend-service 3000:3000

# Backend
kubectl port-forward -n watchy svc/backend-service 8000:8000

# Prometheus
kubectl port-forward -n watchy svc/prometheus-service 9090:9090

# Grafana
kubectl port-forward -n watchy svc/grafana-service 3001:3000
```

### Via Ingress (Production)

- Frontend: `https://yourdomain.com`
- Backend API: `https://api.yourdomain.com`

## Scaling

### Manual Scaling

```bash
kubectl scale deployment backend -n watchy --replicas=5
kubectl scale deployment celery-worker -n watchy --replicas=10
```

### Auto-Scaling

HPA is pre-configured for backend, frontend, and celery-worker.

```bash
# View HPA status
kubectl get hpa -n watchy
```

## Monitoring

### Prometheus

```bash
kubectl port-forward -n watchy svc/prometheus-service 9090:9090
```

Open: http://localhost:9090

### Grafana

```bash
kubectl port-forward -n watchy svc/grafana-service 3001:3000
```

Open: http://localhost:3001 (admin/admin)

### Logs

```bash
kubectl logs -n watchy deployment/backend --tail=100 -f
kubectl logs -n watchy deployment/celery-worker --tail=100 -f
```

## Updates

### Rolling Update

```bash
kubectl set image deployment/backend backend=watchy/backend:v2.0.0 -n watchy
kubectl rollout status deployment/backend -n watchy
```

### Rollback

```bash
kubectl rollout undo deployment/backend -n watchy
```

## Backup

### Database Backup

```bash
POSTGRES_POD=$(kubectl get pod -n watchy -l app.kubernetes.io/component=postgres -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n watchy $POSTGRES_POD -- pg_dump -U watchy_user watchy_trading | gzip > backup-$(date +%Y%m%d).sql.gz
```

### Database Restore

```bash
gunzip < backup-20240115.sql.gz | kubectl exec -i -n watchy $POSTGRES_POD -- psql -U watchy_user watchy_trading
```

## Troubleshooting

### Check Pod Status

```bash
kubectl get pods -n watchy
kubectl describe pod <POD_NAME> -n watchy
kubectl logs <POD_NAME> -n watchy
```

### Check Events

```bash
kubectl get events -n watchy --sort-by='.lastTimestamp'
```

### Test Database Connection

```bash
kubectl exec -n watchy deployment/backend -- nc -zv postgres-service 5432
```

### Resource Usage

```bash
kubectl top pods -n watchy
kubectl top nodes
```

## Security

- Network policies restrict pod communication
- Secrets stored in Kubernetes secrets (use external secret manager in production)
- Non-root containers
- Resource limits prevent resource exhaustion
- PodDisruptionBudgets ensure availability during updates

## Production Checklist

- [ ] Secrets configured (not defaults)
- [ ] TLS certificates installed
- [ ] Custom domain in Ingress
- [ ] Resource limits appropriate
- [ ] HPA tested
- [ ] PodDisruptionBudgets in place
- [ ] Network policies applied
- [ ] Backup strategy implemented
- [ ] Monitoring configured
- [ ] Health checks verified
- [ ] Zero-downtime deployment tested

## Cleanup

```bash
# Delete all resources
./deploy.sh production delete

# Or manually
kubectl delete namespace watchy
```

## Support

For issues:
1. Check logs: `kubectl logs -n watchy deployment/<service>`
2. Check events: `kubectl get events -n watchy`
3. Review documentation

## License

MIT License
