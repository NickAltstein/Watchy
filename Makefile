# Watch Trading Platform - Docker Compose Makefile
.PHONY: help build up down restart logs ps clean test backup

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[1;33m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(BLUE)Watch Trading Platform - Docker Commands$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-20s$(NC) %s\n", $$1, $$2}'

setup: ## Initial setup - copy env template
	@if [ ! -f .env ]; then \
		cp .env.template .env; \
		echo "$(GREEN)✓$(NC) Created .env file from template"; \
		echo "$(YELLOW)⚠$(NC)  Please edit .env and add your API keys"; \
	else \
		echo "$(YELLOW)⚠$(NC)  .env already exists"; \
	fi

build: ## Build all services
	@echo "$(BLUE)Building services...$(NC)"
	docker-compose build

up: ## Start all services
	@echo "$(BLUE)Starting services...$(NC)"
	docker-compose up -d
	@echo "$(GREEN)✓$(NC) Services started"
	@make ps

down: ## Stop all services
	@echo "$(BLUE)Stopping services...$(NC)"
	docker-compose down
	@echo "$(GREEN)✓$(NC) Services stopped"

restart: ## Restart all services
	@echo "$(BLUE)Restarting services...$(NC)"
	docker-compose restart
	@echo "$(GREEN)✓$(NC) Services restarted"

logs: ## View logs from all services
	docker-compose logs -f

logs-backend: ## View backend logs
	docker-compose logs -f backend

logs-frontend: ## View frontend logs
	docker-compose logs -f frontend

logs-worker: ## View celery worker logs
	docker-compose logs -f celery_worker

ps: ## Show service status
	@docker-compose ps

clean: ## Remove all containers, volumes, and images
	@echo "$(YELLOW)⚠$(NC)  This will remove ALL data. Continue? [y/N]" && read ans && [ $${ans:-N} = y ]
	docker-compose down -v --rmi all
	@echo "$(GREEN)✓$(NC) Cleaned up"

reset: down clean setup build up ## Complete reset

db-shell: ## Connect to PostgreSQL database
	docker-compose exec postgres psql -U watchy -d watchy_trading

redis-cli: ## Connect to Redis CLI
	docker-compose exec redis redis-cli

backend-shell: ## Open shell in backend container
	docker-compose exec backend /bin/bash

test: ## Run tests
	docker-compose exec backend pytest -v

test-coverage: ## Run tests with coverage
	docker-compose exec backend pytest --cov=. --cov-report=html

migrate: ## Run database migrations
	docker-compose exec backend python migrate_to_postgres.py

backup: ## Backup database
	@echo "$(BLUE)Creating backup...$(NC)"
	@mkdir -p backups
	docker-compose exec -T postgres pg_dump -U watchy watchy_trading | gzip > backups/backup_$$(date +%Y%m%d_%H%M%S).sql.gz
	@echo "$(GREEN)✓$(NC) Backup created in backups/"

restore: ## Restore database from latest backup
	@echo "$(YELLOW)⚠$(NC)  This will restore from the latest backup. Continue? [y/N]" && read ans && [ $${ans:-N} = y ]
	@LATEST=$$(ls -t backups/*.sql.gz | head -1); \
	if [ -z "$$LATEST" ]; then \
		echo "$(YELLOW)⚠$(NC)  No backups found"; \
	else \
		echo "$(BLUE)Restoring from $$LATEST$(NC)"; \
		gunzip < $$LATEST | docker-compose exec -T postgres psql -U watchy watchy_trading; \
		echo "$(GREEN)✓$(NC) Restored"; \
	fi

health: ## Check health of all services
	@echo "$(BLUE)Checking service health...$(NC)"
	@curl -sf http://localhost:8000/health > /dev/null && echo "$(GREEN)✓$(NC) Backend: healthy" || echo "$(YELLOW)✗$(NC) Backend: unhealthy"
	@curl -sf http://localhost:3000 > /dev/null && echo "$(GREEN)✓$(NC) Frontend: healthy" || echo "$(YELLOW)✗$(NC) Frontend: unhealthy"
	@docker-compose exec -T postgres pg_isready -U watchy > /dev/null && echo "$(GREEN)✓$(NC) Database: healthy" || echo "$(YELLOW)✗$(NC) Database: unhealthy"
	@docker-compose exec -T redis redis-cli ping > /dev/null && echo "$(GREEN)✓$(NC) Redis: healthy" || echo "$(YELLOW)✗$(NC) Redis: unhealthy"

dev: setup up logs ## Setup and start in development mode

prod-build: ## Build for production
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml build

stats: ## Show resource usage
	docker stats --no-stream

prune: ## Clean up Docker system
	docker system prune -f
	@echo "$(GREEN)✓$(NC) Pruned unused Docker resources"
