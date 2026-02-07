# yt-study Makefile
# Cross-platform development workflow for Linux, macOS, and Windows

# ==============================================================================
# Platform Detection
# ==============================================================================
ifeq ($(OS),Windows_NT)
	DETECTED_OS := Windows
	SHELL := cmd.exe
	.SHELLFLAGS := /c
	DEVNULL := NUL
	OPEN := start
	RM_FILE := del /Q /F
	RM_DIR := rmdir /S /Q
	FIND_PYCACHE := for /d /r . %%d in (__pycache__) do @if exist "%%d" $(RM_DIR) "%%d" 2>$(DEVNULL)
	FIND_CACHE := for /d /r . %%d in (.ruff_cache .mypy_cache .pytest_cache) do @if exist "%%d" $(RM_DIR) "%%d" 2>$(DEVNULL)
	FIND_EGG := for /d /r . %%d in (*.egg-info) do @if exist "%%d" $(RM_DIR) "%%d" 2>$(DEVNULL)
	FIND_PYC := del /S /Q *.pyc *.pyo 2>$(DEVNULL) || echo >$(DEVNULL)
	CHECK_DIR = @if exist $(1) $(RM_DIR) $(1) 2>$(DEVNULL)
	CHECK_FILE = @if exist $(1) $(RM_FILE) $(1) 2>$(DEVNULL)
	PYTHON_CMD := python
else
	DETECTED_OS := $(shell uname -s)
	SHELL := /bin/sh
	.SHELLFLAGS := -c
	DEVNULL := /dev/null
	RM_FILE := rm -f
	RM_DIR := rm -rf
	FIND_PYCACHE := find . -type d -name "__pycache__" -exec rm -rf {} + 2>$(DEVNULL) || true
	FIND_CACHE := find . -type d \( -name ".ruff_cache" -o -name ".mypy_cache" -o -name ".pytest_cache" \) -exec rm -rf {} + 2>$(DEVNULL) || true
	FIND_EGG := find . -type d -name "*.egg-info" -exec rm -rf {} + 2>$(DEVNULL) || true
	FIND_PYC := find . -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete 2>$(DEVNULL) || true
	CHECK_DIR = @$(RM_DIR) $(1) 2>$(DEVNULL) || true
	CHECK_FILE = @$(RM_FILE) $(1) 2>$(DEVNULL) || true
	PYTHON_CMD := python3
	ifeq ($(DETECTED_OS),Darwin)
		OPEN := open
	else ifeq ($(DETECTED_OS),Linux)
		OPEN := xdg-open
	else
		OPEN := echo "Open manually:"
	endif
endif

.DEFAULT_GOAL := help
.DELETE_ON_ERROR:
.SUFFIXES:

# ==============================================================================
# Tool Configuration
# ==============================================================================
UV := uv
UV_RUN := $(UV) run
PIP := $(UV) pip
PRE_COMMIT := $(UV_RUN) pre-commit
RUFF := $(UV_RUN) ruff
MYPY := $(UV_RUN) mypy
PYTEST := $(UV_RUN) pytest
DEPTRY := $(UV_RUN) deptry
BANDIT := $(UV_RUN) bandit

# ==============================================================================
# Directory Configuration
# ==============================================================================
SRC_DIR := src
PKG_DIR := src/yt_study
TEST_DIR := tests
BUILD_DIR := build
DIST_DIR := dist
HTMLCOV_DIR := htmlcov

# ==============================================================================
# Target Groups
# ==============================================================================
QUALITY_CHECK_TARGETS := format-check lint-check type-check deps-check security
QUALITY_FIX_TARGETS := format lint type-check deps-check security
CLEAN_TARGETS := clean-cache clean-build clean-test

# ==============================================================================
# Phony Targets
# ==============================================================================
.PHONY: help sync install install-dev dev-setup \
	format format-check lint lint-check type-check deps-check security \
	check verify audit quality pre-commit \
	hooks-install hooks-run \
	test test-fast test-cov test-watch test-failed test-verbose \
	coverage-open \
	build publish publish-test \
	show-deps show-outdated update-deps \
	$(CLEAN_TARGETS) clean clean-all \
	all ci quick info

