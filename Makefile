# Developer entry points. `make check` is exactly what CI runs.
.DEFAULT_GOAL := help
.PHONY: help install dev test lint typecheck check e2e build run clean

PY := backend/.venv/bin

help: ## Show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install backend and frontend dependencies
	python3 -m venv backend/.venv
	$(PY)/pip install -q --upgrade pip
	$(PY)/pip install -q -e "backend/[dev]"
	cd frontend && npm ci --no-audit --no-fund

dev: ## Run the API and the web client with hot reload
	@echo "API      http://127.0.0.1:8000/api/docs"
	@echo "Frontend http://127.0.0.1:5173"
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000 & \
	cd frontend && npm run dev

test: ## Run every unit and integration test
	cd backend && .venv/bin/pytest
	cd frontend && npm run test:coverage

lint: ## Lint and format-check both sides
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check .
	cd frontend && npm run lint

typecheck: ## Strict type checking on both sides
	cd backend && .venv/bin/mypy .
	cd frontend && npm run typecheck

security: ## Static analysis and dependency audit
	cd backend && .venv/bin/bandit -q -c pyproject.toml -r app
	cd backend && .venv/bin/pip-audit --strict --progress-spinner off .
	cd frontend && npm audit --audit-level=high

check: lint typecheck test security ## Everything CI runs, locally

build: ## Build the production container image
	docker build -t lexiclear:local .

run: build ## Build and run the container on http://localhost:8000
	docker run --rm -p 8000:7860 --env-file .env lexiclear:local

e2e: ## Run the end-to-end and accessibility suites against a running container
	cd frontend && npx playwright install --with-deps chromium && npm run test:e2e

clean: ## Remove build and cache artefacts
	rm -rf backend/.venv backend/.pytest_cache backend/.mypy_cache backend/.ruff_cache \
	       backend/coverage.xml frontend/node_modules frontend/dist frontend/coverage \
	       frontend/.tsbuild frontend/playwright-report frontend/test-results
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
