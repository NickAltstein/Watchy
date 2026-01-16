# Kubernetes Manifests

Production-ready Kubernetes deployment for Watchy Watch Trading Engine.

## Quick Start

```bash
# Automated deployment
./deploy.sh production deploy

# Initialize database
./deploy.sh production init-db

# Check status
./deploy.sh production status
```

## Contents

- **namespace.yaml** - Namespace definition
- **configmap.yaml** - Application configuration
- **secrets.yaml** - Secrets template
- **pvc.yaml** - Persistent storage
- **postgres-deployment.yaml** - PostgreSQL + TimescaleDB
- **redis-deployment.yaml** - Redis cache
- **backend-deployment.yaml** - FastAPI backend (+ HPA)
- **frontend-deployment.yaml** - Next.js frontend (+ HPA)
- **celery-deployment.yaml** - Celery workers (+ HPA)
- **nginx-deployment.yaml** - Nginx reverse proxy
- **ingress.yaml** - Ingress with TLS
- **prometheus-deployment.yaml** - Prometheus monitoring
- **grafana-deployment.yaml** - Grafana dashboards
- **network-policy.yaml** - Network security
- **pod-disruption-budget.yaml** - High availability
- **deploy.sh** - Deployment automation script
- **KUBERNETES.md** - Complete documentation

## Features

✅ **High Availability**
- 3+ replicas for critical services
- Pod anti-affinity rules
- PodDisruptionBudgets

✅ **Auto-Scaling**
- HorizontalPodAutoscaler for backend, frontend, celery
- Resource-based scaling (CPU/Memory)

✅ **Security**
- Network policies
- Non-root containers
- Secrets management
- TLS termination

✅ **Monitoring**
- Prometheus metrics
- Grafana dashboards
- Health checks
- Liveness/Readiness probes

✅ **Zero-Downtime Deployment**
- Rolling updates
- Health checks
- Rollback capability

## Architecture

```
                    ┌─────────────┐
                    │   Ingress   │
                    │  (TLS/SSL)  │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │    Nginx    │
                    │   (3 pods)  │
                    └──┬────────┬─┘
               ┌───────┴────┐   └───────┐
               │            │           │
        ┌──────▼──────┐  ┌─▼────────┐  │
        │  Frontend   │  │ Backend  │  │
        │  (3-10 HPA) │  │(3-10 HPA)│  │
        └─────────────┘  └─┬────────┘  │
                           │           │
                    ┌──────▼──────┐    │
                    │   Redis     │    │
                    │  (3 pods)   │    │
                    └─────────────┘    │
                           │           │
                    ┌──────▼──────┐    │
                    │  PostgreSQL │    │
                    │ TimescaleDB │    │
                    └─────────────┘    │
                           │           │
                    ┌──────▼──────┐    │
                    │   Celery    │    │
                    │ (3-20 HPA)  │◄───┘
                    └─────────────┘
```

## Resource Requirements

**Minimum:**
- 3 nodes
- 16 vCPUs total
- 32GB RAM total
- 100GB storage

**Production:**
- 5-10 nodes
- 32+ vCPUs
- 64+ GB RAM
- 500GB+ SSD storage

## Prerequisites

- Kubernetes 1.24+
- kubectl configured
- Storage classes (`fast-ssd`, `standard`)
- Ingress controller (nginx-ingress)
- Cert-manager (for TLS)

## Documentation

See [KUBERNETES.md](KUBERNETES.md) for complete documentation.

## Support

Report issues or questions in the main repository.
