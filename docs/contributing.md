# 🤝 Contributing to yt-study

First off, thank you for considering contributing to `yt-study`! It's people like you that make it a great tool for everyone.

---

## 🏗️ Development Setup

We use **[uv](https://github.com/astral-sh/uv)** for high-performance dependency management.

### 1. Clone & Enter
```bash
git clone https://github.com/whoisjayd/yt-study.git
cd yt-study
```

### 2. Fast Install
```bash
# Install development dependencies
make install-dev

# Or using uv directly
uv sync
```

---

## 🧪 Quality Standards

We maintain high standards for code quality and type safety. Before submitting a PR, ensure all checks pass.

### The `make` Workflow
We provide a comprehensive `Makefile` to simplify common tasks:

| Command | Description |
| :--- | :--- |
| `make test` | Run the full test suite. |
| `make lint` | Check code style with Ruff. |
| `make type-check` | Verify types with Mypy. |
| `make format` | Automatically fix formatting issues. |
| `make all` | **Run everything** (Format -> Lint -> Type-check -> Test). |

---

## 📝 Pull Request Process

1.  **Branching**: Create a feature branch from `main`.
2.  **Coding**: Implement your changes. Please include docstrings and type hints.
3.  **Testing**: Add tests in the `tests/` directory for any new logic.
4.  **Verification**: Run `make all` to ensure you haven't introduced any regressions.
5.  **Commit**: Use descriptive commit messages (e.g., `feat: add mistral support`).
6.  **Submit**: Open a PR and describe your changes clearly.

---

## 📂 Repository Structure

- `src/yt_study/`: The main package.
  - `core/`: Core logic (LLM, YouTube, Events, Telemetry).
  - `pipeline/`: Async orchestration for video processing.
  - `ui/`: CLI (Rich) and Web (NiceGUI) interfaces.
- `docs/`: Documentation (MkDocs).
- `tests/`: Comprehensive test suite.

---

## 🐛 Reporting Bugs

When reporting bugs, please include:
- The command you ran.
- The full error message/stack trace.
- Your OS and Python version.

---

<p align="center">
  Thank you for helping make <b>yt-study</b> better! 🚀
</p>
