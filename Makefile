.PHONY: help install install-dev clean format format-check lint lint-check type-check test test-cov test-cov-ci test-watch build publish dev-setup all check ci

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
	@echo "  make format-check   Check code formatting without fixing"
	@echo "  make lint           Run ruff linter with auto-fix"
	@echo "  make lint-check     Run ruff linter without fixing"
	@echo "  make type-check     Run mypy type checker"
	@echo "  make check          Run all checks (format, lint, type-check)"
	@echo "  make ci             Run CI checks (format-check, lint-check, type-check, test)"
	@echo ""
	@echo "Testing:"
	@echo "  make test           Run tests with pytest"
	@echo "  make test-cov       Run tests with coverage report"
	@echo "  make test-cov-ci    Run tests with XML coverage for CI"
	@echo "  make test-watch     Run tests in watch mode"
	@echo ""
	@echo "Build & Publish:"
	@echo "  make build          Build distribution packages"
	@echo "  make build-exe      Build standalone executable with compression"
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
	uv run ruff format src/ tests/
	@echo "[OK] Formatting complete"

format-check:
	@echo "Checking code formatting..."
	uv run ruff format --check src/ tests/
	@echo "[OK] Format check complete"

# Linting
lint:
	@echo "Running ruff linter..."
	uv run ruff check src/ tests/ --fix
	@echo "[OK] Linting complete"

lint-check:
	@echo "Checking linting..."
	uv run ruff check src/ tests/
	@echo "[OK] Lint check complete"

# Type checking
type-check:
	@echo "Running mypy type checker..."
	uv run mypy src/yt_study

# CI checks (no auto-fix)
ci: format-check lint-check type-check test
	@echo "[OK] CI checks passed"
	@echo "[OK] Type checking complete"

# Combined checks
check: format lint type-check
	@echo "[OK] All checks passed"

# Testing
test:
	@echo "Running tests..."
	uv run python -m pytest -n auto -v

test-cov:
	@echo "Running tests with coverage..."
	uv run python -m pytest -n auto -v --cov=src/yt_study --cov-report=html --cov-report=term-missing
	@echo ""
	@echo "Coverage report generated in htmlcov/index.html"

test-cov-ci:
	@echo "Running tests with coverage for CI..."
	uv run python -m pytest -n auto -v --cov=src/yt_study --cov-report=xml

# Build
build: clean
	@echo "Building distribution packages..."
	uv build
	@echo "[OK] Build complete - check dist/ folder"

build-exe:
	@echo "Building standalone executable..."
	@bash scripts/build_executable.sh

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
