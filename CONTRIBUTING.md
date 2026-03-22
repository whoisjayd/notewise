# Contributing to yt-study

Thank you for taking the time to contribute! This document covers everything you need to get your environment set up, understand how the project is structured, and submit high-quality contributions.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How to Contribute](#how-to-contribute)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Code Quality Standards](#code-quality-standards)
- [Testing](#testing)
- [Commit Messages](#commit-messages)
- [Pull Request Process](#pull-request-process)
- [Reporting Bugs](#reporting-bugs)
- [Requesting Features](#requesting-features)

---

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold it. Please report unacceptable behaviour to [contactjaydeepsolanki@gmail.com](mailto:contactjaydeepsolanki@gmail.com).

---

## How to Contribute

There are many ways to help:

- **Bug reports** — open a [bug report issue](https://github.com/whoisjayd/yt-study/issues/new?template=bug_report.yml)
- **Feature requests** — open a [feature request issue](https://github.com/whoisjayd/yt-study/issues/new?template=feature_request.yml)
- **Documentation fixes** — typos, unclear explanations, missing examples
- **Code contributions** — bug fixes, new features, performance improvements
- **Tests** — increase coverage, add edge cases

If you plan to work on something large, **open an issue first** so we can discuss the design before you invest time writing code.

---

## Development Setup

### Prerequisites

- Python **3.10** or newer
- [uv](https://github.com/astral-sh/uv) — the project's package manager

### Clone and Install

```bash
git clone https://github.com/whoisjayd/yt-study
cd yt-study
uv sync --dev
```

This installs all runtime and development dependencies into an isolated virtual environment.

### Install Pre-commit Hooks

```bash
uv run pre-commit install
```

The hooks run automatically on `git commit` and enforce formatting and single-line commit messages.

### Verify the Setup

```bash
uv run yt-study version
```

---

## Project Structure

```
yt-study/
├── src/yt_study/            # Application source (src layout)
│   ├── __init__.py          # Package version
│   ├── __main__.py          # Entry point (python -m yt_study)
│   ├── _constants.py        # Global constants
│   ├── config.py            # Pydantic-settings configuration
│   ├── errors.py            # All custom exceptions
│   ├── logging.py           # structlog configuration
│   ├── utils.py             # General utilities (filename sanitisation, etc.)
│   ├── cli/                 # Typer CLI layer
│   │   ├── app.py           # Command definitions
│   │   ├── _admin.py        # Admin/info command implementations
│   │   ├── _banner.py       # ASCII banner
│   │   ├── _batch_runner.py # Batch processing orchestration
│   │   ├── _context.py      # Shared CLI context
│   │   ├── _display.py      # Rich display helpers
│   │   ├── _formatters.py   # Output formatting
│   │   ├── _runtime.py      # CliProcessRunner
│   │   ├── _single_runner.py# Single-video run orchestration
│   │   ├── _source_resolution.py # URL/batch-file source handling
│   │   └── _types.py        # CLI-layer type aliases
│   ├── domain/              # Domain value objects (no I/O)
│   │   ├── events.py        # PipelineEvent & EventType enum
│   │   ├── results.py       # PipelineResult & PipelineMetrics
│   │   └── youtube.py       # YouTube domain objects (VideoTranscript, etc.)
│   ├── llm/                 # LLM provider abstraction
│   │   ├── provider.py      # LLMProvider & UsageTotals
│   │   └── prompts/         # Prompt templates
│   │       ├── study_notes.py
│   │       ├── chapter_notes.py
│   │       └── quiz.py
│   ├── pipeline/            # Core processing pipeline
│   │   ├── core.py          # CorePipeline class
│   │   ├── generation.py    # StudyMaterialGenerator
│   │   ├── _execution.py    # Single-video & batch execution
│   │   ├── _artifacts.py    # Quiz generation & transcript export
│   │   ├── _helpers.py      # Utility functions for pipeline
│   │   ├── _limiter.py      # YouTube rate limiter
│   │   └── _state.py        # PipelineSharedState
│   ├── storage/             # SQLite persistence layer
│   │   ├── repository.py    # DatabaseRepository (SQLAlchemy)
│   │   ├── models.py        # ORM models
│   │   ├── schemas.py       # Pydantic schemas
│   │   └── migrations.py    # Schema migrations
│   ├── ui/                  # Rich terminal UI
│   │   ├── dashboard.py     # PipelineDashboard (live progress)
│   │   └── setup_wizard.py  # Interactive setup wizard
│   └── youtube/             # YouTube extraction
│       ├── parser.py        # URL & ID parsing
│       ├── transcript.py    # Transcript fetching
│       ├── metadata.py      # Video/playlist metadata
│       ├── playlist.py      # Playlist video extraction
│       ├── _availability.py # Availability checks
│       ├── _constants.py    # YouTube-specific constants
│       └── extractor/       # Low-level HTTP extractor client
├── tests/                   # Test suite
│   ├── unit/                # Unit tests (mocked I/O)
│   ├── integration/         # Integration tests (real SQLite, etc.)
│   ├── e2e/                 # End-to-end smoke tests
│   └── conftest.py          # Shared fixtures
├── scripts/
│   └── hooks/               # Git hook scripts
├── .github/
│   ├── workflows/           # CI/CD workflows
│   └── ISSUE_TEMPLATE/      # Issue templates
├── Dockerfile               # Two-stage production image
├── Makefile                 # Developer workflow shortcuts
├── pyproject.toml           # Project metadata & tool config
└── uv.lock                  # Locked dependencies
```

### Key Design Principles

- **Src layout** — all importable code lives under `src/yt_study/`
- **Domain objects are I/O-free** — nothing in `domain/` touches the network or disk
- **All exceptions in one place** — define custom exceptions only in `errors.py`
- **Lazy imports in CLI** — heavy dependencies are imported inside command functions to keep startup fast
- **Configuration via Pydantic Settings** — `AppSettings` in `config.py`; all defaults are in `_constants.py`

---

## Code Quality Standards

The project enforces a strict quality baseline through Ruff, ty (type checker), Bandit (security), and deptry (dependency hygiene).

### Run All Quality Checks

```bash
make quality       # lint, format-check, type-check, deps-check, security
```

### Auto-fix Formatting and Lint

```bash
make fix           # ruff format + ruff check --fix
```

### Individual Commands

```bash
# Formatting
uv run ruff format src/yt_study tests

# Lint
uv run ruff check src/yt_study tests

# Type checking
uv run ty check src/yt_study

# Security scanning
uv run bandit -c pyproject.toml -r src/yt_study

# Dependency hygiene
uv run deptry .
```

### Style Rules

- Line length: **88** characters (Ruff default)
- Target: **Python 3.10** syntax
- Quote style: **double quotes**
- Isort: first-party imports in a separate section
- No unused arguments (ARG rule) — prefix intentionally unused params with `_`

---

## Testing

The test suite is split into three layers:

| Layer | Path | Description |
|-------|------|-------------|
| Unit | `tests/unit/` | Fully mocked — fast, no network, no disk |
| Integration | `tests/integration/` | Uses real SQLite and filesystem |
| E2E | `tests/e2e/` | Public smoke tests against YouTube |

### Run Tests

```bash
# Full test suite (parallel)
make test

# Unit tests only with coverage
make test-unit

# Integration tests only
make test-integration

# Single test file
uv run pytest tests/unit/cli/test_display.py -v
```

### Coverage

The CI enforces **90% minimum coverage** on unit tests. Check coverage locally:

```bash
uv run python -m pytest --cov=src/yt_study --cov-report=html
open htmlcov/index.html
```

### Writing Tests

- **Unit tests must not make network calls.** Use `pytest-mock` (`mocker.patch`) to patch YouTube extraction and LLM calls.
- **Fixtures** shared across the test suite live in `tests/conftest.py`.
- **Async tests** use `pytest-asyncio` — mark coroutines with `async def test_...` (the `asyncio_mode = "auto"` setting in `pyproject.toml` handles the rest).
- Test files, classes, and functions must follow the naming convention: `test_*.py`, `Test*`, `test_*`.

---

## Commit Messages

All commit messages must be a **single line** of 72 characters or fewer. This is enforced by the pre-commit hook at `scripts/hooks/check-single-line-commit.sh`.

The recommended format follows [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>
```

Examples:

```
feat(cli): add --export-transcript option to process command
fix(pipeline): handle transcript fetch retry on IPBlockError
docs: update README quick start section
test(storage): add coverage for cache prune edge cases
refactor(llm): extract UsageTotals into provider module
chore: bump litellm to 1.81.1
```

Common types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`, `perf`, `style`.

---

## Pull Request Process

1. **Fork** the repository and create a branch from `main`:
   ```bash
   git checkout -b feat/my-feature
   ```

2. **Write your changes** — code, tests, and documentation together.

3. **Run the full quality suite** locally before pushing:
   ```bash
   make ci
   ```

4. **Push and open a PR** against `main`. Fill in the PR template completely.

5. **CI must pass** — the `pr-gate.yml` workflow runs format, lint, type-check, and the full test matrix.

6. **One review approval** is required before merge.

7. **Squash merge** is preferred for a clean history.

### PR Checklist

- [ ] Tests added or updated for the change
- [ ] `make ci` passes locally
- [ ] Documentation updated if the public interface changed
- [ ] Commit message follows the single-line convention

---

## Reporting Bugs

Use the [bug report template](https://github.com/whoisjayd/yt-study/issues/new?template=bug_report.yml). Please include:

- Your OS and Python version (`python --version`)
- The yt-study version (`yt-study version`)
- The command you ran (redact any API keys)
- The full error output / log file content

The current session log is shown in error messages; you can also find it with `yt-study logs --tail 50`.

---

## Requesting Features

Use the [feature request template](https://github.com/whoisjayd/yt-study/issues/new?template=feature_request.yml). Describe the problem you're trying to solve, not just the solution.

---

## Security Issues

Please **do not** open a public issue for security vulnerabilities. See [SECURITY.md](SECURITY.md) for the responsible disclosure process.
