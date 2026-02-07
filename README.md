# YT-Study

<div align="center">

[![PyPI](https://badge.fury.io/py/yt-study.svg)](https://badge.fury.io/py/yt-study)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/whoisjayd/yt-study/actions/workflows/ci-main.yml/badge.svg)](https://github.com/whoisjayd/yt-study/actions/workflows/ci-main.yml)
[![PR Gate](https://github.com/whoisjayd/yt-study/actions/workflows/pr-gate.yml/badge.svg)](https://github.com/whoisjayd/yt-study/actions/workflows/pr-gate.yml)
[![Coverage](https://codecov.io/gh/whoisjayd/yt-study/branch/main/graph/badge.svg)](https://codecov.io/gh/whoisjayd/yt-study)
[![Ruff](https://img.shields.io/badge/lint-ruff-46a758)](https://github.com/astral-sh/ruff)
[![Mypy](https://img.shields.io/badge/types-mypy-blue)](https://mypy-lang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

### Turn YouTube learning into structured study material.

Convert videos, playlists, and URL batches into clean Markdown notes with chapter awareness, transcript fallback logic, and LLM-powered organization.

[Quick Start](#quick-start) • [Features](#features) • [How-It-Works](#how-it-works) • [Configuration](#configuration) • [Contributing](#contributing)

</div>

## At A Glance

| Category      | Details                                                         |
| ------------- | --------------------------------------------------------------- |
| Primary Use   | Generate reusable study notes from YouTube                      |
| Inputs        | Single video URL, playlist URL, `urls.txt` batch file           |
| Output        | Markdown notes (single file or chapter-based files)             |
| Core Stack    | Python, Typer, Rich, LiteLLM, youtube-transcript-api, pytubefix |
| Runtime Style | Async orchestration with concurrent playlist workers            |
| Quality       | Tests, Ruff, MyPy, CI workflows                                 |

## Documentation Map

Use the wiki for detailed guides:

- [Wiki Home](https://github.com/whoisjayd/yt-study/wiki)
- [Installation Guide](https://github.com/whoisjayd/yt-study/wiki/Installation)
- [Usage Guide](https://github.com/whoisjayd/yt-study/wiki/Usage)
- [Configuration Reference](https://github.com/whoisjayd/yt-study/wiki/Configuration)
- [Architecture](https://github.com/whoisjayd/yt-study/wiki/Architecture)
- [FAQ](https://github.com/whoisjayd/yt-study/wiki/FAQ)

## Vision

Most high-quality educational content is now video-first, but video is a weak medium for revision:

- Slow to scan.
- Hard to search deeply.
- Difficult to convert into repeatable study systems.

`yt-study` exists to close that gap.

The long-term vision is to make long-form video learning operational: not just consumable once, but reusable as a durable knowledge asset.
Instead of repeatedly scrubbing timelines, you get structured notes that can be reviewed, annotated, shared, and versioned.

Design principles:

1. **Fidelity over generic summarization**
   Preserve critical terminology, workflow steps, and technical context.
2. **Low-friction daily usage**
   One command flow for setup, processing, and iteration.
3. **Scalable processing**
   Handle long transcripts and multi-video queues with concurrency.
4. **Reliability under real-world conditions**
   Fallbacks, retries, and strict engineering standards over demo-only flows.

## Features

### Content Ingestion

- Supports video URLs, playlist URLs, and batch files (`yt-study process urls.txt`).
- Parses common YouTube formats: `watch`, `youtu.be`, `embed`, `shorts`, and playlist links.

### Transcript Reliability

- Prioritizes manual transcripts in preferred language.
- Falls back to auto-generated transcripts.
- Can select other languages and translate when appropriate.
- Includes retry behavior and IP-block detection paths.

### Note Generation Quality

- Uses chapter-based note generation for long standalone videos with chapters.
- Uses chunked generation with overlap for large transcript contexts.
- Outputs clean Markdown suitable for Obsidian, Notion import, Git docs, and revision sets.

### Pipeline + UX

- Async orchestration for better throughput.
- Concurrent worker processing for playlists.
- Rich live dashboard for status, worker activity, and run summary.

### Engineering Quality

- Strict typing with MyPy.
- Formatting/linting with Ruff.
- Automated validation through CI and PR gate workflows.

## Quick Start

### 1. Install

```bash
pip install yt-study
```

### 2. First-Time Setup

```bash
yt-study setup
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

### 4. Useful CLI Commands

```bash
yt-study --help
yt-study config-path
yt-study version
```

## How It Works

```text
Input URL/File
  -> URL parsing (video/playlist detection)
  -> metadata + transcript retrieval
  -> generation strategy selection
     - chapter mode (long standalone video + chapters)
     - chunked mode (large transcript)
  -> LLM generation (provider/model from config)
  -> Markdown write to output directory
```

## Command Reference

```bash
yt-study setup                # interactive first-run configuration
yt-study process "URL"        # process a single video or playlist URL
yt-study process urls.txt     # process a text file of URLs
yt-study config-path          # show ~/.yt-study/config.env location
yt-study version              # print installed CLI version
yt-study --help               # full command/options help
```

## Usage Patterns

### Course Playlist Capture

Use `yt-study` after finishing a lecture playlist to convert each session into searchable notes.

### Research Queue

Maintain `urls.txt` as a personal watch-and-learn queue and generate notes in batches.

### Team Knowledge Sync

Run on shared technical videos and commit generated Markdown into an internal docs repo.

## Troubleshooting

### YouTube IP Block Detected

When YouTube rate-limits your IP, transcript/metadata requests can fail.

Try:

1. Wait and retry later.
2. Reduce `MAX_CONCURRENT_VIDEOS` in `~/.yt-study/config.env` (for example `1` or `2`).
3. Retry from a different network/IP.

### Missing API Key For Model

If the selected model is missing its provider key, processing will stop early.

Fix:

1. Run `yt-study setup` and reconfigure the provider/model.
2. Verify expected key in `~/.yt-study/config.env`.
3. Use `yt-study config-path` to confirm the active config location.

### Transcript Not Available

Some videos have disabled transcripts or no usable subtitles.

What to try:

1. Use `-l en` or provide preferred languages with `-l`.
2. Confirm the video has captions available on YouTube.
3. Try another video if captions are disabled by the creator.

### Processing Fails For Some Playlist Items

Large playlists can have mixed availability (private/deleted/restricted videos).

What happens:

- `yt-study` continues processing and shows failed items in summary.

## FAQ

### Is yt-study free?

The CLI is open-source. LLM provider usage may cost money depending on your API plan.

### Which model should I start with?

Start with a fast model from your preferred provider, then move to higher-quality models for final notes.

### Does yt-study support batch processing?

Yes. Provide a text file with one URL per line:

```bash
yt-study process urls.txt
```

### Where are logs stored?

Session log files are written to:

- `~/.yt-study/logs/`

If home is not writable, logs fall back to a local `./logs` directory.

### Where can I read extended docs?

Use the wiki pages linked in [Documentation Map](#documentation-map), including [FAQ](https://github.com/whoisjayd/yt-study/wiki/FAQ).

## Configuration

Config file location:

- `~/.yt-study/config.env`

Common settings:

- `MODEL` (example: `gemini/gemini-2.5-pro`)
- `MAX_CONCURRENT_VIDEOS` (default: `5`)
- Provider keys such as `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`
- Generation options including `temperature` and token controls

Configuration loading behavior:

- Reads `~/.yt-study/config.env` first.
- Applies environment variable overrides after file load.
- Syncs provider API keys into process environment for downstream SDK usage.

Full reference: [Configuration Wiki](https://github.com/whoisjayd/yt-study/wiki/Configuration)

## Output Organization

Typical output shape:

```text
output/
  Video Title/
    Video Title.md
  Long Video With Chapters/
    01_Intro.md
    02_Core Concept.md
    03_Implementation.md
```

## Developer Experience

```bash
make sync      # install locked dependencies
make ci        # CI-equivalent checks
make all       # local full pass (with autofix)
make help      # list all make targets
```

Project layout:

```text
src/yt_study/
  cli.py
  config.py
  setup_wizard.py
  llm/
  pipeline/
  prompts/
  ui/
  youtube/
```

## Contributing

- [Contributing Guide](CONTRIBUTING.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Security Policy](SECURITY.md)

## License

[MIT License](LICENSE)
