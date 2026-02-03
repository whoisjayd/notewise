# Contributing to yt-study

First off, thanks for taking the time to contribute! 🎉

`yt-study` is built with a focus on robustness, type safety, and code quality. We welcome bug reports, feature requests, and pull requests.

## 🛠 Development Setup

We use **[uv](https://github.com/astral-sh/uv)** for fast dependency management and **Makefile** for streamlined development workflows.

### 1. Clone the repository
```bash
git clone https://github.com/whoisjayd/yt-study.git
cd yt-study
```

### 2. Install dependencies
```bash
# Install the package with development dependencies
make install-dev

# Or manually with uv
uv sync
```

### 3. Activate virtualenv
```bash
# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate
```

---

## 🧪 Testing & Code Quality

We strictly enforce type safety and linting. **All checks must pass** before a PR can be merged.

### Quick Commands (Using Makefile)

```bash
# Run all tests
make test

# Run tests with coverage report
make test-cov

# Format code
make format

# Run linter
make lint

# Run type checker
make type-check

# Run all checks (format + lint + type-check)
make check

# Run everything (format + lint + type-check + test)
make all
```

### Manual Commands (Without Makefile)

```bash
# Run all tests
uv run python -m pytest

# Run with coverage report
uv run python -m pytest --cov=src/yt_study

# Ruff (Linting)
ruff check src tests --fix

# Ruff (Formatting)
ruff format src tests

# Mypy (Type Checking)
mypy src/yt_study
```

### View All Available Commands
```bash
make help
```

---

## 📝 Pull Request Guidelines

1.  **Fork** the repository and create your branch from `main`.
2.  **Add Tests** for any new functionality or bug fix. Coverage should not decrease.
3.  **Ensure Code Quality**: Run `make check` locally before pushing.
4.  **Run Tests**: Ensure `make test` passes with all 99+ tests.
5.  **Descriptive Commits**: Use clear commit messages (e.g., `feat: add mistral support`, `fix: retry logic for playlists`).

### Before Submitting Your PR

Run this single command to verify everything passes:

```bash
make all
```

This will:
- Format your code
- Run the linter
- Type-check your code
- Run all tests

### Directory Structure

- `src/yt_study/`: Source code
    - `cli.py`: Entry point (Typer app)
    - `pipeline/`: Core orchestration logic
    - `llm/`: LLM integration (LiteLLM wrapper)
    - `youtube/`: YouTube data extraction logic
    - `ui/`: Rich TUI components
- `tests/`: Test suite (mirrors source structure)

---

## 🐛 Reporting Bugs

Please include:
1.  Command run (e.g. `yt-study process ...`)
2.  Error output / Stack trace
3.  Python version
4.  OS environment

Thank you for contributing!
