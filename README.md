# yt-study

> Turn public YouTube videos and playlists into structured Markdown study notes.

[![CI](https://img.shields.io/github/actions/workflow/status/whoisjayd/yt-study/ci-main.yml?branch=dev&label=CI)](https://github.com/whoisjayd/yt-study/actions/workflows/ci-main.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-2E8B57)](LICENSE)
[![Type Checked](https://img.shields.io/badge/Type%20Checked-mypy-2A6DB0)](https://mypy-lang.org/)
[![Formatted with Ruff](https://img.shields.io/badge/Formatter-ruff-40B5A8?logo=ruff&logoColor=white)](https://docs.astral.sh/ruff/)

`yt-study` is a Python CLI for converting YouTube videos and playlists into
Markdown study materials. It uses a native YouTube extractor, LiteLLM, Rich,
SQLAlchemy, and SQLite to keep the workflow fast, testable, and local-first.

## Why It Exists

- Native YouTube extraction without `yt-dlp`.
- Async orchestration for transcripts, metadata, and generation.
- Rich terminal output with a clean headless mode for CI and automation.
- SQLite caching so repeat runs stay fast.
- Focused, testable package boundaries that are easy to extend.

## Quick Start

```bash
make sync
yt-study setup
yt-study process "https://www.youtube.com/watch?v=8uiZC0l4Ajw"
yt-study process "https://www.youtube.com/playlist?list=PL7s8EzBd1s8op6WSiYxr3U9E_T1DoIkJG"
```

## What You Get

- Markdown study notes for single videos, playlists, or batch files.
- Optional quizzes with `--quiz`.
- Optional transcript export with `--export-transcript`.
- Headless output with `--no-ui` for logs, scripts, and CI.
- Configurable output paths, models, transcript languages, and cookie files.

## Project Layout

- `yt_study.cli` for command wiring and Rich rendering.
- `yt_study.pipeline` for orchestration and generation flow.
- `yt_study.youtube` for YouTube parsing, metadata, transcripts, and extractor internals.
- `yt_study.llm` for provider and prompt integration.
- `yt_study.storage` for SQLite persistence.
- `yt_study.ui` for the dashboard and setup wizard.
- `yt_study.domain` for pure data objects, events, and results.

## Quality Gates

Run these before opening a PR:

```bash
make hooks-run
make ci
python -m pytest tests -q
```

If you are contributing, start with `CONTRIBUTING.md`.
