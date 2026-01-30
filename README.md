# 🎓 yt-study

[![PyPI version](https://badge.fury.io/py/yt-study.svg)](https://badge.fury.io/py/yt-study)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CI Status](https://github.com/whoisjayd/yt-study/actions/workflows/ci.yml/badge.svg)](https://github.com/whoisjayd/yt-study/actions)
[![Code Coverage](https://img.shields.io/badge/coverage-92%25-brightgreen)](https://github.com/whoisjayd/yt-study)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Mypy](https://img.shields.io/badge/mypy-checked-blue)](https://mypy-lang.org/)

> **Automated, AI-powered study notes from YouTube videos.**

`yt-study` is a command-line tool that transforms video content into structured, academic-quality Markdown notes. It handles transcripts, detects chapters, and preserves technical details like code snippets and SQL queries using state-of-the-art LLMs.

---

## Key Features

-   **Model Flexibility**: Use **Gemini**, **GPT-4**, **Claude**, or **Groq** via a unified interface.
-   **Chapter Intelligence**: Automatically splits long videos (>1hr) into separate, detailed chapter notes.
-   **Deep Context**: Processes massive transcripts (100k+ tokens) without summarization loss using recursive chunking.
-   **Universal Language**: Translates foreign content (e.g., Hindi, Spanish) directly into English notes.
-   **Robust Batch Processing**: Handle playlists or URL lists with a rich TUI dashboard that dynamically adjusts to your workload.
-   **IP Block Handling**: Gracefully detects YouTube rate limits and pauses/alerts without crashing.
-   **Developer Ready**: Fully type-checked (Mypy), linted (Ruff), and tested (100% pass rate, >90% coverage).

---

## Installation

Requires Python 3.10 or higher.

```bash
pip install yt-study
```

---

## Quick Start

### 1. Configure

Run the interactive wizard to set up your LLM provider and API keys.

```bash
yt-study setup
```

### 2. Run

Generate notes for a single video:

```bash
yt-study process "https://youtube.com/watch?v=VIDEO_ID"
```

Or an entire playlist:

```bash
yt-study process "https://youtube.com/playlist?list=PLAYLIST_ID"
```

---

## Documentation

Full documentation is available in the [`docs/`](docs/) directory.

-   [**Installation Guide**](docs/installation.md)
-   [**Configuration & Models**](docs/configuration.md)
-   [**Usage & CLI Options**](docs/usage.md)
-   [**Architecture**](docs/architecture.md)

---

## Output Example

Notes are organized automatically:

```
output/
└── Complete Python Course/
    ├── 01_Introduction.md
    ├── 02_Data_Types.md
    └── 03_Control_Flow.md
```

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details on setting up the development environment.

## License

MIT © [Jaydeep Solanki](https://github.com/whoisjayd)
