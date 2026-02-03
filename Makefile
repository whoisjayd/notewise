.PHONY: help install install-dev clean format lint type-check test test-cov test-watch build publish dev-setup all check

# Default target
help:
	@echo "yt-study - Makefile Commands"
	@echo ""
	@echo "Setup & Installation:"
	@echo "  make install        Install package in editable mode"
	@echo "  make install-dev    Install with development dependencies"
	@echo "  make dev-setup      Complete development environment setup"
	@echo ""
	@echo "Code Quality:"
	@echo "  make format         Format code with ruff"
	@echo "  make lint           Run ruff linter"
	@echo "  make type-check     Run mypy type checker"
	@echo "  make check          Run all checks (format, lint, type-check)"
	@echo ""
	@echo "Testing:"
	@echo "  make test           Run tests with pytest"
	@echo "  make test-cov       Run tests with coverage report"
	@echo "  make test-watch     Run tests in watch mode"
	@echo ""
	@echo "Build & Publish:"
	@echo "  make build          Build distribution packages"
	@echo "  make publish        Publish to PyPI (requires credentials)"
	@echo "  make clean          Clean build artifacts and cache"
	@echo ""
	@echo "Combined:"
	@echo "  make all            Run format, lint, type-check, and test"

# Installation
install:
	pip install -e .

install-dev:
	pip install -e . --dependency-groups dev

dev-setup: install-dev
	@echo "Development environment setup complete!"
	@echo "Run 'yt-study setup' to configure the application."

# Code formatting
format:
	@echo "Formatting code with ruff..."
	ruff format src/ tests/
	@echo "[OK] Formatting complete"

# Linting
lint:
	@echo "Running ruff linter..."
	ruff check src/ tests/ --fix
	@echo "[OK] Linting complete"

# Type checking
type-check:
	@echo "Running mypy type checker..."
	mypy src/yt_study
	@echo "[OK] Type checking complete"

# Combined checks
check: format lint type-check
	@echo "[OK] All checks passed"

# Testing
test:
	@echo "Running tests..."
	uv run python -m pytest tests/ -v

test-cov:
	@echo "Running tests with coverage..."
	uv run python -m pytest tests/ --cov=src/yt_study --cov-report=html --cov-report=term-missing -v
	@echo ""
	@echo "Coverage report generated in htmlcov/index.html"

test-watch:
	@echo "Running tests in watch mode..."
	uv run python -m pytest-watch tests/ -v

# Build
build: clean
	@echo "Building distribution packages..."
	pip install build
	python -m build
	@echo "[OK] Build complete - check dist/ folder"

# Publish to PyPI
publish: build
	@echo "Publishing to PyPI..."
	pip install twine
	twine upload dist/*

# Clean
clean:
	@echo "Cleaning build artifacts and cache..."
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	@echo "[OK] Cleanup complete"

# Run everything
all: format lint type-check test
	@echo ""
	@echo "[OK] All tasks completed successfully!"
