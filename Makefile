# notewise Makefile
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
	FIND_CACHE := for /d /r . %%d in (.ruff_cache .ty_cache .pytest_cache) do @if exist "%%d" $(RM_DIR) "%%d" 2>$(DEVNULL)
	FIND_EGG := for /d /r . %%d in (*.egg-info) do @if exist "%%d" $(RM_DIR) "%%d" 2>$(DEVNULL)
	FIND_EMPTY_DIRS := powershell -NoProfile -Command "Get-ChildItem -Directory -Recurse | Where-Object { (Get-ChildItem -Force -LiteralPath $${PSItem}.FullName | Measure-Object).Count -eq 0 -and $${PSItem}.FullName -notmatch '\\.venv\\' } | Sort-Object FullName -Descending | ForEach-Object { Remove-Item -LiteralPath $${PSItem}.FullName -Force -Recurse }"
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
	FIND_CACHE := find . -type d \( -name ".ruff_cache" -o -name ".ty_cache" -o -name ".pytest_cache" \) -exec rm -rf {} + 2>$(DEVNULL) || true
	FIND_EGG := find . -type d -name "*.egg-info" -exec rm -rf {} + 2>$(DEVNULL) || true
	FIND_EMPTY_DIRS := find . -type d -empty -not -path "./.venv/*" -not -path "./.venv" -exec rmdir {} + 2>$(DEVNULL) || true
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
TY := $(UV_RUN) ty
PYTEST := $(UV) run --no-sync python -m pytest
PYTEST_WATCH := $(UV_RUN) --with pytest-watch ptw
PYTEST_PARALLEL_FLAGS := -n auto --dist=loadfile
DEPTRY := $(UV_RUN) deptry
BANDIT := $(UV_RUN) bandit
TWINE := $(UV_RUN) --with twine twine
HELP_SCRIPT := scripts/make_help.py

# ==============================================================================
# Directory Configuration
# ==============================================================================
SRC_DIR := src
PKG_DIR := src/notewise
SCRIPTS_DIR := scripts
TEST_DIR := tests
UNIT_TEST_DIR := $(TEST_DIR)/unit
INTEGRATION_TEST_DIR := $(TEST_DIR)/integration
PY_FILES := $(PKG_DIR) $(TEST_DIR) $(SCRIPTS_DIR)
BUILD_DIR := build
DIST_DIR := dist
HTMLCOV_DIR := htmlcov
MAKEFILE_PATH := $(firstword $(MAKEFILE_LIST))

# ==============================================================================
# Shared Command Arguments
# ==============================================================================
PYTEST_ALL := $(PYTEST) $(TEST_DIR) $(PYTEST_PARALLEL_FLAGS)
COVERAGE_TERM_ARGS := --cov=$(PKG_DIR) --cov-report=term-missing
COVERAGE_CI_ARGS := $(COVERAGE_TERM_ARGS) --cov-fail-under=90 --cov-report=xml --cov-report=html

# ==============================================================================
# Target Groups
# ==============================================================================
QUALITY_CHECK_TARGETS := format-check lint-check type-check version-check deps-check security
QUALITY_FIX_TARGETS := format lint type-check version-check deps-check security
CLEAN_TARGETS := clean-cache clean-build clean-test

# ==============================================================================
# Phony Targets
# ==============================================================================
.PHONY: help sync install install-dev dev-setup \
	format format-check lint lint-check type-check version-check deps-check security \
	check verify fix audit quality pre-commit \
	hooks-install hooks-run \
	test test-unit test-integration test-fast test-cov test-watch test-failed test-verbose \
	coverage-open \
	build publish publish-test \
	show-deps show-outdated update-deps \
	$(CLEAN_TARGETS) clean-empty-dirs clean clean-all \
	all ci quick info

# ==============================================================================
# Help
# ==============================================================================
##@ Help
help: ## Show all developer tasks
	@$(PYTHON_CMD) $(HELP_SCRIPT) "$(DETECTED_OS)" "$(MAKEFILE_PATH)"

# ==============================================================================
# Setup
# ==============================================================================
##@ Setup
sync: ## Install all dependencies from lockfile
	$(UV) sync --all-extras --dev --frozen

install: ## Install package in editable mode
	$(PIP) install -e .

install-dev: ## Install package + dev dependencies + hooks
	$(PIP) install -e .
	$(UV) sync --all-extras --dev --frozen
	$(MAKE) hooks-install

dev-setup: install-dev ## Full contributor setup (alias for install-dev)

# ==============================================================================
# Code Quality - Formatting
# ==============================================================================
##@ Code Quality
format: ## Format code with ruff
	$(RUFF) format $(PY_FILES)

format-check: ## Check code formatting
	$(RUFF) format --check $(PY_FILES)

