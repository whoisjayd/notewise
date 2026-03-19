# PROJECT KNOWLEDGE BASE

**Updated:** 2026-03-19  **Stack:** Python 3.10+ · Typer · Rich · LiteLLM · Pydantic v2 · SQLAlchemy 2 · structlog

---

## WHAT THIS PROJECT DOES

`yt-study` converts YouTube videos and playlists into Markdown study notes using LLMs.
It is a CLI tool that: fetches transcripts via a native YouTube extractor (no yt-dlp),
generates notes/quizzes via LiteLLM, and caches results in SQLite.

---

## REPOSITORY STRUCTURE

```
yt-study/
├── src/yt_study/
│   ├── _constants.py              ← App-wide constants (defaults, filenames, limits)
│   ├── cli/
│   │   ├── app.py                 ← Full CLI (process / setup / config-path / version)
│   │   ├── types.py               ← ResolvedSource, _BatchVideoJob, _WorkerSlotManager, …
│   │   └── formatters.py          ← Rich rendering helpers (panels, cost table)
│   ├── config/
│   │   └── settings.py            ← AppSettings (Pydantic BaseSettings), provider key map
│   ├── domain/
│   │   ├── events.py              ← EventType, PipelineEvent
│   │   ├── results.py             ← PipelineResult, PipelineMetrics
│   │   └── youtube.py             ← VideoChapter, VideoTranscript, VideoMetadata, ParsedURL
│   ├── errors/
│   │   ├── exceptions.py          ← YtStudyError hierarchy + raise_if_video_unavailable
│   │   └── formatting.py          ← format_user_error
│   ├── infrastructure/
│   │   ├── llm/
│   │   │   ├── provider.py        ← LLMProvider (LiteLLM async), UsageTotals, get_provider
│   │   │   └── prompts/           ← study_notes.py, chapter_notes.py, quiz.py
│   │   └── youtube/
│   │       ├── _constants.py      ← YouTube URLs, Innertube config, user-agent, limits
│   │       ├── extractor/
│   │       │   ├── client.py      ← YouTubeExtractorClient (sync HTTP), YouTubeExtractorConfig
│   │       │   ├── async_client.py← AsyncYouTubeExtractorClient (async facade)
│   │       │   └── parsers.py     ← parse_transcript_payload, select_track
│   │       ├── metadata.py        ← async get_video_metadata (single-page batch)
│   │       ├── transcript.py      ← async fetch_transcript, _fetch_async
│   │       ├── playlist.py        ← async extract_playlist_videos, _extract_async
│   │       └── parser.py          ← parse_youtube_url → ParsedURL
│   ├── logging_config/
│   │   └── setup.py               ← configure_logging(), get_session_log_path()
│   ├── persistence/
│   │   ├── models.py              ← SQLAlchemy ORM (VideoRecord, TranscriptRecord, …)
│   │   ├── schemas.py             ← Pydantic v2 read schemas
│   │   ├── repository.py          ← DatabaseRepository (thread-safe singleton)
│   │   └── migrations.py          ← Additive schema repair
│   ├── services/
│   │   ├── pipeline.py            ← CorePipeline (async orchestrator)
│   │   ├── generation.py          ← StudyMaterialGenerator (chunking + LLM calls)
│   │   └── _limiter.py            ← get_youtube_limiter, clear_youtube_limiters
│   ├── ui/
│   │   ├── dashboard.py           ← PipelineDashboard (Rich live)
│   │   └── setup_wizard.py        ← run_setup_wizard
│   └── utils/
│       ├── filenames.py           ← sanitize_filename, safe_output_path
│       ├── iterables.py           ← dedupe_ordered
│       └── config_helpers.py      ← parse_bool_setting, is_valid_bool_setting
├── tests/                         ← 461 pytest tests
├── wiki/Architecture.md           ← CANONICAL architecture doc (read this first)
├── plans/                         ← Refactor execution plans (01–12)
├── pyproject.toml
└── Makefile
```

---

## IMPORTANT FILES

| File | Why it matters |
|------|---------------|
| `src/yt_study/cli/app.py` | All CLI commands; logging init; single/batch/playlist dispatch |
| `src/yt_study/cli/types.py` | `_WorkerSlotManager`, `_BatchVideoJob`, `ResolvedSource` — CLI-internal types with `_` prefix for private convention |
| `src/yt_study/_constants.py` | Single source of truth for defaults — never hardcode values elsewhere |
| `src/yt_study/infrastructure/youtube/_constants.py` | YouTube-specific constants (URLs, Innertube API details) |
| `src/yt_study/infrastructure/youtube/extractor/async_client.py` | `AsyncYouTubeExtractorClient` — the ONLY async boundary for YouTube I/O; wraps sync client via `asyncio.to_thread` |
| `src/yt_study/infrastructure/youtube/metadata.py` | `async get_video_metadata` — single-page fetch for title+duration+chapters |
| `src/yt_study/services/pipeline.py` | `CorePipeline.run()` — async orchestrator; uses `return_exceptions=True` |
| `src/yt_study/services/_limiter.py` | Shared `AsyncLimiter` keyed by `(loop_id, rate)` |
| `src/yt_study/persistence/repository.py` | `DatabaseRepository` — thread-safe singleton; all write via `upsert_video_cache()` |
| `src/yt_study/errors/exceptions.py` | `raise_if_video_unavailable()` — central access-restriction detection |
| `tests/conftest.py` | `mock_extractor_client` fixture — patches `AsyncYouTubeExtractorClient` with `AsyncMock` methods |
| `tests/test_pipeline/test_core_pipeline.py` | Reference for expected pipeline behaviour |

