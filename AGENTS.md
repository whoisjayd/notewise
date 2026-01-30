# PROJECT KNOWLEDGE BASE

**Generated:** 2026-01-30
**Commit:** 52919bc
**Branch:** main

## OVERVIEW

Python CLI tool converting YouTube videos/playlists into AI-powered study notes. Stack: Python 3.10+, Typer CLI, LiteLLM, Rich TUI, youtube-transcript-api, pytubefix. Build via hatchling, managed with uv.

## STRUCTURE

```
yt-study/
├── wiki/               # Documentation (submodule)
├── src/yt_study/           # Main package
│   ├── cli.py              # Entry point (Typer app)
│   ├── config.py           # Config dataclass + env loading
│   ├── setup_wizard.py     # Interactive first-run setup
│   ├── llm/                # LLM integration
│   │   ├── generator.py    # Chunking + note generation logic
│   │   └── providers.py    # LiteLLM wrapper (acompletion)
│   ├── pipeline/
│   │   └── orchestrator.py # Main async pipeline (418 LOC, largest file)
│   ├── prompts/            # System/user prompt templates
│   │   ├── study_notes.py  # Standard chunked generation
│   │   └── chapter_notes.py# Chapter-based generation
│   ├── ui/
│   │   └── dashboard.py    # Rich Live TUI with progress bars
│   └── youtube/            # YouTube data fetching
│       ├── parser.py       # URL parsing (video/playlist detection)
│       ├── transcript.py   # Transcript fetch with language fallback
│       ├── metadata.py     # Title, duration, chapters
│       └── playlist.py     # Playlist video extraction
├── tests/                  # pytest test suite
│   ├── conftest.py         # Fixtures (sample_video_id, sample_playlist_id)
│   └── test_*/             # Module-specific tests
├── pyproject.toml          # Build config, dependencies, pytest options
└── .github/workflows/      # CI (pytest on 3.10, 3.11, 3.12)
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Add CLI command | `cli.py` | Use `@app.command()` decorator |
| Change LLM behavior | `llm/providers.py` | Uses `litellm.acompletion` |
| Modify prompt templates | `prompts/*.py` | SYSTEM_PROMPT, CHUNK_GENERATION_PROMPT, etc. |
| Adjust chunking logic | `llm/generator.py` | `_chunk_transcript()` method |
| Add new LLM provider | `config.py` | Add to ALLOWED_KEYS, key_map in orchestrator |
| Parse new URL format | `youtube/parser.py` | Add regex pattern |
| Handle transcript edge cases | `youtube/transcript.py` | Language fallback, retry logic |
| Customize TUI | `ui/dashboard.py` | `PipelineDashboard.__rich__()` |
| Add/modify tests | `tests/` | Follow pytest async pattern |

## CODE MAP

| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `app` | Typer | `cli.py:38` | CLI entry point |
| `PipelineOrchestrator` | class | `pipeline/orchestrator.py:34` | Main processing coordinator |
| `StudyMaterialGenerator` | class | `llm/generator.py:23` | Chunk + generate logic |
| `LLMProvider` | class | `llm/providers.py:14` | LiteLLM abstraction |
| `Config` | dataclass | `config.py:12` | Global singleton (`config`) |
| `PipelineDashboard` | class | `ui/dashboard.py:25` | Rich Live TUI component |
| `fetch_transcript` | async fn | `youtube/transcript.py:49` | Multi-language transcript fetch |
| `parse_youtube_url` | fn | `youtube/parser.py:59` | URL → ParsedURL |

## CONVENTIONS

- **Async-first**: Use `async def` for I/O operations, wrap sync libs with `asyncio.to_thread()`
- **Config pattern**: Single `Config` dataclass instance at module level (`config = Config()`)
- **Lazy imports**: Heavy imports inside functions for faster CLI startup (see `cli.py:107`)
- **LiteLLM model format**: Provider prefix required (`gemini/`, `anthropic/`, `groq/`, `xai/`, etc.)
- **Error handling**: Custom exceptions (`TranscriptError`), retry with exponential backoff
- **UI updates**: Pass `Progress` and `TaskID` through call stack, never create nested Progress bars

## ANTI-PATTERNS (THIS PROJECT)

- **DO NOT** create nested `rich.progress.Progress` bars - causes display corruption
- **DO NOT** print to console during `Live` context - use `dashboard.update_worker()` instead
- **NEVER** call blocking YouTube API directly in async context - use `asyncio.to_thread()`
- **NEVER** add keys to `Config.ALLOWED_KEYS` without updating `_load_from_user_config()`
- **AVOID** `logging.getLogger("LiteLLM")` calls in hot paths - already suppressed in `cli.py`

## UNIQUE STYLES

- **Filename sanitization**: `sanitize_filename()` in orchestrator removes `<>:"/\|?*`, limits to 100 chars
- **Chapter detection**: Videos >1hr with chapters → separate notes per chapter
- **Transcript fallback**: Manual → Auto-generated → Any language → Translate to English
- **Chunk overlap**: 200 tokens overlap between chunks to preserve context
- **Token counting**: Uses `litellm.token_counter()` for model-specific tokenization

## COMMANDS

```bash
# Development
uv sync                          # Install dependencies
uv run pytest                    # Run tests
uv run yt-study --help           # CLI help
uv run yt-study setup            # Configure API keys
uv run yt-study process "URL"    # Generate notes

# Build
uv build                         # Create wheel/sdist in dist/

# CI runs: uv sync --all-extras --dev && uv run pytest
```

## NOTES

- **User config**: `~/.yt-study/config.env` (not `.env` in project root)
- **Logs**: `~/.yt-study/logs/yt-study.log` (file handler at DEBUG level)
- **Concurrency**: `config.max_concurrent_videos` (default 5) controls parallel processing
- **Test fixtures**: `sample_video_id` = Rick Astley, `sample_playlist_id` = public test playlist
- **Rich screen mode**: Playlist processing uses `screen=True` in `Live()` to prevent scroll artifacts
- **pytubefix**: Fork of pytube with better maintenance, used for playlist extraction
