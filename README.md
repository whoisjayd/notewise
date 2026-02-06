# 🎓 yt-study

<p align="center">
  <pre align="center">
                 _                     _             _
            _  _| |_      ___| |_ _  _| | _  _
           | || |  _|____(_-<|  _| || | |/ /| || |
            \_, |\__|____/__/ \__|\_,_|_|\_\ \_, |
            |__/                             |__/
  </pre>
</p>

<p align="center">
  <b>Automated, AI-powered study notes from YouTube videos.</b>
</p>

<p align="center">
  <a href="https://badge.fury.io/py/yt-study"><img src="https://badge.fury.io/py/yt-study.svg" alt="PyPI version"></a>
  <a href="https://github.com/whoisjayd/yt-study/actions/workflows/ci-main.yml"><img src="https://github.com/whoisjayd/yt-study/actions/workflows/ci-main.yml/badge.svg" alt="CI Status"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+"></a>
</p>

---

`yt-study` is a powerful command-line tool that transforms YouTube video content into structured, academic-quality Markdown notes. It handles transcripts, detects logical chapters, and preserves technical details like code snippets and mathematical formulas using state-of-the-art LLMs.

## ✨ Key Features

- 🤖 **Multi-Model Support**: Use Gemini, Claude, GPT-4, or Groq via LiteLLM.
- 🧠 **Smart Chaptering**: Automatically detects logical sections even for videos without native chapters.
- 🌐 **Web Visualizer**: Interactive dashboard to view and manage your study notes (`yt-study serve`).
- 📝 **Academic Quality**: Generates detailed notes with code blocks, tables, and structured summaries.
- ⚡ **Parallel Processing**: Efficiently process entire playlists with configurable concurrency.
- 📂 **Organized Output**: Clean directory structure for all generated content.

## 🚀 Quick Start

### 1. Installation

**Standard (pip):**
```bash
pip install yt-study
```

**Fast (uv):**
```bash
uv tool install yt-study
```

### 2. Initialization

Configure your preferred LLM provider and API keys:

```bash
yt-study setup
```

### 3. Generate Notes

Transform any video into structured notes instantly:

```bash
yt-study process "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

## 🖥️ Web Visualizer

`yt-study` comes with a built-in web dashboard to browse your notes library:

```bash
yt-study serve
```

Visit `http://localhost:8000` to explore your generated notes in a beautiful, searchable interface.

## ⚙️ Configuration

You can customize `yt-study` via environment variables or the `~/.yt-study/config.env` file.

| Variable | Description | Default |
| :--- | :--- | :--- |
| `DEFAULT_MODEL` | LLM model to use | `gemini/gemini-2.0-flash` |
| `OUTPUT_DIR` | Where to save notes | `./output` |
| `MAX_CONCURRENT_VIDEOS` | Parallel processing limit | `5` |
| `TEMPERATURE` | LLM creativity (0.0 to 1.0) | `0.7` |

<details>
<summary><b>View More Configuration Options</b></summary>

See the full list in the [Configuration Documentation](https://whoisjayd.github.io/yt-study/Configuration/).
</details>

## 📖 Documentation

For full installation guides, CLI reference, and advanced configuration, visit our documentation:

👉 **[https://whoisjayd.github.io/yt-study/](https://whoisjayd.github.io/yt-study/)**

## 🤝 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for more details.

---

<p align="center">
  Built with ❤️ by <a href="https://github.com/whoisjayd">Jaydeep Solanki</a>
</p>
