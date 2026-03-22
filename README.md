<div align="center">

# 🎓 yt-study

**Convert YouTube videos and playlists into comprehensive AI-powered study notes — from your terminal.**

<br />

<img src="https://img.shields.io/badge/version-0.2.6-4f86f7?style=flat-square" alt="version" /> <img src="https://img.shields.io/badge/status-beta-f59e0b?style=flat-square" alt="status" /> <img src="https://img.shields.io/badge/license-MIT--Attribution-10b981?style=flat-square" alt="license" /> <img src="https://img.shields.io/badge/python-3.10%20|%203.11%20|%203.12%20|%203.13-3776AB?style=flat-square&logo=python&logoColor=white" alt="python versions" /> <img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=flat-square" alt="ruff" /> <img src="https://img.shields.io/badge/type--checked-ty-7c3aed?style=flat-square" alt="ty" /> <img src="https://img.shields.io/github/actions/workflow/status/whoisjayd/yt-study/ci-main.yml?branch=main&style=flat-square&label=CI&logo=github" alt="CI" /> <img src="https://img.shields.io/codecov/c/github/whoisjayd/yt-study?style=flat-square&logo=codecov&logoColor=white&label=coverage" alt="coverage" /> <img src="https://img.shields.io/badge/coverage%20gate-%E2%89%A590%25-22c55e?style=flat-square" alt="coverage gate" /> <img src="https://img.shields.io/badge/LiteLLM-powered-ff6b35?style=flat-square" alt="litellm" /> <img src="https://img.shields.io/badge/packaged%20with-uv-de5fe9?style=flat-square" alt="uv" /> <img src="https://img.shields.io/badge/Docker-ghcr.io-2496ED?style=flat-square&logo=docker&logoColor=white" alt="docker" />

<br /><br />

