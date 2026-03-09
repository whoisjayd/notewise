# YT-Study

<div align="center">

[![PyPI](https://badge.fury.io/py/yt-study.svg)](https://badge.fury.io/py/yt-study)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/whoisjayd/yt-study/actions/workflows/ci-main.yml/badge.svg)](https://github.com/whoisjayd/yt-study/actions/workflows/ci-main.yml)
[![Coverage](https://codecov.io/gh/whoisjayd/yt-study/branch/main/graph/badge.svg)](https://codecov.io/gh/whoisjayd/yt-study)
[![Ruff](https://img.shields.io/badge/lint-ruff-46a758)](https://github.com/astral-sh/ruff)
[![Mypy](https://img.shields.io/badge/types-mypy-blue)](https://mypy-lang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

### Turn YouTube learning into structured study material.

Convert videos, playlists, and URL batches into clean Markdown notes with chapter-aware output, transcript fallback logic, and LLM-powered organization.

[Quick Start](#quick-start) • [Features](#features) • [How It Works](#how-it-works) • [Configuration](#configuration) • [Documentation](#documentation) • [Contributing](#contributing)

</div>

## At A Glance

| Category | Details |
| --- | --- |
| Inputs | Single video URL, playlist URL, or text file with one URL per line |
| Output | Markdown notes as one file per video or one file per chapter |
| Runtime | Async pipeline with concurrency-limited video workers |
| Core Stack | Python, Typer, Rich, LiteLLM, youtube-transcript-api, pytubefix |
| Config Path | `~/.yt-study/config.env` |
| Quality | Pytest, Ruff, MyPy, Bandit, Deptry, GitHub Actions |

## Why yt-study?

Video is useful for learning but weak for review. It is slow to scan, hard to search, and awkward to turn into reusable study assets. `yt-study` closes that gap by converting YouTube content into Markdown you can revisit, search, annotate, version, and move into tools like Obsidian or Notion.

Design priorities:

1. Fidelity over shallow summarization
2. Low-friction daily usage
3. Strong fallback behavior for real-world transcript issues
4. Reliable processing for long videos and playlists

## Features

### Content Ingestion

- Accepts single video URLs, playlist URLs, and batch files.
- Supports common YouTube URL forms including `watch`, `youtu.be`, `embed`, and `shorts`.
- Expands playlists into per-video jobs automatically.

### Transcript Reliability

- Prefers manual captions in the requested language list.
- Falls back to generated captions when needed.
- Can use other available languages and translate to English when possible.
- Retries transient failures and surfaces IP-block cases clearly.

### Note Generation

- Uses chapter-based generation for long videos with chapters.
- Uses transcript chunking plus overlap for large contexts.
- Produces Markdown suitable for notes repos, internal docs, or study vaults.

### Terminal Experience

- Rich live dashboard for active worker status and total progress.
- End-of-run summary for successes and failures.
- Batch mode support for repeated study queues.

### Engineering Quality

- Strict-ish typing via MyPy
- Formatting and linting via Ruff
- Security and dependency checks
- Cross-platform CI matrix

## Quick Start

### 1. Install

```bash
pip install yt-study
```

### 2. Run First-Time Setup

```bash
yt-study setup
```

This creates:

```text
~/.yt-study/config.env
```

### 3. Process Content

Single video:

```bash
yt-study process "https://youtube.com/watch?v=VIDEO_ID"
```

Playlist:

```bash
yt-study process "https://youtube.com/playlist?list=PLAYLIST_ID"
```

Batch file:

```bash
yt-study process urls.txt
```

### 4. Useful Commands

```bash
yt-study --help
yt-study setup --force
yt-study config-path
yt-study version
```

## Command Reference

Main command:

```bash
yt-study process [OPTIONS] URL_OR_FILE
```

Supported options:

```bash
--model / -m
--output / -o
--language / -l
--temperature / -t
--max-tokens / -k
```

Examples:

```bash
yt-study process "URL" -m gemini/gemini-2.0-flash
yt-study process "URL" -o ./course-notes
yt-study process "URL" -l hi -l en
yt-study process "URL" -t 0.4 -k 2500
```

## How It Works

```text
Input URL or batch file
  -> URL parsing
  -> metadata fetch (title, duration, chapters)
  -> transcript fetch with fallback logic
  -> strategy selection
     - chapter mode for long videos with chapters
     - chunked mode for everything else
  -> LLM generation
  -> Markdown write to output directory
```

Chapter mode activates when:

- duration is greater than `3600` seconds
- chapters are available

Otherwise the transcript flows through the chunker in `core/llm/generator.py`.

## Output Layout

Single-file output:

```text
output/
  My Awesome Video.md
```

Chapter-based output:

```text
output/
  My Awesome Video/
    01_Intro.md
    02_Core Concepts.md
    03_Implementation.md
```

Playlist output:

```text
output/
  Sanitized Playlist Name/
    Video One.md
    Video Two.md
    Long Video/
      01_Intro.md
      02_Deep Dive.md
```

Filenames are sanitized to remove filesystem-unsafe characters and trimmed to a safe length.

## Configuration

Runtime config location:

```text
~/.yt-study/config.env
```

Common supported keys:

- `DEFAULT_MODEL`
- `OUTPUT_DIR`
- `MAX_CONCURRENT_VIDEOS`
- `TEMPERATURE`
- `MAX_TOKENS`
- `GEMINI_API_KEY`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GROQ_API_KEY`
- `XAI_API_KEY`
- `MISTRAL_API_KEY`

Config behavior:

- loads `~/.yt-study/config.env`
- applies environment variable overrides
- syncs supported provider keys into `os.environ` for LiteLLM

Important:

- the repository root `.env` is not used by the runtime
- `.env.example` is only a reference for what belongs in `~/.yt-study/config.env`

## Troubleshooting

### Missing API key for selected model

Run:

```bash
yt-study setup --force
```

Then verify the matching provider key exists in `~/.yt-study/config.env`.

### Transcript unavailable

Try:

1. `-l en` or your preferred language order
2. verifying captions exist on YouTube
3. retrying another public video to isolate the issue

### YouTube IP block or rate limiting

Try:

1. waiting and retrying later
2. lowering `MAX_CONCURRENT_VIDEOS`
3. retrying from another network or IP

### Windows Unicode console issues

If Rich output fails in a legacy console, use Windows Terminal or UTF-8 mode:

```powershell
chcp 65001
```

More detail: [Troubleshooting Wiki](https://github.com/whoisjayd/yt-study/wiki/Troubleshooting)

## Documentation

Detailed docs live in the wiki:

- [Wiki Home](https://github.com/whoisjayd/yt-study/wiki)
- [Installation Guide](https://github.com/whoisjayd/yt-study/wiki/Installation)
- [Usage Guide](https://github.com/whoisjayd/yt-study/wiki/Usage)
- [Configuration Reference](https://github.com/whoisjayd/yt-study/wiki/Configuration)
- [Architecture](https://github.com/whoisjayd/yt-study/wiki/Architecture)
- [Development Guide](https://github.com/whoisjayd/yt-study/wiki/Development)
- [Troubleshooting](https://github.com/whoisjayd/yt-study/wiki/Troubleshooting)
- [FAQ](https://github.com/whoisjayd/yt-study/wiki/FAQ)

## Developer Experience

```bash
make sync
make quick
make ci
make all
make hooks-install
make test-cov
make help
```

Project layout:

```text
src/yt_study/
  cli.py
  setup_wizard.py
  core/
    config.py
    pipeline.py
    llm/
    prompts/
    youtube/
  ui/
    dashboard.py
tests/
wiki/
```

## Contributing

- [Contributing Guide](CONTRIBUTING.md)
- [Architecture Overview](ARCHITECTURE.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Security Policy](SECURITY.md)

The wiki is maintained as a Git submodule, so documentation changes can affect both the parent repo and the `wiki/` submodule.

## License

[MIT License](LICENSE)
