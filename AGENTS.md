# PROJECT KNOWLEDGE BASE

**Updated:** 2026-03-20
**Stack:** Python 3.10+ · Typer · Rich · LiteLLM · Pydantic v2 · SQLAlchemy 2 · structlog

---

## What This Project Does

`yt-study` turns public YouTube videos and playlists into Markdown study notes.
It fetches transcripts through a native YouTube extractor, generates notes and
quizzes via LiteLLM, and caches results in SQLite.

---

## Repository Structure

```text
yt-study/
├── src/yt_study/
│   ├── __main__.py                ← CLI entrypoint for `yt-study`
│   ├── _constants.py              ← App-wide defaults, filenames, and limits
│   ├── cli/
│   │   ├── app.py                 ← Typer commands and top-level wiring
│   │   ├── _runtime.py            ← CLI process coordinator
│   │   ├── _context.py            ← Shared CLI runtime state
│   │   ├── _display.py            ← Rich and headless event rendering
│   │   ├── _formatters.py         ← Panels, summaries, and cost tables
│   │   ├── _single_runner.py      ← Single URL flow
│   │   ├── _batch_runner.py       ← Batch file flow
│   │   ├── _source_resolution.py  ← URL and playlist resolution
│   │   └── _types.py              ← CLI-only dataclasses and helpers
│   ├── config.py                  ← AppSettings and state-dir helpers
│   ├── domain/
│   │   ├── events.py              ← EventType and PipelineEvent
│   │   ├── results.py             ← PipelineResult and metrics
│   │   └── youtube.py             ← VideoTranscript, VideoMetadata, ParsedURL
│   ├── errors.py                  ← Exception hierarchy and formatting
│   ├── llm/
│   │   ├── provider.py            ← LiteLLM async provider wrapper
│   │   └── prompts/               ← study_notes.py, chapter_notes.py, quiz.py
│   ├── logging.py                 ← structlog setup and session log path
│   ├── pipeline/
│   │   ├── core.py                ← CorePipeline facade
│   │   ├── generation.py          ← Chunking and note generation
│   │   ├── _execution.py          ← Single-video and batch execution logic
│   │   ├── _artifacts.py          ← Transcript export and quiz writing
│   │   ├── _helpers.py            ← Usage, token, and output helpers
│   │   ├── _limiter.py            ← Shared YouTube rate limiter
│   │   └── _state.py              ← Shared pipeline state
│   ├── storage/
│   │   ├── repository.py          ← SQLite repository
│   │   ├── models.py              ← ORM models
│   │   ├── schemas.py             ← Pydantic read schemas
│   │   └── migrations.py          ← Schema repair helpers
│   ├── ui/
│   │   ├── dashboard.py           ← Rich live dashboard
│   │   └── setup_wizard.py        ← Interactive setup flow
│   ├── utils.py                   ← Filename, iterable, and bool helpers
│   └── youtube/
│       ├── parser.py              ← YouTube URL parsing
│       ├── metadata.py            ← Video and playlist metadata fetchers
│       ├── playlist.py            ← Playlist video extraction
│       ├── transcript.py          ← Transcript fetching and chapter splitting
│       ├── _availability.py       ← Availability checks
│       ├── _constants.py          ← YouTube-specific constants
│       └── extractor/             ← Native extractor implementation
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── README.md
├── CONTRIBUTING.md
├── AGENTS.md
└── pyproject.toml
```

---

## Important Files

| File | Why it matters |
| --- | --- |
| `src/yt_study/__main__.py` | Console-script entrypoint used by `yt-study` |
| `src/yt_study/cli/app.py` | Public Typer command surface and module patch points |
| `src/yt_study/pipeline/core.py` | Pipeline orchestration facade |
| `src/yt_study/pipeline/_execution.py` | Video processing and batch processing logic |
| `src/yt_study/youtube/extractor/async_client.py` | Only async boundary for YouTube I/O |
| `src/yt_study/youtube/metadata.py` | Video metadata, chapter, and playlist helpers |
| `src/yt_study/storage/repository.py` | SQLite repository and cache persistence |
| `tests/conftest.py` | Shared fixtures and extractor client mock |

---

## Runtime Flow

1. `yt_study.__main__:main` launches the Typer app.
2. `yt_study.cli.app` validates the input and selects single, playlist, or batch
   mode.
3. `yt_study.pipeline.core.CorePipeline` orchestrates the run.
4. `yt_study.youtube.metadata`, `playlist`, and `transcript` resolve YouTube
   content.
5. `yt_study.llm.provider` generates study notes and quizzes.
6. `yt_study.storage.repository` persists cache data in SQLite.
7. `yt_study.cli._display` renders Rich UI or headless output.

---

## Configuration Model

- Runtime config lives in `~/.yt-study/config.env`.
- Load order is code defaults, `config.env`, then environment variables.
- `AppSettings` is defined in `src/yt_study/config.py`.
- `YT_STUDY_HOME` overrides the state directory for tests and local isolation.

Key settings:

| Key | Default |
| --- | --- |
| `DEFAULT_MODEL` | `gemini/gemini-2.5-flash` |
| `MAX_CONCURRENT_VIDEOS` | `5` |
| `YOUTUBE_REQUESTS_PER_MINUTE` | `10` |
| `TEMPERATURE` | `0.7` |
| `MAX_TOKENS` | `None` |

Treat `AppSettings` as immutable. Tests should prefer `monkeypatch.setenv(...)`
over direct mutation.

---

## Testing Patterns

- Patch async YouTube functions with `AsyncMock`.
- Patch `yt_study.cli.app.Live` to avoid Rich event-loop conflicts in tests.
- Patch module-level CLI symbols at `yt_study.cli.app.*`.
- Keep helper-level coverage in `tests/unit/`, orchestration coverage in
  `tests/integration/`, and live public smoke coverage in `tests/e2e/`.
- Run live smoke tests only with `RUN_E2E=1` and a real provider key.
- Use the public smoke URLs when a change touches parsing, metadata, or the CLI:
  - `https://www.youtube.com/watch?v=8uiZC0l4Ajw`
  - `https://www.youtube.com/playlist?list=PL7s8EzBd1s8op6WSiYxr3U9E_T1DoIkJG`

---

## Architecture Rules

1. Keep CLI, UI, pipeline, storage, YouTube, LLM, domain, and config boundaries explicit.
2. Blocking YouTube I/O lives only inside `AsyncYouTubeExtractorClient`.
3. All progress flows through `PipelineEvent`.
4. Exceptions come from `yt_study.errors`, not local ad hoc classes.
5. Shared defaults live in `_constants.py`.
6. `DatabaseRepository` returns schemas, not raw ORM objects.
7. Use `structlog.get_logger(__name__)` in every module.

---

## Gotchas

- `yt_study.cli.app` is a module, not the Typer app object.
- `get_video_metadata`, `get_playlist_info`, `extract_playlist_videos`, and
  `fetch_transcript` are async functions.
- The extractor helper module is private and named `yt_study.youtube.extractor._parsers`.
- `AsyncYouTubeExtractorClient` is the only place where blocking network work is wrapped in `asyncio.to_thread`.

---
