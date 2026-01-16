#!/bin/bash
# Kubernetes deployment script for Watchy Watch Trading Engine
# Usage: ./deploy.sh [environment] [action]
# Example: ./deploy.sh production deploy

set -e

# Configuration
NAMESPACE="watchy"
ENVIRONMENT=${1:-production}
ACTION=${2:-deploy}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl not found. Please install kubectl."
        exit 1
    fi
    
    # Check cluster connection
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster. Check your kubeconfig."
        exit 1
    fi
    
    # Check storage classes
    if ! kubectl get storageclass &> /dev/null; then
        log_warn "No storage classes found. You may need to configure storage."
    fi
    
    log_info "Prerequisites check passed ✓"
}

create_secrets() {
    log_info "Creating secrets..."
    
    if kubectl get secret watchy-secrets -n $NAMESPACE &> /dev/null; then
        log_warn "Secrets already exist. Skipping creation."
        log_warn "To update secrets, delete and recreate: kubectl delete secret watchy-secrets -n $NAMESPACE"
        return
    fi
    
    # Generate random passwords
    POSTGRES_PASSWORD=$(openssl rand -base64 32)
    REDIS_PASSWORD=$(openssl rand -base64 32)
    SECRET_KEY=$(openssl rand -base64 64)
    JWT_SECRET_KEY=$(openssl rand -base64 64)
    
    # Create secrets
    kubectl create secret generic watchy-secrets \
        --from-literal=POSTGRES_USER=watchy_user \
        --from-literal=POSTGRES_PASSWORD=$POSTGRES_PASSWORD \
        --from-literal=REDIS_PASSWORD=$REDIS_PASSWORD \
        --from-literal=SECRET_KEY=$SECRET_KEY \
        --from-literal=JWT_SECRET_KEY=$JWT_SECRET_KEY \
        --from-literal=OPENAI_API_KEY=${OPENAI_API_KEY:-sk-placeholder} \
        --from-literal=ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-sk-ant-placeholder} \
        --from-literal=DATABASE_URL="postgresql://watchy_user:$POSTGRES_PASSWORD@postgres-service:5432/watchy_trading" \
        -n $NAMESPACE
    
    log_info "Secrets created ✓"
    log_warn "IMPORTANT: Save these credentials securely!"
    echo "POSTGRES_PASSWORD: $POSTGRES_PASSWORD"
    echo "REDIS_PASSWORD: $REDIS_PASSWORD"
}

deploy_infrastructure() {
    log_info "Deploying infrastructure..."
    
    # Create namespace
    kubectl apply -f namespace.yaml
    
    # Deploy configuration
    kubectl apply -f configmap.yaml
    
    # Create secrets if needed
    create_secrets
    
    # Deploy storage
    kubectl apply -f pvc.yaml
    
    # Deploy databases
    kubectl apply -f postgres-deployment.yaml
    kubectl apply -f redis-deployment.yaml
    
    log_info "Waiting for databases to be ready..."
    kubectl wait --for=condition=ready pod -l app.kubernetes.io/component=postgres -n $NAMESPACE --timeout=300s
    kubectl wait --for=condition=ready pod -l app.kubernetes.io/component=redis -n $NAMESPACE --timeout=300s
    
    log_info "Infrastructure deployed ✓"
}

deploy_application() {
    log_info "Deploying application..."
    
    # Deploy application services
    kubectl apply -f backend-deployment.yaml
    kubectl apply -f frontend-deployment.yaml
    kubectl apply -f celery-deployment.yaml
    
    # Deploy nginx
    kubectl apply -f nginx-deployment.yaml
    
    log_info "Waiting for application to be ready..."
    kubectl wait --for=condition=ready pod -l app.kubernetes.io/component=backend -n $NAMESPACE --timeout=300s
    kubectl wait --for=condition=ready pod -l app.kubernetes.io/component=frontend -n $NAMESPACE --timeout=300s
    
    log_info "Application deployed ✓"
}

deploy_monitoring() {
    log_info "Deploying monitoring..."
    
    kubectl apply -f prometheus-deployment.yaml
    kubectl apply -f grafana-deployment.yaml
    
    log_info "Monitoring deployed ✓"
}

deploy_networking() {
    log_info "Deploying networking..."
    
    kubectl apply -f ingress.yaml
    kubectl apply -f network-policy.yaml
    
    log_info "Networking deployed ✓"
}

deploy_policies() {
    log_info "Deploying policies..."
    
    kubectl apply -f pod-disruption-budget.yaml
    
    log_info "Policies deployed ✓"
}

initialize_database() {
    log_info "Initializing database..."
    
    POSTGRES_POD=$(kubectl get pod -n $NAMESPACE -l app.kubernetes.io/component=postgres -o jsonpath='{.items[0].metadata.name}')
    
    if [ -z "$POSTGRES_POD" ]; then
        log_error "PostgreSQL pod not found"
        exit 1
    fi
    
    # Copy schema file
    kubectl cp ../schema.sql $NAMESPACE/$POSTGRES_POD:/tmp/schema.sql
    
    # Load schema
    kubectl exec -n $NAMESPACE $POSTGRES_POD -- psql -U watchy_user -d watchy_trading -f /tmp/schema.sql
    
    log_info "Database initialized ✓"
}

deploy_all() {
    log_info "Starting full deployment..."
    
    deploy_infrastructure
    deploy_application
    deploy_monitoring
    deploy_networking
    deploy_policies
    
    log_info "Deployment complete! ✓"
    
    # Show status
    show_status
}

show_status() {
    log_info "Cluster Status:"
    echo ""
    echo "Pods:"
    kubectl get pods -n $NAMESPACE
    echo ""
    echo "Services:"
    kubectl get svc -n $NAMESPACE
    echo ""
    echo "Ingress:"
    kubectl get ingress -n $NAMESPACE
    echo ""
    echo "HPA:"
    kubectl get hpa -n $NAMESPACE
    echo ""
    echo "PVC:"
    kubectl get pvc -n $NAMESPACE
}

delete_all() {
    log_warn "This will delete ALL resources in namespace $NAMESPACE"
    read -p "Are you sure? (yes/no): " confirm
    
    if [ "$confirm" != "yes" ]; then
        log_info "Aborted"
        exit 0
    fi
    
    log_info "Deleting all resources..."
    kubectl delete namespace $NAMESPACE
    log_info "Resources deleted ✓"
}

# Main script
case $ACTION in
    deploy)
        check_prerequisites
        deploy_all
        ;;
    infrastructure)
        check_prerequisites
        deploy_infrastructure
        ;;
    application)
        check_prerequisites
        deploy_application
        ;;
    monitoring)
        check_prerequisites
        deploy_monitoring
        ;;
    init-db)
        initialize_database
        ;;
    status)
        show_status
        ;;
    delete)
        delete_all
        ;;
    *)
        echo "Usage: $0 [environment] [action]"
        echo ""
        echo "Actions:"
        echo "  deploy        - Deploy all components"
        echo "  infrastructure - Deploy infrastructure only"
        echo "  application   - Deploy application only"
        echo "  monitoring    - Deploy monitoring only"
        echo "  init-db       - Initialize database with schema"
        echo "  status        - Show cluster status"
        echo "  delete        - Delete all resources"
        echo ""
        echo "Example: $0 production deploy"
        exit 1
        ;;
esac
