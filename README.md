# 🎓 yt-study

<p align="center">
  <img src="https://raw.githubusercontent.com/whoisjayd/yt-study/main/docs/assets/logo.png" alt="yt-study logo" width="200">
</p>

<p align="center">
  <b>Automated, AI-powered study notes from YouTube videos.</b>
</p>

<p align="center">
  <a href="https://badge.fury.io/py/yt-study"><img src="https://badge.fury.io/py/yt-study.svg" alt="PyPI version"></a>
  <a href="https://github.com/whoisjayd/yt-study/actions/workflows/ci-main.yml"><img src="https://github.com/whoisjayd/yt-study/actions/workflows/ci-main.yml/badge.svg" alt="CI Status"></a>
  <a href="https://codecov.io/gh/whoisjayd/yt-study"><img src="https://codecov.io/gh/whoisjayd/yt-study/branch/main/graph/badge.svg?token=CODECOV_TOKEN" alt="Code Coverage"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+"></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff"></a>
</p>

---

`yt-study` is a powerful command-line tool that transforms YouTube video content into structured, academic-quality Markdown notes. It handles transcripts, detects logical chapters, and preserves technical details like code snippets and mathematical formulas using state-of-the-art LLMs.

## ✨ Key Features

| Feature | Description |
| :--- | :--- |
| 🤖 **Multi-Model Support** | Seamlessly use Gemini, Claude, GPT-4, or Groq via LiteLLM. |
| 🧠 **Smart Chaptering** | Automatically detects logical sections for videos without native chapters. |
| 📝 **Academic Quality** | Generates detailed notes with code blocks, tables, and structured summaries. |
| 📂 **Organized Output** | Creates a clean directory structure for each video and playlist. |
| ⚡ **Parallel Processing** | Handles large playlists efficiently with configurable concurrency. |
| 🛠 **Developer Friendly** | Fully type-checked, tested, and easy to extend. |

## 🚀 Quick Start

### 1. Installation

```bash
pip install yt-study
```

### 2. Initialization

Run the setup wizard to configure your preferred LLM provider and API keys:

```bash
yt-study setup
```

### 3. Generate Notes

Transform any video into structured notes instantly:

```bash
# Process a single video
yt-study process "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Process an entire playlist
yt-study process "https://www.youtube.com/playlist?list=PL..."
```

## 📖 Documentation

For full installation guides, CLI reference, and advanced configuration, visit our documentation:

👉 **[https://whoisjayd.github.io/yt-study/](https://whoisjayd.github.io/yt-study/)**

## 🤝 Contributing

Contributions are welcome! Whether it's a bug report, feature request, or a pull request, we appreciate your help in making `yt-study` better.

1. Clone the repo: `git clone https://github.com/whoisjayd/yt-study.git`
2. Install dev dependencies: `make install-dev`
3. Run checks: `make all`

Please see [CONTRIBUTING.md](CONTRIBUTING.md) for more details.

---

<p align="center">
  Built with ❤️ by <a href="https://github.com/whoisjayd">Jaydeep Solanki</a>
</p>