# ==============================================================================
# Code Quality - Linting
# ==============================================================================
lint: ## Run ruff with auto-fix
	$(RUFF) check $(PY_FILES) --fix --unsafe-fixes

lint-check: ## Run ruff without auto-fix
	$(RUFF) check $(PY_FILES)

# ==============================================================================
# Code Quality - Type Checking & Security
# ==============================================================================
type-check: ## Run ty type checker
	$(TY) check $(PKG_DIR)

version-check: ## Verify package version metadata is aligned
	$(UV_RUN) python scripts/check_version_sync.py

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

fix: format lint ## Auto-fix formatting and lint issues

audit: deps-check security ## Run deps-check + security

# ==============================================================================
# Git Hooks
# ==============================================================================
##@ Git Hooks
hooks-install: ## Install pre-commit hooks
	$(PRE_COMMIT) install --hook-type pre-commit --hook-type pre-push --hook-type commit-msg

hooks-run: ## Run pre-commit hooks on all files
	$(PRE_COMMIT) run --all-files
	$(PRE_COMMIT) run --hook-stage pre-push --all-files

pre-commit: check test-fast ## Run checks + fast tests before commit

# ==============================================================================
# Testing
# ==============================================================================
##@ Testing
test: ## Run full test suite
	$(PYTEST_ALL) -v

test-unit: ## Run unit tests with coverage
	$(PYTEST) $(UNIT_TEST_DIR) $(PYTEST_PARALLEL_FLAGS) $(COVERAGE_TERM_ARGS) -v

test-integration: ## Run integration tests
	$(PYTEST) $(INTEGRATION_TEST_DIR) $(PYTEST_PARALLEL_FLAGS) -v

test-fast: ## Run tests in quiet mode
	$(PYTEST_ALL) -q

test-cov: ## Run tests with coverage report
	$(PYTEST_ALL) $(COVERAGE_CI_ARGS) -v
	@echo ""
	@echo "Coverage reports generated:"
	@echo "  HTML: $(HTMLCOV_DIR)/index.html"
	@echo "  XML:  coverage.xml"

coverage-open: test-cov ## Generate and open HTML coverage report
	@$(OPEN) $(HTMLCOV_DIR)/index.html 2>$(DEVNULL) || echo "Open $(HTMLCOV_DIR)/index.html manually"

test-watch: ## Run tests in watch mode
	$(PYTEST_WATCH) $(TEST_DIR) -v

test-failed: ## Re-run only failed tests
	$(PYTEST_ALL) --lf -v

test-verbose: ## Run tests with maximal verbosity
	$(PYTEST) $(TEST_DIR) -vv -s

# ==============================================================================
# Build & Publish
# ==============================================================================
##@ Build & Publish
build: clean-build ## Build wheel and source distribution
	$(UV) build

publish: build ## Publish to PyPI
	$(TWINE) check $(DIST_DIR)/*
	$(TWINE) upload $(DIST_DIR)/*

publish-test: build ## Publish to TestPyPI
	$(TWINE) upload --repository testpypi $(DIST_DIR)/*

# ==============================================================================
# Dependency Management
# ==============================================================================
##@ Info
show-deps: ## Show installed dependencies
	$(UV) pip list

show-outdated: ## Show outdated dependencies
	$(UV) pip list --outdated

update-deps: ## Update dependencies and lockfile
	$(UV) sync --all-extras --dev

# ==============================================================================
# Cleanup
# ==============================================================================
##@ Cleanup
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

clean-empty-dirs: ## Remove empty directories created by build and refactor churn
	@$(FIND_EMPTY_DIRS)

clean: $(CLEAN_TARGETS) clean-empty-dirs ## Remove all generated files

clean-all: clean ## Remove generated files and virtualenvs
	$(call CHECK_DIR,.venv)
	$(call CHECK_DIR,venv)
	$(call CHECK_DIR,env)

# ==============================================================================
# Info
# ==============================================================================
##@ Info
info: ## Show tool and interpreter versions
	@echo "OS: $(DETECTED_OS)"
	@echo ""
	@$(PYTHON_CMD) --version 2>$(DEVNULL) || echo "Python: not found"
	@$(UV) --version 2>$(DEVNULL) || echo "uv: not found"
	@$(RUFF) --version 2>$(DEVNULL) || echo "ruff: not found"
	@$(TY) --version 2>$(DEVNULL) || echo "ty: not found"
	@$(PYTEST) --version 2>$(DEVNULL) || echo "pytest: not found"

# ==============================================================================
# Workflow Bundles
# ==============================================================================
##@ Workflow Bundles
quick: format-check lint-check test-fast ## Fast pre-push validation

ci: check test-cov ## CI-equivalent validation

all: ci ## Alias for ci