# ==============================================================================
# Help
# ==============================================================================
help: ## Show all developer tasks
	@echo ""
	@echo "yt-study developer tasks (OS: $(DETECTED_OS))"
	@echo ""
	@echo "Setup:"
	@echo "  sync          Install all dependencies from lockfile"
	@echo "  install       Install package in editable mode"
	@echo "  install-dev   Install package + dev dependencies + hooks"
	@echo "  dev-setup     Full contributor setup (alias for install-dev)"
	@echo ""
	@echo "Code Quality:"
	@echo "  format        Format code with ruff"
	@echo "  format-check  Check code formatting"
	@echo "  lint          Run ruff with auto-fix"
	@echo "  lint-check    Run ruff without auto-fix"
	@echo "  type-check    Run mypy type checker"
	@echo "  deps-check    Detect unused/missing dependencies"
	@echo "  security      Run bandit security scan"
	@echo "  check         Run all quality checks (CI-safe)"
	@echo "  verify        Run all quality checks with auto-fixes"
	@echo "  audit         Run deps-check + security"
	@echo "  quality       Alias for check"
	@echo "  pre-commit    Run check + fast tests"
	@echo "  hooks-install Install git pre-commit hooks"
	@echo "  hooks-run     Run pre-commit on all files"
	@echo ""
	@echo "Testing:"
	@echo "  test          Run full test suite"
	@echo "  test-fast     Run tests in quiet mode"
	@echo "  test-cov      Run tests with coverage report"
	@echo "  coverage-open Generate and open HTML coverage report"
	@echo "  test-failed   Re-run only failed tests"
	@echo "  test-verbose  Run tests with maximal verbosity"
	@echo "  test-watch    Run tests in watch mode"
	@echo ""
	@echo "Build & Publish:"
	@echo "  build         Build wheel and source distribution"
	@echo "  publish       Publish to PyPI"
	@echo "  publish-test  Publish to TestPyPI"
	@echo ""
	@echo "Cleanup:"
	@echo "  clean         Remove generated files"
	@echo "  clean-all     Remove generated files + virtualenvs"
	@echo ""
	@echo "Info:"
	@echo "  show-deps     Show installed dependencies"
	@echo "  show-outdated Show outdated dependencies"
	@echo "  update-deps   Update dependencies and lockfile"
	@echo "  info          Show tool versions"
	@echo ""
	@echo "Workflow Bundles:"
	@echo "  quick         Fast validation (format-check + lint-check + test-fast)"
	@echo "  ci            CI validation (check + test-cov)"
	@echo "  all           Alias for ci"

# ==============================================================================
# Setup
# ==============================================================================
sync: ## Install all dependencies from lockfile
	$(UV) sync --all-extras --dev --frozen

install: ## Install package in editable mode
	$(PIP) install -e .

install-dev: ## Install package and development dependencies
	$(PIP) install -e .
	$(UV) sync --all-extras --dev --frozen
	$(MAKE) hooks-install

dev-setup: install-dev ## Full contributor setup

# ==============================================================================
# Code Quality - Formatting
# ==============================================================================
format: ## Format code with ruff
	$(RUFF) format $(PKG_DIR) $(TEST_DIR)

format-check: ## Check code formatting
	$(RUFF) format --check $(PKG_DIR) $(TEST_DIR)

# ==============================================================================
# Code Quality - Linting
# ==============================================================================
lint: ## Run ruff with auto-fix
	$(RUFF) check $(PKG_DIR) $(TEST_DIR) --fix --unsafe-fixes

lint-check: ## Run ruff without auto-fix
	$(RUFF) check $(PKG_DIR) $(TEST_DIR)

# ==============================================================================
# Code Quality - Type Checking & Security
# ==============================================================================
type-check: ## Run static type checks
	$(MYPY) $(PKG_DIR)

deps-check: ## Detect unused/missing dependencies
	$(DEPTRY) $(SRC_DIR)

security: ## Run security scan with bandit
	$(BANDIT) -c pyproject.toml -r $(PKG_DIR) --severity-level high

# ==============================================================================
# Code Quality - Bundles
# ==============================================================================
check: $(QUALITY_CHECK_TARGETS) ## Run all quality checks (CI-safe)

quality: check ## Alias for check

verify: $(QUALITY_FIX_TARGETS) ## Run all quality checks with auto-fixes

