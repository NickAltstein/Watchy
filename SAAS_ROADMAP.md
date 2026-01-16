# SaaS Platform Transformation Roadmap

## Executive Summary

This document outlines the transformation of the Watch Trading Engine from a production-ready backend infrastructure into a **scalable, multi-tenant SaaS platform** suitable for paying customers (dealers, brokers, collectors).

**Current State (After This PR):**
- ✅ Production-ready backend infrastructure  
- ✅ PostgreSQL + TimescaleDB database
- ✅ Deal scoring engine with ML predictions
- ✅ Docker Compose + Kubernetes deployment
- ✅ Monitoring with Grafana/Prometheus
- ✅ 59 passing tests, 2,600+ lines documentation

**Target State:**
A venture-backable SaaS platform with:
- Multi-tenant architecture
- Modern web dashboard (React/Next.js)
- Authentication & authorization (JWT, API keys)
- Subscription management
- Enhanced AI pipeline
- CI/CD automation
- Mobile-responsive interface

---

## Phase 1: Monorepo Restructure & Multi-Tenancy (Weeks 1-3)

### Objective
Refactor codebase into a clean monorepo structure with multi-tenant database architecture.

### Deliverables

#### 1.1 Monorepo Structure
```
watchy/
├── apps/
│   ├── ingest-service/          # Node.js WhatsApp ingestion (Baileys)
│   ├── api-service/             # Python FastAPI backend
│   └── web/                     # React/Next.js dashboard
├── packages/
│   ├── shared-types/            # TypeScript type definitions
│   ├── scoring-engine/          # Deal scoring logic (Python)
│   └── database/                # SQLAlchemy models, migrations
├── infra/
│   ├── docker/
│   ├── k8s/                     # Kubernetes manifests
│   └── ci/                      # GitHub Actions workflows
└── docs/
```

#### 1.2 Multi-Tenant Database Schema
```sql
-- New tables for multi-tenancy
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    subscription_tier VARCHAR(50) DEFAULT 'free',
    max_users INTEGER DEFAULT 5,
    max_alerts INTEGER DEFAULT 10,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    organization_id UUID REFERENCES organizations(id),
    role VARCHAR(50) DEFAULT 'user',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Add organization_id to existing tables
ALTER TABLE trades ADD COLUMN organization_id UUID REFERENCES organizations(id);
ALTER TABLE alerts ADD COLUMN organization_id UUID REFERENCES organizations(id);
```

### Tasks
- [ ] Restructure repository into monorepo format
- [ ] Migrate existing code to new structure
- [ ] Create multi-tenant database schema
- [ ] Implement Alembic migrations
- [ ] Add organization/user SQLAlchemy models
- [ ] Update docker-compose.yml for new structure
- [ ] Write migration guide documentation

### Success Metrics
- All services run independently
- Database migrations execute successfully
- Existing functionality preserved
- Zero downtime migration path documented

---

## Phase 2: Authentication & Authorization (Weeks 4-5)

### Objective
Implement secure JWT-based authentication with role-based access control.

### Deliverables

#### 2.1 Authentication Endpoints
```python
POST   /auth/register          # Create new user account
POST   /auth/login             # Login with email/password
POST   /auth/refresh           # Refresh access token
POST   /auth/logout            # Revoke refresh token
GET    /auth/me                # Get current user info

# API Key management
GET    /api-keys               # List user's API keys
POST   /api-keys               # Create new API key
DELETE /api-keys/:id           # Revoke API key
```

#### 2.2 Role-Based Access Control
```python
ROLES = {
    'viewer': ['read'],
    'user': ['read', 'create', 'update_own'],
    'admin': ['read', 'create', 'update', 'delete', 'manage_users'],
    'super_admin': ['*']
}
```

### Tasks
- [ ] Implement JWT token generation/validation
- [ ] Create authentication endpoints
- [ ] Add password hashing (bcrypt)
- [ ] Implement API key system
- [ ] Add role-based access control middleware
- [ ] Create user management endpoints
- [ ] Write authentication tests
- [ ] Document API authentication

### Success Metrics
- Users can register and login
- JWT tokens expire and refresh properly
- API keys work for programmatic access
- Role-based permissions enforced

---

## Phase 3: Production-Ready API Layer (Weeks 6-7)

### Objective
Build comprehensive RESTful API with full CRUD operations for all resources.

### Deliverables