[**Why yt-study?**](#-why-yt-study) · [**Quick Start**](#-quick-start) · [**Features**](#-features) · [**Installation**](#-installation) · [**Configuration**](#configuration) · [**Providers**](#-supported-providers) · [**Contributing**](CONTRIBUTING.md)

</div>

## 💡 Why yt-study?

YouTube has become one of the richest learning platforms on the planet — university lectures, conference talks, technical deep-dives, language lessons, and entire courses are all freely available. But video is a passive medium. You watch, you nod, and two days later the details are gone.

**yt-study was built to fix that gap.**

The idea is simple: your time watching a video is valuable. The notes that _should_ come from it — the structured, searchable, reviewable kind — shouldn't require an extra hour of your day. yt-study automates exactly that step. Point it at any YouTube URL and walk away with Markdown study notes that are deeper and more comprehensive than most people would write by hand.

**Where it shines:**

- 📚 **Students** catching up on lecture recordings or supplementing textbooks with YouTube explanations
- 🧑‍💻 **Developers** staying on top of conference talks, tutorials, and technical deep-dives without watching at 3x speed
- 🌍 **Language learners** extracting structured notes from native-language content
- 📋 **Researchers** quickly distilling hours of talks into organized, searchable reference material
- 🏢 **Teams** turning internal video presentations into shareable written documentation

The output isn't a transcript summary. It's structured, hierarchical Markdown — with headers, sub-topics, definitions, examples, and every concept explained in depth. Chapter-aware videos get per-chapter notes. Long courses produce an organized note file per session. Everything lands in your filesystem: portable, searchable, and permanently yours.

## ✨ Features

|                                        |                                                                                            |
| -------------------------------------- | ------------------------------------------------------------------------------------------ |
| 📹 **Single Video, Playlists & Batch** | Process one video, an entire playlist, or a `.txt` file of URLs in a single command        |
| 🤖 **Multi-Provider LLM Support**      | Works with Gemini, OpenAI, Anthropic, Groq, Mistral, Cohere, DeepSeek, and xAI via LiteLLM |
| 🗂️ **Chapter-Aware Notes**             | Automatically detects video chapters and generates separate, structured notes per chapter  |
| ❓ **Quiz Generation**                 | Optionally produce a ready-to-use multiple-choice quiz alongside each study guide          |
| 📝 **Transcript Export**               | Export raw transcripts as plain `.txt` or timestamped `.json`                              |
| ⚡ **Concurrent Processing**           | Configurable concurrency — process multiple videos and chapters simultaneously             |
| 💾 **Local SQLite Cache**              | Transcripts and run stats are cached; skip already-processed videos automatically          |
| 🖥️ **Rich Live Dashboard**             | Real-time progress UI with a `--no-ui` plain-output mode for CI/cron                       |
| 🐳 **Docker Ready**                    | Minimal two-stage Docker image for reproducible, stateless runs                            |
| 🔒 **Private Video Support**           | Pass a Netscape-format cookie file to process age-gated or login-required videos           |

## 🚀 Quick Start

### 1 · Install

```bash
pip install yt-study
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv tool install yt-study
```

### 2 · Configure

Run the interactive setup wizard once to store your LLM API key:

```bash
yt-study setup
```

This creates `~/.yt-study/config.env`. The default model is **Gemini 2.5 Flash** — grab a free key at [aistudio.google.com](https://aistudio.google.com/app/apikey).

### 3 · Generate Study Notes

```bash
# Single video
yt-study process "https://youtube.com/watch?v=VIDEO_ID"

# Full playlist
yt-study process "https://youtube.com/playlist?list=PLAYLIST_ID"

# Batch file (one URL per line)
yt-study process my-course-urls.txt -o ./course-notes
```

Notes are written as Markdown files in `./output/` (or your configured directory).

## 📦 Installation

### Requirements

- Python **3.10** or newer (3.10, 3.11, 3.12, and 3.13 are tested in CI)
- An API key for at least one [supported LLM provider](#-supported-providers)

### pip

```bash
pip install yt-study
```

### uv (recommended)

```bash
uv tool install yt-study
```

### Docker

```bash
docker pull ghcr.io/whoisjayd/yt-study:latest

docker run --rm \
  -e GEMINI_API_KEY="your_key" \
  -v "$(pwd)/output:/output" \
  ghcr.io/whoisjayd/yt-study:latest \
  process "https://youtube.com/watch?v=VIDEO_ID"
```

### Development Install

```bash
git clone https://github.com/whoisjayd/yt-study
cd yt-study
uv sync --dev
```

<a id="configuration"></a>

## ⚙️ Configuration

yt-study reads configuration from `~/.yt-study/config.env` (created by `yt-study setup`).
Environment variables always take precedence over the config file.

### Key Settings

| Key                           | Default                   | Description                        |
| ----------------------------- | ------------------------- | ---------------------------------- |
| `DEFAULT_MODEL`               | `gemini/gemini-2.5-flash` | LiteLLM-format model string        |
| `OUTPUT_DIR`                  | `./output`                | Where study notes are saved        |
| `TEMPERATURE`                 | `0.7`                     | LLM sampling temperature (0.0–1.0) |
| `MAX_TOKENS`                  | _(model default)_         | Max tokens per LLM response        |
| `MAX_CONCURRENT_VIDEOS`       | `5`                       | Parallel video processing limit    |
| `YOUTUBE_REQUESTS_PER_MINUTE` | `10`                      | YouTube request rate limit         |
| `YOUTUBE_COOKIE_FILE`         | _(none)_                  | Path to Netscape cookies file      |

Override any setting per-run via CLI flags — run `yt-study process --help` for all options.

### State Directory

All persistent state (config, cache, logs) lives in `~/.yt-study/` by default. Override with:

```bash
export YT_STUDY_HOME=/path/to/custom/dir
```

## 🤖 Supported Providers

yt-study uses [LiteLLM](https://github.com/BerriAI/litellm) — any model string LiteLLM supports works here.

| Provider      | Config Key          | Example Model String           |
| ------------- | ------------------- | ------------------------------ |
| Google Gemini | `GEMINI_API_KEY`    | `gemini/gemini-2.5-flash`      |
| OpenAI        | `OPENAI_API_KEY`    | `gpt-4o`                       |
| Anthropic     | `ANTHROPIC_API_KEY` | `claude-3-5-sonnet-20241022`   |
| Groq          | `GROQ_API_KEY`      | `groq/llama3-70b-8192`         |
| xAI           | `XAI_API_KEY`       | `xai/grok-2`                   |
| Mistral       | `MISTRAL_API_KEY`   | `mistral/mistral-large-latest` |
| Cohere        | `COHERE_API_KEY`    | `command-r-plus`               |
| DeepSeek      | `DEEPSEEK_API_KEY`  | `deepseek/deepseek-chat`       |

Use any provider with `--model`:

```bash
yt-study process "URL" --model claude-3-5-sonnet-20241022
```

## 🖥️ CLI Reference

```
yt-study [COMMAND] [OPTIONS]
```

| Command         | Description                                                |
| --------------- | ---------------------------------------------------------- |
| `process <url>` | Generate study notes from a video, playlist, or batch file |
| `setup`         | Run the interactive configuration wizard                   |
| `config`        | Display the current configuration (secrets masked)         |
| `stats`         | Show aggregate processing statistics                       |
| `history`       | List recently processed videos                             |
| `info [url]`    | Inspect a YouTube source or show runtime info              |
| `doctor`        | Run a health check on config, cache, and logs              |
| `edit-config`   | Open the config file in your editor                        |
| `cache`         | Manage the local SQLite cache                              |
| `logs`          | Inspect and manage session log files                       |
| `version`       | Print the installed version                                |

### `process` Options

```
yt-study process URL [OPTIONS]

  -m, --model TEXT           LLM model (overrides config)
  -o, --output PATH          Output directory (overrides config)
  -l, --language TEXT        Preferred transcript language (repeatable)
  -t, --temperature FLOAT    LLM temperature 0.0–1.0
  -k, --max-tokens INT       Max tokens per LLM response
  -F, --force                Re-process already-processed videos
      --no-ui                Plain stdout output (CI/cron friendly)
      --quiz                 Also generate a multiple-choice quiz
      --export-transcript    Export raw transcript: txt or json
      --cookie-file PATH     Netscape cookies file for private videos
```

## 📂 Output Structure

```
output/
├── Video Title/
│   ├── study_notes.md           # Full study notes
│   ├── quiz.md                  # (optional, --quiz)
│   └── transcript.txt           # (optional, --export-transcript txt)
└── Another Video Title/
    └── study_notes.md
```

For chapter-aware videos (>1 hour with chapters), notes are split by chapter:

```
output/
└── Long Course Title/
    ├── Chapter 01 - Introduction.md
    ├── Chapter 02 - Core Concepts.md
    └── ...
```

## 🐳 Docker

The image is published to GHCR on every release:

```bash
docker run --rm \
  -e GEMINI_API_KEY="your_key" \
  -v "$(pwd)/output:/output" \
  ghcr.io/whoisjayd/yt-study:latest \
  process "https://youtube.com/watch?v=VIDEO_ID" --no-ui
```

Mount `/output` to access generated files on the host. The container runs as a non-root user (uid 1001).

## 🛠️ Development

```bash
# Clone & install
git clone https://github.com/whoisjayd/yt-study
cd yt-study
uv sync --dev

# Run tests
make test

# Lint, format, type-check
make quality

# Full CI pipeline locally
make ci
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the complete contributor guide.

## 📋 Changelog

See [GitHub Releases](https://github.com/whoisjayd/yt-study/releases) for the full history.

## 📄 License

[MIT with Attribution](LICENSE) — free to use, modify, and distribute.
If you use yt-study in a project or build on top of it, you are required to include credit and a link back to this repository. See [LICENSE](LICENSE) for the full terms.

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

Found a bug? [Open an issue](https://github.com/whoisjayd/yt-study/issues/new/choose).
Have a security concern? See [SECURITY.md](SECURITY.md).

## 🙏 Thank You

yt-study is built on top of a great open-source ecosystem, and this project is deeply grateful to the maintainers behind those tools and libraries.

See [GRATITUDE.md](GRATITUDE.md) for full acknowledgements.

And most importantly — **thank you to everyone who has used yt-study, filed issues, suggested features, or contributed code.** Every star, bug report, and PR makes this better.

If yt-study helped you study smarter, learn faster, or just saved you some time — that's exactly why it was built. ⭐

<div align="center">
<br />
<sub>Built with ❤️ by <a href="https://github.com/whoisjayd">whoisjayd</a></sub>
<br />
<sub>If you use yt-study, please give credit — it takes two seconds and means a lot.</sub>
</div>
