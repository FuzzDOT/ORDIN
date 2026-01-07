# =============================================================================
# ORDIN Backend - Makefile
# =============================================================================
# Common development tasks for the ORDIN backend service.
# Usage: make <target>
# =============================================================================

.PHONY: help install install-dev run dev test lint format typecheck clean docker-build docker-run

# Default target
help:
	@echo "ORDIN Backend - Available Commands"
	@echo "==================================="
	@echo "  make install      Install production dependencies"
	@echo "  make install-dev  Install development dependencies"
	@echo "  make run          Run production server"
	@echo "  make dev          Run development server with auto-reload"
	@echo "  make test         Run test suite"
	@echo "  make lint         Run linters"
	@echo "  make format       Format code with black and isort"
	@echo "  make typecheck    Run mypy type checking"
	@echo "  make clean        Remove build artifacts"
	@echo "  make docker-build Build Docker image"
	@echo "  make docker-run   Run Docker container"

# Installation
install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt
	pre-commit install

# Running
run:
	uvicorn app.main:app --host 0.0.0.0 --port 8000

dev:
	python run.py --reload

# Testing
test:
	pytest -v

test-cov:
	pytest --cov=app --cov-report=html --cov-report=term-missing

# Code Quality
lint:
	ruff check app tests

format:
	black app tests
	isort app tests

typecheck:
	mypy app

check: lint typecheck test
	@echo "All checks passed!"

# Cleanup
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true

# Docker
docker-build:
	docker build -t ordin-backend:latest .

docker-run:
	docker run -p 8000:8000 --env-file .env ordin-backend:latest
