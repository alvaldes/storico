.PHONY: help build up down logs restart ps test-backend test-frontend shell-api shell-backend shell-frontend clean setup bump

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
	# Intentional word splitting: `make logs api backend` must pass each goal as a
	# separate service name, so the expansion stays unquoted on purpose.
	# shellcheck disable=SC2068,SC2145
	docker compose logs -f $(filter-out $@,$(MAKECMDGOALS))

restart: down up ## Restart all services

ps: ## List running services
	docker compose ps

test-backend: ## Run backend tests with pytest
	cd backend && .venv/bin/pytest -v

test-frontend: ## Run frontend tests (build as smoke test)
	cd frontend && pnpm run build

shell-api: ## Open a bash shell in the storico-api container
	docker compose exec storico-api bash

shell-backend: shell-api ## Alias for shell-api

shell-frontend: ## Open a shell in the frontend directory
	cd frontend && bash

clean: ## Stop and remove all volumes (destructive)
	docker compose down -v

setup: ## Install all dependencies and build images
	cd backend && python -m venv .venv && .venv/bin/pip install -e ".[dev]"
	cd frontend && pnpm install
	docker compose build

bump: ## Bump version from Conventional Commits and tag the release
	@test -z "$$(git status --porcelain --untracked-files=no)" || { echo "error: there are uncommitted tracked changes:"; git status --short --untracked-files=no; echo "       cz bump sweeps staged AND unstaged tracked changes into the version commit."; echo "       Commit or stash them first, then re-run make bump."; exit 1; }
	@tag=$$(git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//'); \
	test -n "$$tag" || { echo "error: no tag found; cz bump needs one as its version baseline."; exit 1; }; \
	for f in package.json frontend/package.json backend/pyproject.toml; do \
		case "$$f" in \
			*.json) got=$$(sed -n 's/^[[:space:]]*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$$f" | head -1) ;; \
			*)      got=$$(sed -n 's/^[[:space:]]*version[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "$$f" | head -1) ;; \
		esac; \
		test "$$got" = "$$tag" || { echo "error: $$f carries version '$$got' but the current tag is '$$tag'."; echo "       cz bump reads the version from the tag, needs to find that exact value already written in each version file, and skips the file silently when it does not match, while still creating the tag."; exit 1; }; \
	done
	cz bump
