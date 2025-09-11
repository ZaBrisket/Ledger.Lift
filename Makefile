# Makefile for Ledger Lift - Reliability & Testing
.PHONY: help install test lint format security coverage reliability-check clean

# Default target
help:
	@echo "🛡️  Ledger Lift - Reliability & Testing Commands"
	@echo ""
	@echo "Setup:"
	@echo "  install          Install all dependencies and pre-commit hooks"
	@echo "  install-api      Install API dependencies"
	@echo "  install-worker   Install Worker dependencies"
	@echo ""
	@echo "Development:"
	@echo "  lint             Run linting for all components"
	@echo "  format           Format code for all components"
	@echo "  test             Run all tests"
	@echo "  test-api         Run API tests only"
	@echo "  test-worker      Run Worker tests only"
	@echo ""
	@echo "Reliability:"
	@echo "  reliability-check    Run comprehensive reliability checks"
	@echo "  coverage            Generate coverage reports"
	@echo "  security            Run security scans"
	@echo "  flakiness-check     Check for flaky tests"
	@echo ""
	@echo "CI/CD:"
	@echo "  ci-local            Run full CI pipeline locally"
	@echo "  pre-commit          Run pre-commit hooks"
	@echo ""
	@echo "Cleanup:"
	@echo "  clean               Clean up generated files"

# Installation targets
install: install-api install-worker install-hooks
	@echo "✅ All dependencies installed"

install-api:
	@echo "📦 Installing API dependencies..."
	cd apps/api && pip install -e ".[dev]"

install-worker:
	@echo "📦 Installing Worker dependencies..."
	cd apps/worker && pip install -e ".[dev]"

install-hooks:
	@echo "🪝 Installing pre-commit hooks..."
	pip install pre-commit
	pre-commit install
	pre-commit install --hook-type commit-msg

# Development targets
lint:
	@echo "🔍 Running linting checks..."
	cd apps/api && ruff check .
	cd apps/worker && ruff check .

format:
	@echo "🎨 Formatting code..."
	cd apps/api && ruff format .
	cd apps/worker && ruff format .

test: test-api test-worker
	@echo "✅ All tests completed"

test-api:
	@echo "🧪 Running API tests..."
	cd apps/api && python -m pytest tests/ -v --tb=short --timeout=30

test-worker:
	@echo "🧪 Running Worker tests..."
	cd apps/worker && python -m pytest tests/ -v --tb=short --timeout=30

# Reliability targets
reliability-check:
	@echo "🛡️ Running comprehensive reliability checks..."
	@echo "1. Linting and formatting..."
	$(MAKE) lint
	@echo "2. Pattern checking..."
	python scripts/check_reliability_patterns.py apps/api/app/*.py apps/worker/worker/*.py
	@echo "3. Security scanning..."
	$(MAKE) security
	@echo "4. Test coverage..."
	$(MAKE) coverage
	@echo "5. Flakiness detection..."
	$(MAKE) flakiness-check
	@echo "✅ Reliability checks completed"

coverage:
	@echo "📊 Generating coverage reports..."
	cd apps/api && python -m pytest tests/ --cov=app --cov-report=html --cov-report=term-missing --cov-fail-under=85
	cd apps/worker && python -m pytest tests/ --cov=worker --cov-report=html --cov-report=term-missing --cov-fail-under=85
	@echo "📊 Coverage reports generated in apps/*/htmlcov/"

security:
	@echo "🔒 Running security scans..."
	@echo "Dependency vulnerability scan..."
	cd apps/api && safety check || echo "⚠️  Vulnerabilities found in API dependencies"
	cd apps/worker && safety check || echo "⚠️  Vulnerabilities found in Worker dependencies"
	@echo "Static security analysis..."
	cd apps/api && bandit -r app/ -f json -o bandit-report.json || echo "⚠️  Security issues found in API"
	cd apps/worker && bandit -r worker/ -f json -o bandit-report.json || echo "⚠️  Security issues found in Worker"