---

## ASYNC PATTERN

```python
# ALL YouTube I/O is async-first — no asyncio.to_thread in callers

# metadata
meta = await get_video_metadata(video_id, cookie_file)

# transcript
transcript = await fetch_transcript(video_id, languages, on_request=limiter_acquire)

# playlist
video_ids = await extract_playlist_videos(playlist_id, cookie_file=cookie_file)
```

`asyncio.to_thread` lives ONLY inside `AsyncYouTubeExtractorClient` methods.
Pipeline and CLI code never use it directly.

---

## CONFIGURATION MODEL

Runtime config: `~/.yt-study/config.env`
Load order: code defaults → `config.env` → environment variables

Key settings (with defaults from `_constants.py`):

| Key | Default | Notes |
|-----|---------|-------|
| `DEFAULT_MODEL` | `gemini/gemini-2.5-flash` | LiteLLM model string |
| `MAX_CONCURRENT_VIDEOS` | `5` | Pipeline parallelism |
| `YOUTUBE_REQUESTS_PER_MINUTE` | `10` | Shared rate limiter |
| `TEMPERATURE` | `0.7` | 0.0–1.0 validated |
| `MAX_TOKENS` | `None` | Model max if unset |

`AppSettings` is **immutable at runtime**. Tests use `monkeypatch.setenv` + fresh
`AppSettings()`, never direct attribute mutation.

---

## TESTING PATTERNS

### Mock extractor client
```python
# conftest.py provides mock_extractor_client fixture
# Each module's AsyncYouTubeExtractorClient is patched with AsyncMock methods

def test_something(mock_extractor_client):
    client = mock_extractor_client["metadata"].return_value
    client.metadata.return_value = {"title": "Test", ...}
    # client.transcript, client.chapters, client.playlist are also AsyncMocks
```

### Async metadata/playlist functions
```python
# get_video_metadata, get_playlist_info, extract_playlist_videos are ALL async
# Patch with AsyncMock:
patch("yt_study.services.pipeline.get_video_metadata",
      new=AsyncMock(return_value=VideoMetadata(...)))
```

### CLI tests
```python
# Patch at yt_study.cli.app.* (module-level imports)
patch("yt_study.cli.app.CorePipeline", return_value=pipeline_instance)
patch("yt_study.cli.app.parse_youtube_url", return_value=ParsedURL(...))
patch("yt_study.cli.app.get_playlist_info", new=AsyncMock(return_value=("Name", 2)))
patch("yt_study.cli.app.Live")           # mock the entire Live class
patch("yt_study.cli.app.config")         # mock the config singleton
# Always set: mock_config.youtube_requests_per_minute = 10
#              mock_config.youtube_cookie_file = None
```

---

## ARCHITECTURE RULES

1. **`services/` and `infrastructure/` never import from `cli/` or `ui/`**
2. **Blocking I/O only inside `AsyncYouTubeExtractorClient`** — nowhere else
3. **All progress via `PipelineEvent`** — pipeline emits; CLI converts to UI
4. **Centralised exceptions** — always raise from `yt_study.errors`, never define local exception classes
5. **Centralised logging** — `structlog.get_logger(__name__)` in every module
6. **Constants in `_constants.py`** — never hardcode defaults inline
7. **`AppSettings` is immutable** — test via env vars, not attribute mutation
8. **`DatabaseRepository` returns Pydantic schemas** — never raw ORM objects

---

## KNOWN GOTCHAS

- `yt_study.cli.app` is a **module**, not the Typer app. Import the Typer app as:
  `from yt_study.cli.app import app` (not `from yt_study.cli import app`)
- `_WorkerSlotManager` methods: `.acquire(vid)`, `.release(vid)`, `.get(vid)` — not `get_slot`
- `get_video_metadata` is `async def` — patch with `new=AsyncMock(return_value=...)`,
  not `return_value=...`
- `get_playlist_info` and `extract_playlist_videos` are also `async def`
- The `DASHBOARD_STATUS_MAP` and `DASHBOARD_STATUS_MAP` are defined inside `process()`
  — patch `yt_study.cli.app.Live` to prevent Rich event-loop conflicts in tests
- `_fetch_async` (was `_fetch_sync`) in `transcript.py` — update any references
- `_extract_async` (was `_extract_sync`) in `playlist.py` — update any references

---

## ARCHITECTURE REFERENCE

Full details: [`wiki/Architecture.md`](wiki/Architecture.md)
