# Contributing to yt-study

First off, thanks for taking the time to contribute! 🎉

`yt-study` is built with a focus on robustness, type safety, and code quality. We welcome bug reports, feature requests, and pull requests.

## 🛠 Development Setup

We use **[uv](https://github.com/astral-sh/uv)** for fast dependency management.

### 1. Clone the repository
```bash
git clone https://github.com/whoisjayd/yt-study.git
cd yt-study
```

### 2. Install dependencies
```bash
# This creates a virtualenv and installs dependencies
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

### Run Tests
```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=src/yt_study
```

### Run Linters
```bash
# Ruff (Linting)
uv run ruff check src tests

# Mypy (Type Checking)
uv run mypy src
```

---

## 📝 Pull Request Guidelines

1.  **Fork** the repository and create your branch from `main`.
2.  **Add Tests** for any new functionality or bug fix. Coverage should not decrease.
3.  **Ensure Code Quality**: Run `ruff` and `mypy` locally.
4.  **Format Code**: We follow standard Python formatting practices.
5.  **Descriptive Commits**: Use clear commit messages (e.g., `feat: add mistral support`, `fix: retry logic for playlists`).

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
