# 🎓 yt-study

[![PyPI version](https://badge.fury.io/py/yt-study.svg)](https://badge.fury.io/py/yt-study)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CI Status](https://github.com/whoisjayd/yt-study/actions/workflows/ci.yml/badge.svg)](https://github.com/whoisjayd/yt-study/actions)

> **Convert YouTube videos and playlists into comprehensive, academic-grade study notes using AI.**

`yt-study` is a powerful CLI tool that transforms educational video content into structured, high-quality study materials. It supports massive videos (10h+), playlists, and multiple languages, using state-of-the-art LLMs.

---

## ✨ Features

- **🧠 Multi-Model Support**: Works with Gemini 1.5/2.0, GPT-4o, Claude 3.5, Groq, and more via LiteLLM.
- **📚 Chapter-Aware**: Automatically detects chapters in long videos (>1hr) and creates separate, detailed notes for each.
- **🧩 Smart Chunking**:  Robustly handles transcripts of any length (even 20k+ tokens) without losing context.
- **🌍 Auto-Translation**: Processes videos in any language (e.g., Hindi, Spanish) and generates notes in **English**.
- **💻 SQL & Code Preservation**: Specifically tuned to preserve code blocks, SQL schemas, and technical syntax.
- **⚡ Robust Pipeline**: Process playlists sequentially with automatic retries for maximum reliability.

---

## 🚀 Quick Start

### 1. Installation

```bash
pip install yt-study
```

### 2. Setup (One-time)

Run the interactive wizard to configure your preferred LLM and API keys:

```bash
yt-study setup
```

### 3. Generate Notes

**Single Video:**
```bash
yt-study process "https://youtube.com/watch?v=VIDEO_ID"
```

**Entire Playlist:**
```bash
yt-study process "https://youtube.com/playlist?list=PLAYLIST_ID"
```

---

## 🛠 CLI Reference

**Primary Command:**
`yt-study [COMMAND] [OPTIONS]`

| Command | Description | Usage Example |
| :--- | :--- | :--- |
| **`process`** | Generate notes from URL | `yt-study process "URL"` |
| **`setup`** | Configure API keys & model | `yt-study setup` |
| **`config-path`** | Show config file location | `yt-study config-path` |
| **`version`** | Show version info | `yt-study version` |

### **`process` Options**

| Option | Description |
| :--- | :--- |
| `--model <name>` / `-m` | Override default model (e.g. `gpt-4o`) |
| `--language <code>` / `-l` | Preferred transcript language (default: `en`). Can be used multiple times. |
| `--output <path>` / `-o` | Custom output directory |
| `--help` | Show help message |

**Example with options:**
```bash
yt-study process "URL" --model anthropic/claude-3-5-sonnet-20241022 --output ./my-course-notes
```

---

## 📂 Output Structure

Organized automatically for easy navigation.

**📺 Single Video**
```
output/
└── Video Title/
    └── Video Title.md  # Comprehensive notes
```

**📖 Long Video (Chaptered)**
```
output/
└── Complete DBMS Course/
    ├── 01_Introduction.md
    ├── 02_ER_Diagrams.md
    └── 03_Normalization.md
```

**📑 Playlist**
```
output/
└── Playlist Name/
    ├── Video 1.md
    ├── Video 2.md
    └── Video 3.md
```

---

## ⚙️ Configuration

Config is stored in `~/.yt-study/config.env`.

**Supported Providers:**
- **Google Gemini** (Recommended for free tier)
- **OpenAI**
- **Anthropic**
- **Groq**
- **Mistral**
- **xAI (Grok)**

To re-run setup:
```bash
yt-study setup --force
```

---

## 👨‍💻 Development

Requirements: Python 3.10+

```bash
# Clone repo
git clone https://github.com/whoisjayd/yt-study.git
cd yt-study

# Install dependencies (using uv is recommended)
pip install uv
uv sync

# Run tests
uv run pytest

# Run locally
uv run yt-study --help
```