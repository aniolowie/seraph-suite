.PHONY: up down dev test test-unit test-integration lint format bench ingest ingest-nvd ingest-exploitdb worker sandbox-build sandbox-test sandbox-clean api-dev dashboard-dev dashboard-build dashboard-test clean help

PYTHON := python
UV := uv

help:
	@echo "Seraph Suite — Available targets:"
	@echo "  up              Start all services (Qdrant, Neo4j, Redis)"
	@echo "  down            Stop all services"
	@echo "  dev             Start services with dev overrides"
	@echo "  install         Install Python dependencies"
	@echo "  ingest          Run data ingestion pipeline"
	@echo "  test            Run unit + integration tests"
	@echo "  test-unit       Run unit tests only"
	@echo "  lint            Run ruff linter"
	@echo "  format          Run ruff formatter"
	@echo "  bench           Run HTB benchmark suite"
	@echo "  api-dev         Run FastAPI dev server (hot reload)"
	@echo "  dashboard-dev   Run Vite dev server for dashboard"
	@echo "  dashboard-build Build dashboard for production"
	@echo "  dashboard-test  Run dashboard unit tests"
	@echo "  clean               Remove __pycache__, .pyc, coverage files"
	@echo "  sandbox-build       Build the seraph-agent Docker image"
	@echo "  sandbox-test        Run sandbox integration tests (requires Docker)"
	@echo "  sandbox-clean       Remove all Seraph-managed sandbox containers"

up:
	docker compose up -d
	@echo "Services starting. Qdrant: http://localhost:6333, Neo4j: http://localhost:7474"

down:
	docker compose down

dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

install:
	$(UV) sync --all-extras

ingest:
	$(PYTHON) -m seraph.cli.ingest $(ARGS)

test:
	pytest tests/ -v --cov=src --cov-report=term-missing

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

bench:
	$(PYTHON) -m seraph.cli.bench $(ARGS)

ingest-nvd:
	seraph ingest nvd $(ARGS)

ingest-exploitdb:
	seraph ingest exploitdb $(ARGS)

worker:
	celery -A seraph.worker worker --loglevel=info

sandbox-build:
	docker build -t seraph-agent:latest -f src/seraph/sandbox/Dockerfile.agent .

sandbox-test:
	pytest tests/integration/sandbox/ -v -m integration

sandbox-clean:
	docker ps -aq --filter "label=seraph.managed=true" | xargs -r docker rm -f

api-dev:
	$(UV) run uvicorn seraph.api.app:create_app --factory --host 0.0.0.0 --port 8000 --reload

dashboard-dev:
	cd dashboard && npm run dev

dashboard-build:
	cd dashboard && npm run build

dashboard-test:
	cd dashboard && npm test

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	find . -name ".coverage" -delete
	find . -name "coverage.xml" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