#### 3.1 Core API Endpoints
```python
# Listings
GET    /listings                    # List all listings (paginated, filtered)
POST   /listings                    # Create new listing
GET    /listings/:id                # Get listing details
PUT    /listings/:id                # Update listing
DELETE /listings/:id                # Delete listing

# Alerts
GET    /alerts                      # List user's alerts
POST   /alerts                      # Create alert
PUT    /alerts/:id                  # Update alert
DELETE /alerts/:id                  # Delete alert

# Analytics
GET    /analytics/dashboard         # Dashboard summary stats
GET    /analytics/deals             # Deal distribution over time
GET    /analytics/brands            # Brand statistics
```

### Tasks
- [ ] Implement all CRUD endpoints
- [ ] Add pagination, filtering, sorting
- [ ] Implement batch operations
- [ ] Add export functionality (CSV, JSON, Excel)
- [ ] Create OpenAPI/Swagger documentation
- [ ] Write integration tests for all endpoints
- [ ] Generate API client SDKs

### Success Metrics
- All endpoints documented in Swagger
- Response times < 200ms for GET requests
- 100% test coverage for API layer

---

## Phase 4: Web Dashboard (Weeks 8-10)

### Objective
Build modern, responsive web dashboard with React/Next.js.

### Deliverables

#### 4.1 Dashboard Pages
```
apps/web/src/
├── pages/
│   ├── index.tsx              # Dashboard home
│   ├── login.tsx              # Login page
│   ├── listings/
│   │   ├── index.tsx          # Listings table
│   │   └── [id].tsx           # Listing details
│   ├── alerts/
│   ├── analytics/
│   ├── settings/
│   └── admin/
├── components/
│   ├── ListingCard.tsx
│   ├── PriceChart.tsx
│   ├── FilterPanel.tsx
│   └── DataTable.tsx
```

### Tasks
- [ ] Set up Next.js 14 with TypeScript
- [ ] Implement authentication pages
- [ ] Build dashboard home page
- [ ] Create listings table with filters
- [ ] Build alert management UI
- [ ] Create analytics dashboard
- [ ] Add dark mode support
- [ ] Make fully mobile-responsive
- [ ] Write E2E tests (Playwright)

### Success Metrics
- < 3s initial page load
- 95+ Lighthouse score
- Mobile-responsive on all pages

---

## Phase 5: Enhanced AI Pipeline (Weeks 11-12)

### Objective
Improve AI parsing robustness with validation, retry logic, and confidence scoring.

### Deliverables

#### 5.1 Structured AI Output
```python
from pydantic import BaseModel, Field

class ParsedListing(BaseModel):
    reference: str
    brand: Optional[str]
    price: Optional[int]
    condition: Optional[str]
    confidence_reference: float
    confidence_price: float
    overall_confidence: float
```

### Tasks
- [ ] Create Pydantic schemas for AI output
- [ ] Implement retry logic with tenacity
- [ ] Add confidence scoring for each field
- [ ] Build validation layer
- [ ] Add fallback to cheaper models
- [ ] Implement caching for duplicates
- [ ] Write comprehensive tests

### Success Metrics
- > 95% successful parse rate
- < $0.02 average cost per parse
- < 3s average parse time

---

## Phase 6: CI/CD & Testing (Weeks 13-14)

### Objective
Implement comprehensive testing and continuous integration/deployment.

### Deliverables

#### 6.1 GitHub Actions Workflows
```yaml
# .github/workflows/ci.yml
name: CI/CD Pipeline

jobs:
  lint:
    # Lint code
  test-api:
    # Run API tests
  test-web:
    # Run web tests
  build-and-push:
    # Build Docker images
  deploy-production:
    # Deploy to production
```

### Tasks
- [ ] Set up GitHub Actions workflows
- [ ] Write unit tests for all endpoints
- [ ] Add integration tests
- [ ] Write E2E tests (Playwright)
- [ ] Set up code coverage reporting
- [ ] Add automated Docker builds
- [ ] Implement staging/production deployment
- [ ] Set up error tracking (Sentry)

### Success Metrics
- > 80% code coverage
- < 10 min CI pipeline duration
- Zero failed deployments

---

## Phase 7: Subscription & Billing (Weeks 15-16)

### Objective
Integrate payment processing and subscription management.

### Deliverables