audit: deps-check security ## Run dependency and security audits

# ==============================================================================
# Git Hooks
# ==============================================================================
hooks-install: ## Install pre-commit hooks
	$(PRE_COMMIT) install --hook-type pre-commit --hook-type pre-push --hook-type commit-msg

hooks-run: ## Run pre-commit hooks on all files
	$(PRE_COMMIT) run --all-files
	$(PRE_COMMIT) run --hook-stage pre-push --all-files

pre-commit: check test-fast ## Run checks + fast tests before commit

# ==============================================================================
# Testing
# ==============================================================================
test: ## Run full test suite
	$(PYTEST) $(TEST_DIR) -v

test-fast: ## Run tests in quiet mode
	$(PYTEST) $(TEST_DIR) -q

test-cov: ## Run tests with coverage report
	$(PYTEST) $(TEST_DIR) \
		--cov=$(PKG_DIR) \
		--cov-report=term-missing \
		--cov-report=xml \
		--cov-report=html \
		-v
	@echo ""
	@echo "Coverage reports generated:"
	@echo "  HTML: $(HTMLCOV_DIR)/index.html"
	@echo "  XML:  coverage.xml"

coverage-open: test-cov ## Generate and open HTML coverage report
	@$(OPEN) $(HTMLCOV_DIR)/index.html 2>$(DEVNULL) || echo "Open $(HTMLCOV_DIR)/index.html manually"

test-watch: ## Run tests in watch mode
	$(UV_RUN) ptw $(TEST_DIR) -v

test-failed: ## Re-run only failed tests
	$(PYTEST) $(TEST_DIR) --lf -v

test-verbose: ## Run tests with maximal verbosity
	$(PYTEST) $(TEST_DIR) -vv -s

# ==============================================================================
# Build & Publish
# ==============================================================================
build: clean-build ## Build wheel and source distribution
	$(UV) build

publish: build ## Publish to PyPI
	$(PIP) install twine
	$(UV_RUN) twine check $(DIST_DIR)/*
	$(UV_RUN) twine upload $(DIST_DIR)/*

publish-test: build ## Publish to TestPyPI
	$(PIP) install twine
	$(UV_RUN) twine upload --repository testpypi $(DIST_DIR)/*

# ==============================================================================
# Dependency Management
# ==============================================================================
show-deps: ## Show installed dependencies
	$(UV) pip list

show-outdated: ## Show outdated dependencies
	$(UV) pip list --outdated

update-deps: ## Update dependencies and lockfile
	$(UV) sync --all-extras --dev

# ==============================================================================
# Cleanup
# ==============================================================================
clean-cache: ## Remove Python and tool caches
	@$(FIND_PYCACHE)
	@$(FIND_CACHE)
	@$(FIND_PYC)

clean-build: ## Remove build artifacts
	$(call CHECK_DIR,$(BUILD_DIR))
	$(call CHECK_DIR,$(DIST_DIR))
	@$(FIND_EGG)

clean-test: ## Remove test artifacts
	$(call CHECK_DIR,$(HTMLCOV_DIR))
	$(call CHECK_FILE,.coverage)
	$(call CHECK_FILE,coverage.xml)

clean: $(CLEAN_TARGETS) ## Remove all generated files

clean-all: clean ## Remove generated files and virtualenvs
	$(call CHECK_DIR,.venv)
	$(call CHECK_DIR,venv)
	$(call CHECK_DIR,env)

# ==============================================================================
# Info
# ==============================================================================
info: ## Show tool and interpreter versions
	@echo "OS: $(DETECTED_OS)"
	@echo ""
	@$(PYTHON_CMD) --version 2>$(DEVNULL) || echo "Python: not found"
	@$(UV) --version 2>$(DEVNULL) || echo "uv: not found"
	@$(RUFF) --version 2>$(DEVNULL) || echo "ruff: not found"
	@$(MYPY) --version 2>$(DEVNULL) || echo "mypy: not found"
	@$(PYTEST) --version 2>$(DEVNULL) || echo "pytest: not found"

# ==============================================================================
# Workflow Bundles
# ==============================================================================
quick: format-check lint-check test-fast ## Fast pre-push validation

ci: check test-cov ## CI-equivalent validation

all: ci ## Alias for ci
