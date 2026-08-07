SRC = app
TESTS ?= tests/
PYTEST_ARGS ?=

.PHONY: help
.PHONY: init install run worker scheduler
.PHONY: verify fix check format format-check type openapi openapi-check
.PHONY: test cov
.PHONY: build
.PHONY: migrate makemigrations deploy taskiq-stream-cleanup usage-memory-stress usage-query-benchmark runtime-state-stress system-jsonrpc-cache-stress gateway-flow-integration circuit-flow-integration
.PHONY: commit
.PHONY: ci changelog

.DEFAULT_GOAL := help

help:
	@echo "Usage:"
	@echo "  make init            Install dependencies (uv sync --all-groups)"
	@echo "  make install         Alias for init"
	@echo "  make run             Start the app (uv run app)"
	@echo "  make worker          Start the TaskIQ worker"
	@echo ""
	@echo "  make verify          Check only: format-check, check, type"
	@echo "  make fix             Auto-fix lint and format"
	@echo "  make check           Lint (ruff check)"
	@echo "  make format          Format (ruff format)"
	@echo "  make format-check    Check formatting only"
	@echo "  make type            Type check (ty, basedpyright)"
	@echo ""
	@echo "  make test            Run tests (optionally TESTS=tests/path PYTEST_ARGS='-k expr')"
	@echo "  make cov             Run tests with coverage (optionally TESTS=tests/path)"
	@echo "  make build           Build the project"
	@echo ""
	@echo "  make migrate         Apply database migrations"
	@echo "  make makemigrations  Create new migrations"
	@echo "  make deploy          Create standard developer accounts"
	@echo "  make taskiq-stream-cleanup  Inspect TaskIQ Stream cleanup boundary (ARGS='--apply' to trim)"
	@echo "  make usage-memory-stress  Measure Usage Stream memory against a dedicated Redis"
	@echo "  make usage-query-benchmark  Compare wide and narrow Usage queries in a test PostgreSQL database"
	@echo "  make runtime-state-stress  Stress Runtime State against a dedicated Redis DB (ARGS='...')"
	@echo "  make system-jsonrpc-cache-stress  Stress System JSON-RPC Cache core and isolated Redis/PostgreSQL paths"
	@echo "  make gateway-flow-integration  Run the isolated real-environment Gateway flow"
	@echo "  make circuit-flow-integration  Run the real Gateway flow including adaptive Circuit qualification"
	@echo ""
	@echo "  make commit          Run prek hooks"
	@echo "  make ci              Full CI pipeline (format-check, check, type, cov, build)"
	@echo "  make changelog       Generate CHANGELOG.md (git-cliff)"

# Dependencies
init install:
	uv sync --all-groups

# Run app
run:
	uv run app

# Run TaskIQ worker
worker:
	uv run taskiq worker jobs.worker:broker --no-configure-logging

# Run TaskIQ scheduler (single instance only)
scheduler:
	uv run taskiq scheduler jobs.scheduler:scheduler

# Lint & format
verify: format-check check type openapi-check

fix:
	uv run ruff check --fix .
	uv run ruff format .

check:
	uv run ruff check .

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

type:
	uv run ty check .
	uv run basedpyright

openapi:
	ENV_FILE=/dev/null APP_ENV=dev APP_API_KEY_MASTER_KEY=openapi-contract-placeholder-32-bytes uv run python scripts/export_openapi.py

openapi-check:
	ENV_FILE=/dev/null APP_ENV=dev APP_API_KEY_MASTER_KEY=openapi-contract-placeholder-32-bytes uv run python scripts/export_openapi.py --check

# Test
test:
	uv run python -m pytest $(TESTS) $(PYTEST_ARGS)

cov:
	uv run python -m pytest --cov=$(SRC) $(TESTS) --cov-report=term-missing $(PYTEST_ARGS)

# Build
build:
	uv build

# Migration
migrate:
	uv run tortoise migrate

makemigrations:
	uv run tortoise makemigrations

# Deploy developer accounts (idempotent)
deploy:
	uv run python scripts/deploy.py

# Trim only acknowledged TaskIQ Stream history (dry-run by default)
taskiq-stream-cleanup:
	uv run python scripts/taskiq_stream_cleanup.py $(ARGS)

usage-memory-stress:
	uv run python scripts/usage_memory_stress.py $(ARGS)

usage-query-benchmark:
	uv run python scripts/usage_query_benchmark.py $(ARGS)

runtime-state-stress:
	uv run python -m scripts.runtime_state_stress $(ARGS)

system-jsonrpc-cache-stress:
	uv run python -m scripts.system_jsonrpc_cache_stress $(ARGS)

gateway-flow-integration:
	uv run python -m scripts.gateway_flow_integration.orchestrator $(ARGS)

circuit-flow-integration: gateway-flow-integration

# Pre-commit
commit:
	uv run prek run

# CI
ci: format-check check type cov build

# Changelog
changelog:
	uvx git-cliff -o CHANGELOG.md
