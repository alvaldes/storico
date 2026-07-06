.PHONY: help build up down logs restart ps test-backend test-frontend shell-api shell-backend shell-frontend clean setup

.DEFAULT_GOAL := help

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

build: ## Build all Docker images
	docker compose build

up: ## Start all services in detached mode
	docker compose up -d

down: ## Stop all services
	docker compose down

logs: ## Tail logs (optional: make logs <service>)
	docker compose logs -f $(filter-out $@,$(MAKECMDGOALS))

restart: down up ## Restart all services

ps: ## List running services
	docker compose ps

test-backend: ## Run backend tests with pytest
	cd backend && .venv/bin/pytest -v

test-frontend: ## Run frontend tests (build as smoke test)
	cd frontend && npm run build

shell-api: ## Open a bash shell in the storico-api container
	docker compose exec storico-api bash

shell-backend: shell-api ## Alias for shell-api

shell-frontend: ## Open a shell in the frontend directory
	cd frontend && bash

clean: ## Stop and remove all volumes (destructive)
	docker compose down -v

setup: ## Install all dependencies and build images
	cd backend && python -m venv .venv && .venv/bin/pip install -e ".[dev]"
	cd frontend && npm install
	docker compose build