#### 7.1 Subscription Plans
```python
SUBSCRIPTION_PLANS = {
    "free": {
        "price": 0,
        "max_users": 1,
        "max_alerts": 5,
        "features": ["Basic deal scoring", "Price history"]
    },
    "pro": {
        "price": 49,
        "max_users": 5,
        "max_alerts": 50,
        "features": ["API access", "Advanced filters"]
    },
    "team": {
        "price": 149,
        "max_users": 20,
        "max_alerts": 200,
        "features": ["Multi-user", "Priority support"]
    }
}
```

### Tasks
- [ ] Integrate Stripe SDK
- [ ] Create subscription plans
- [ ] Build checkout flow
- [ ] Implement webhook handlers
- [ ] Add usage tracking
- [ ] Enforce subscription limits
- [ ] Build billing settings page
- [ ] Test subscription lifecycle

### Success Metrics
- Checkout conversion > 80%
- Zero failed payments
- Instant activation

---

## Implementation Timeline

| Phase | Duration | Effort | Dependencies |
|-------|----------|--------|--------------|
| Phase 1: Monorepo & Multi-Tenancy | 3 weeks | High | None |
| Phase 2: Authentication | 2 weeks | Medium | Phase 1 |
| Phase 3: API Layer | 2 weeks | Medium | Phase 2 |
| Phase 4: Web Dashboard | 3 weeks | High | Phase 3 |
| Phase 5: Enhanced AI Pipeline | 2 weeks | Medium | Phase 1 |
| Phase 6: CI/CD & Testing | 2 weeks | High | Phases 1-5 |
| Phase 7: Subscription & Billing | 2 weeks | Medium | Phase 2 |

**Total Duration: 16 weeks (4 months)**

### Resource Requirements
- **Engineering**: 2-3 full-time engineers
- **Design**: 1 part-time UI/UX designer
- **DevOps**: 1 part-time DevOps engineer
- **Budget**: $5K-10K (Stripe, AWS/GCP, monitoring)

---

## Success Metrics & KPIs

### Technical Metrics
- **Uptime**: > 99.9% availability
- **Performance**: API < 200ms (p95), Pages < 2s
- **Scalability**: 1000+ concurrent users
- **Code Quality**: > 80% test coverage

### Business Metrics
- **Activation**: > 60% complete onboarding
- **Engagement**: > 40% DAU/MAU ratio
- **Retention**: < 5% monthly churn
- **Revenue**: > $10K MRR within 6 months

---

## Risk Mitigation

### Technical Risks
1. **Database Migration**: Phased migration with rollback
2. **AI Costs**: Caching, cheaper models for retries
3. **Performance at Scale**: Load testing, indexing

### Business Risks
1. **Low Adoption**: Beta program, iterate on feedback
2. **Payment Issues**: Comprehensive Stripe testing
3. **Competition**: Focus on unique AI capabilities

---

## Post-Launch Roadmap

### Quarter 1 (Months 5-7)
- Mobile app (iOS/Android)
- Advanced analytics
- Email digest reports

### Quarter 2 (Months 8-10)
- API marketplace
- White-label solution
- Multi-language support

### Quarter 3 (Months 11-12)
- Deal collaboration
- Semantic search
- Marketplace features

---

## Technology Stack

- **Frontend**: Next.js 14, TypeScript, Tailwind CSS
- **Backend**: Python FastAPI, SQLAlchemy
- **Database**: PostgreSQL 15, TimescaleDB, Redis
- **AI**: OpenAI GPT-4o, GPT-4o-mini
- **Infrastructure**: Docker, Kubernetes, Nginx
- **Monitoring**: Prometheus, Grafana, Sentry
- **Payments**: Stripe
- **CI/CD**: GitHub Actions

---

## Estimated Costs

| Service | Monthly Cost |
|---------|--------------|
| Cloud infrastructure | $500-1000 |
| Database (managed) | $200-400 |
| OpenAI API | $300-800 |
| Monitoring | $100-200 |
| Stripe fees | Variable |
| **Total** | **$1150-2500/month** |

---

## Conclusion

This roadmap provides a comprehensive path to transform the Watch Trading Engine into a **venture-backable SaaS platform**. The foundation built in the current PR provides the perfect launchpad.

**Next Steps:**
1. Review and approve roadmap
2. Prioritize Phase 1-2
3. Recruit engineering resources
4. Begin user research

---

*Document Version: 1.0*  
*Last Updated: 2026-01-16*  
*Author: GitHub Copilot*
