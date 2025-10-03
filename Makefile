.PHONY: help setup start stop restart clean status logs pipeline test

# Colors for output
RED=\033[0;31m
GREEN=\033[0;32m
YELLOW=\033[1;33m
NC=\033[0m # No Color

##@ Help

help: ## Display this help message
	@echo "$(GREEN)AI Challenge | Public Incentives - Makefile Commands$(NC)"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make $(YELLOW)<target>$(NC)\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2 } /^##@/ { printf "\n$(YELLOW)%s$(NC)\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Setup & Initialization

setup: ## Initial setup - start DB and create schema
	@echo "$(GREEN)🚀 Starting database...$(NC)"
	docker-compose up -d db
	@echo "$(YELLOW)⏳ Waiting for PostgreSQL to be ready...$(NC)"
	@sleep 5
	@echo "$(GREEN)✅ Initializing database schema...$(NC)"
	docker-compose run --rm api python -m backend.app.db.init_db

##@ Services Management

start: ## Start all services (db, api, prometheus, grafana)
	@echo "$(GREEN)🚀 Starting all services...$(NC)"
	docker-compose up -d
	@echo "$(GREEN)✅ Services started!$(NC)"
	@echo "API: http://localhost:8000"
	@echo "Docs: http://localhost:8000/docs"
	@echo "Metrics: http://localhost:9090"
	@echo "Grafana: http://localhost:3000"

stop: ## Stop all services
	@echo "$(YELLOW)🛑 Stopping all services...$(NC)"
	docker-compose stop
	@echo "$(GREEN)✅ Services stopped$(NC)"

restart: ## Restart all services
	@echo "$(YELLOW)🔄 Restarting services...$(NC)"
	docker-compose restart
	@echo "$(GREEN)✅ Services restarted$(NC)"

restart-api: ## Restart only the API service
	@echo "$(YELLOW)🔄 Restarting API...$(NC)"
	docker-compose restart api
	@echo "$(GREEN)✅ API restarted$(NC)"

##@ Pipeline & Data Processing

pipeline: ## Run full pipeline (scrape → process → embed → load companies)
	@echo "$(GREEN)🔄 Running full pipeline...$(NC)"
	docker-compose --profile pipeline run --rm pipeline
	@echo "$(GREEN)✅ Pipeline complete!$(NC)"

pipeline-quick: ## Run pipeline with limit (faster for testing)
	@echo "$(GREEN)🔄 Running quick pipeline (limited)...$(NC)"
	docker-compose --profile pipeline run --rm pipeline --limit 10
	@echo "$(GREEN)✅ Quick pipeline complete!$(NC)"

pipeline-enhance: ## Run enhancement pipeline (HTML + PDF processing)
	@echo "$(GREEN)🔄 Enhancing incentives data...$(NC)"
	docker-compose run --rm api python -m backend.app.scripts.enhance_with_source_html
	@echo "$(GREEN)✅ Enhancement complete!$(NC)"

load-companies: ## Load companies from CSV
	@echo "$(GREEN)📊 Loading companies...$(NC)"
	docker-compose run --rm api python -m backend.app.scripts.load_companies
	@echo "$(GREEN)✅ Companies loaded!$(NC)"

generate-embeddings: ## Generate embeddings for incentives
	@echo "$(GREEN)🧮 Generating embeddings...$(NC)"
	docker-compose run --rm api python -m backend.app.scripts.extract_ai_descriptions --generate-embeddings
	@echo "$(GREEN)✅ Embeddings generated!$(NC)"

##@ Logs & Monitoring

logs: ## Show logs from all services
	docker-compose logs -f

logs-api: ## Show API logs
	docker-compose logs -f api

logs-db: ## Show database logs
	docker-compose logs -f db

logs-pipeline: ## Show pipeline logs
	docker-compose logs pipeline

stats: ## Show cost tracking statistics
	@echo "$(GREEN)💰 Cost Tracking Statistics$(NC)"
	@docker-compose exec -T api python -c "import json; data = json.load(open('.cache/cost_tracking.json', 'r')) if __import__('os').path.exists('.cache/cost_tracking.json') else {}; total = sum(v.get('total_cost', 0) for v in data.values()); print(f'Total documents: {len(data)}'); print(f'Total cost: €{total:.4f}'); [print(f'{k}: €{v.get(\"total_cost\", 0):.4f}') for k, v in sorted(data.items(), key=lambda x: x[1].get(\"total_cost\", 0), reverse=True)[:5]]" 2>/dev/null || echo "No cost data available yet"

##@ Database

db-shell: ## Open PostgreSQL shell
	@echo "$(GREEN)🐘 Opening PostgreSQL shell...$(NC)"
	docker-compose exec db psql -U postgres -d ai_challenge

db-backup: ## Backup database to backups/
	@echo "$(GREEN)💾 Creating database backup...$(NC)"
	@mkdir -p backups
	@docker-compose exec -T db pg_dump -U postgres ai_challenge > backups/backup_$$(date +%Y%m%d_%H%M%S).sql
	@echo "$(GREEN)✅ Backup created in backups/$(NC)"

db-restore: ## Restore database from latest backup
	@echo "$(YELLOW)⚠️  This will restore from the latest backup. Continue? [y/N]$(NC)" && read ans && [ $${ans:-N} = y ]
	@echo "$(GREEN)📥 Restoring database...$(NC)"
	@latest=$$(ls -t backups/*.sql | head -1); \
	docker-compose exec -T db psql -U postgres ai_challenge < $$latest
	@echo "$(GREEN)✅ Database restored!$(NC)"

db-reset: ## Reset database (drop and recreate)
	@echo "$(RED)⚠️  WARNING: This will DELETE ALL DATA! Continue? [y/N]$(NC)" && read ans && [ $${ans:-N} = y ]
	@echo "$(YELLOW)🗑️  Resetting database...$(NC)"
	docker-compose run --rm api python -m backend.app.db.init_db --drop
	docker-compose run --rm api python -m backend.app.db.init_db
	@echo "$(GREEN)✅ Database reset complete!$(NC)"

##@ API Testing & Documentation

api-shell: ## Open shell in API container
	@echo "$(GREEN)🐚 Opening API container shell...$(NC)"
	docker-compose exec api /bin/bash

api-docs: ## Open API documentation in browser
	@echo "$(GREEN)📚 Opening API documentation...$(NC)"
	@open http://localhost:8000/docs 2>/dev/null || xdg-open http://localhost:8000/docs 2>/dev/null || echo "Open http://localhost:8000/docs in your browser"

api-test: ## Test API endpoints
	@echo "$(GREEN)🧪 Testing API endpoints...$(NC)"
	@curl -s http://localhost:8000/health | python -m json.tool
	@echo ""
	@curl -s http://localhost:8000/api/v1/incentives?page=1&page_size=5 | python -m json.tool | head -30

##@ Matching & Search

search-matches: ## Interactive matching search
	@echo "$(GREEN)🔍 Starting interactive matching search...$(NC)"
	docker-compose run --rm api python -m backend.app.scripts.search_matches

search-matches-for: ## Search matches for specific incentive ID (usage: make search-matches-for ID=<id>)
	@echo "$(GREEN)🔍 Searching matches for incentive $(ID)...$(NC)"
	docker-compose run --rm api python -m backend.app.scripts.search_matches --incentive-id $(ID)

evaluate-matching: ## Run matching evaluation (P@5, nDCG@5)
	@echo "$(GREEN)📊 Running matching evaluation...$(NC)"
	docker-compose run --rm api python -m backend.app.scripts.evaluate_matching

##@ Testing

test: ## Run all tests
	@echo "$(GREEN)🧪 Running tests...$(NC)"
	docker-compose run --rm api pytest tests/ -v

test-unit: ## Run unit tests only
	@echo "$(GREEN)🧪 Running unit tests...$(NC)"
	docker-compose run --rm api pytest tests/unit/ -v

test-integration: ## Run integration tests
	@echo "$(GREEN)🧪 Running integration tests...$(NC)"
	docker-compose run --rm api pytest tests/integration/ -v

test-coverage: ## Run tests with coverage report
	@echo "$(GREEN)🧪 Running tests with coverage...$(NC)"
	docker-compose run --rm api pytest --cov=backend --cov-report=html --cov-report=term

##@ Cleanup

clean: ## Remove all containers, volumes, and cache
	@echo "$(RED)⚠️  This will remove all containers, volumes, and cached data! Continue? [y/N]$(NC)" && read ans && [ $${ans:-N} = y ]
	@echo "$(YELLOW)🧹 Cleaning up...$(NC)"
	docker-compose down -v
	rm -rf .cache/
	@echo "$(GREEN)✅ Cleanup complete!$(NC)"

clean-cache: ## Clear OpenAI cache only
	@echo "$(YELLOW)🧹 Clearing cache...$(NC)"
	rm -rf .cache/
	@echo "$(GREEN)✅ Cache cleared!$(NC)"

clean-data: ## Remove processed data
	@echo "$(RED)⚠️  This will remove processed data! Continue? [y/N]$(NC)" && read ans && [ $${ans:-N} = y ]
	@echo "$(YELLOW)🧹 Cleaning data...$(NC)"
	rm -rf data/processed/*
	@echo "$(GREEN)✅ Data cleaned!$(NC)"

##@ Status & Info

status: ## Show status of all services
	@echo "$(GREEN)📊 Service Status:$(NC)"
	@docker-compose ps

info: ## Show system information
	@echo "$(GREEN)ℹ️  System Information:$(NC)"
	@echo "Docker version: $$(docker --version)"
	@echo "Docker Compose version: $$(docker-compose --version)"
	@echo ""
	@echo "$(GREEN)📦 Database Info:$(NC)"
	@docker-compose exec -T db psql -U postgres -d ai_challenge -c "SELECT COUNT(*) as total_incentives FROM incentives;" 2>/dev/null || echo "Database not running"
	@docker-compose exec -T db psql -U postgres -d ai_challenge -c "SELECT COUNT(*) as total_companies FROM companies;" 2>/dev/null || echo "Database not running"
	@echo ""
	@echo "$(GREEN)💾 Disk Usage:$(NC)"
	@du -sh data/ 2>/dev/null || echo "No data directory"
	@du -sh .cache/ 2>/dev/null || echo "No cache directory"

ports: ## Show exposed ports
	@echo "$(GREEN)🌐 Exposed Ports:$(NC)"
	@echo "API: http://localhost:8000"
	@echo "API Docs: http://localhost:8000/docs"
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana: http://localhost:3000"
	@echo "PostgreSQL: localhost:5432"

##@ Development

dev-setup: ## Setup local development environment
	@echo "$(GREEN)🔧 Setting up development environment...$(NC)"
	python -m venv venv
	./venv/bin/pip install -r requirements.txt
	./venv/bin/pip install -r backend/requirements.txt
	./venv/bin/pip install -r scraper/requirements.txt
	./venv/bin/playwright install chromium
	@echo "$(GREEN)✅ Development environment ready!$(NC)"
	@echo "Activate with: source venv/bin/activate"

format: ## Format code with black
	@echo "$(GREEN)🎨 Formatting code...$(NC)"
	docker-compose run --rm api black backend/ tests/

lint: ## Lint code with ruff
	@echo "$(GREEN)🔍 Linting code...$(NC)"
	docker-compose run --rm api ruff check backend/ tests/

type-check: ## Type check with mypy
	@echo "$(GREEN)🔬 Type checking...$(NC)"
	docker-compose run --rm api mypy backend/

##@ Quick Commands

quick-test: start api-test ## Quick test - start services and test API
	@echo "$(GREEN)✅ Quick test complete!$(NC)"

quick-demo: setup pipeline start ## Full demo - setup, run pipeline, start services
	@echo "$(GREEN)✅ Demo ready!$(NC)"
	@echo "$(GREEN)📚 Visit http://localhost:8000/docs to explore the API$(NC)"