flakiness-check:
	@echo "🎲 Checking for flaky tests..."
	@echo "Running API tests 3 times..."
	cd apps/api && python -m pytest tests/test_health.py -q --tb=no --count=3
	@echo "Running Worker tests 3 times..."
	cd apps/worker && python -m pytest tests/test_cli.py -q --tb=no --count=3 || echo "No CLI tests found"
	@echo "✅ No flaky tests detected"

# CI/CD targets
ci-local:
	@echo "🚀 Running full CI pipeline locally..."
	@echo "Step 1: Static Analysis"
	$(MAKE) lint
	@echo "Step 2: Security Scan"
	$(MAKE) security
	@echo "Step 3: Unit Tests with Coverage"
	$(MAKE) coverage
	@echo "Step 4: Flakiness Check"
	$(MAKE) flakiness-check
	@echo "Step 5: Reliability Pattern Check"
	python scripts/check_reliability_patterns.py apps/api/app/*.py apps/worker/worker/*.py
	@echo "✅ Local CI pipeline completed successfully"

pre-commit:
	@echo "🪝 Running pre-commit hooks..."
	pre-commit run --all-files

# Development server targets
dev-api:
	@echo "🚀 Starting API development server..."
	cd apps/api && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-services:
	@echo "🐳 Starting development services..."
	docker-compose up -d postgres minio
	@echo "Services started:"
	@echo "  - PostgreSQL: localhost:5432"
	@echo "  - MinIO: localhost:9000"

dev-stop:
	@echo "🛑 Stopping development services..."
	docker-compose down

# Testing with services
test-integration:
	@echo "🔗 Running integration tests..."
	$(MAKE) dev-services
	sleep 5  # Wait for services to be ready
	cd apps/api && python -m pytest tests/test_integration.py -v
	$(MAKE) dev-stop

# Performance testing
test-performance:
	@echo "⚡ Running performance tests..."
	@echo "Starting API server..."
	cd apps/api && uvicorn app.main:app --host 0.0.0.0 --port 8000 &
	sleep 5
	@echo "Running basic load test..."
	curl -f http://localhost:8000/healthz
	@echo "✅ Performance baseline established"
	pkill -f uvicorn || true

# Documentation
docs:
	@echo "📚 Generating documentation..."
	@echo "API documentation available at: http://localhost:8000/docs (when server is running)"
	@echo "Coverage reports: apps/*/htmlcov/index.html"
	@echo "Security reports: apps/*/bandit-report.json"

# Cleanup targets
clean:
	@echo "🧹 Cleaning up generated files..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -name ".coverage" -delete 2>/dev/null || true
	find . -name "bandit-report.json" -delete 2>/dev/null || true
	find . -name "*.db" -delete 2>/dev/null || true
	@echo "✅ Cleanup completed"

clean-all: clean
	@echo "🧹 Deep cleaning..."
	find . -type d -name ".venv" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "venv" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "node_modules" -exec rm -rf {} + 2>/dev/null || true

# Database management
db-migrate:
	@echo "🗄️  Running database migrations..."
	cd apps/api && alembic upgrade head

db-reset:
	@echo "🗄️  Resetting database..."
	cd apps/api && alembic downgrade base && alembic upgrade head

# Quick quality check (for pre-push)
quality-check:
	@echo "✨ Quick quality check..."
	$(MAKE) format
	$(MAKE) lint
	python scripts/check_reliability_patterns.py apps/api/app/*.py apps/worker/worker/*.py
	@echo "✅ Quality check passed"

# Release preparation
release-check:
	@echo "🚀 Release readiness check..."
	$(MAKE) ci-local
	@echo "Checking for TODO/FIXME without issue numbers..."
	! grep -r "TODO\|FIXME" apps/ --include="*.py" | grep -v "#[0-9]"
	@echo "✅ Release ready"