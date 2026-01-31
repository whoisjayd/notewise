# 🎓 yt-study

[![PyPI version](https://badge.fury.io/py/yt-study.svg)](https://badge.fury.io/py/yt-study)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CI Status](https://github.com/whoisjayd/yt-study/actions/workflows/ci-main.yml/badge.svg)](https://github.com/whoisjayd/yt-study/actions)
[![Code Coverage](https://codecov.io/gh/whoisjayd/yt-study/branch/main/graph/badge.svg?token=CODECOV_TOKEN)](https://codecov.io/gh/whoisjayd/yt-study)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Mypy](https://img.shields.io/badge/mypy-checked-blue)](https://mypy-lang.org/)

> **Automated, AI-powered study notes from YouTube videos.**

`yt-study` is a command-line tool that transforms video content into structured, academic-quality Markdown notes. It handles transcripts, detects chapters, and preserves technical details like code snippets and SQL queries using state-of-the-art LLMs.

### 🛡️ Badges Explained
- **CI Status**: Shows if our full validation suite is passing on the `main` branch.
- **Code Coverage**: Indicates the percentage of code covered by tests (we aim for >90%).
- **Ruff/Mypy**: Certifies that the code adheres to strict linting and type-checking standards.

---

## 🏗 Architecture Overview

`yt-study` is built as a modular pipeline:
1.  **CLI Layer** (`src/yt_study/cli.py`): Entry point using Typer and Rich for TUI.
2.  **Orchestrator** (`src/yt_study/pipeline/`): Manages async workers, rate limiting, and progress state.
3.  **YouTube Provider** (`src/yt_study/youtube/`): Handles transcript fetching (with cookie auth) and metadata extraction.
4.  **LLM Provider** (`src/yt_study/llm/`): Interfaces with Gemini, ChatGPT, Claude, etc., via LiteLLM.
5.  **Data Layer** (`src/yt_study/db.py`): SQLite backend for caching and metrics (coming in v0.2.0).

---

## ✨ Features

-   **Model Flexibility**: Use **Gemini**, **ChatGPT**, **Claude**, or **Groq** and **Many More** via a unified interface.
-   **Chapter Intelligence**: Automatically splits long videos (>1hr) into separate, detailed chapter notes.
-   **Deep Context**: Processes massive transcripts (100k+ tokens) without summarization loss using recursive chunking.
-   **Universal Language**: Translates foreign content (e.g., Hindi, Spanish) directly into English notes.
-   **Robust Batch Processing**: Handle playlists or URL lists with a rich TUI dashboard.
-   **IP Block Handling**: Gracefully detects YouTube rate limits and pauses/alerts without crashing.
-   **Developer Ready**: Fully type-checked (Mypy), linted (Ruff), and tested.

---

## 🚀 Quick Start

### 1. Installation

Requires Python 3.10 or higher.

```bash
pip install yt-study
```

### 2. Configure

Run the interactive wizard to set up your LLM provider and API keys.

```bash
yt-study setup
```

### 3. Run

Generate notes for a single video:

```bash
yt-study process "https://youtube.com/watch?v=VIDEO_ID"
```

Or an entire playlist:

```bash
yt-study process "https://youtube.com/playlist?list=PLAYLIST_ID"
```

---

## ⚙️ Configuration

Full configuration options are detailed in [wiki/Configuration.md](wiki/Configuration.md).

Key environment variables:
- `GEMINI_API_KEY`, `OPENAI_API_KEY`, etc. for LLM access.
- `MAX_CONCURRENT_VIDEOS`: Control parallel worker count (default: 5).

---

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details on setting up the development environment.

We abide by our [Code of Conduct](CODE_OF_CONDUCT.md) and [Governance](GOVERNANCE.md) policies.

### Entry Points
- **Good First Issues**: Check our [Issues page](https://github.com/whoisjayd/yt-study/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) for beginner-friendly tasks.
- **Discussions**: Join the conversation in GitHub Discussions.

---

## 🛣️ Roadmap

See [Issues](https://github.com/whoisjayd/yt-study/issues) for the full backlog.

---

## 🔒 Security

For vulnerability reporting, please refer to [SECURITY.md](SECURITY.md).

---

## License

MIT © [Jaydeep Solanki](https://github.com/whoisjayd)
