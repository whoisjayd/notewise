# yt-study — Master Task Backlog

**Local reference only — do not commit this file.**
**Last updated:** 2026-03-21
**Source-verified:** Every bug confirmed by reading actual source files.
**Refactoring status:** dev branch refactor in progress — commit-based plan.
**Stack:** Python 3.10+ · Typer · Rich · LiteLLM · Pydantic v2 · SQLAlchemy 2 · structlog · uv · ruff

---

## Table of Contents

1. [Current State Snapshot](#current-state-snapshot)
2. [Architecture Invariants](#architecture-invariants)
3. [Stable Interfaces](#stable-interfaces)
4. [Bug Registry](#bug-registry) — **36 confirmed bugs**
5. [Task Backlog](#task-backlog)
   - TASK-01 Bug fixes
   - TASK-02 ty migration
   - TASK-03 Parallel chapters
   - TASK-04 CLI startup speed
   - TASK-05 ASCII banner & enhanced landing
   - TASK-06 New CLI commands (stats, history, info, doctor, cache, logs, edit-config)
   - TASK-07 Dashboard visual refactor
   - TASK-08 Mintlify docs scaffold
   - TASK-09 Per-subfolder AGENTS.md
   - TASK-10 Targeted test expansion
   - TASK-11 Storage hardening (schema versioning, cached_at, prune)
   - TASK-12 YouTube extractor HTTP retry
   - TASK-13 CI and Makefile hardening
   - TASK-14 Benchmark harness
6. [Commit Plan](#commit-plan)
7. [Coverage Gap Summary](#coverage-gap-summary)
8. [Definition of Done](#definition-of-done)
9. [Compact Memory](#compact-memory)

---

## Current State Snapshot

| Dimension | Status |
|---|---|
| Test coverage | ~93% — gaps in CLI routing, display bridging, config edges, UI edge cases |
| Type checker | `mypy 1.19` strict → **migrating to `ty` (TASK-02)** |
| Mintlify docs | None — no `docs.json`, no `docs/` tree |
| CLI startup | Slow — `_runtime` imported at `app.py` top level, defeats lazy loading for all fast commands |
| Chapter processing | Sequential — `generate_chapter_notes_concurrent()` **complete in `generation.py`, never wired** |
| Batch `--no-ui` | Completely silent — zero headless event emission |
| Dashboard | Functional; double-markup bug, wrong failure order, no `PipelineMetrics.__bool__` |
| Playlist privacy | Naive `"private" in title.lower()` string-match — false positives on legit playlists |
| Language fallback | Silent alphabetical fallback — wrong language, no warning |
| Cache management | No user-facing CLI commands for inspect / clear / prune / stats |
| HTTP retry | YouTube transport layer has no retry |
| Useful commands | No `stats`, `history`, `info`, `doctor`, `edit-config` commands |
| ASCII banner | No branding — raw Typer help on `yt-study` with no args |

### What Is Already Strong

- Clean layer separation: `cli → pipeline → youtube / llm / storage`. No reverse imports.
- `DatabaseRepository.close_all_instances()` exists; `conftest.py::isolate_state_dir` (autouse) calls it.
- Higher-level retry present: `LLM_NUM_RETRIES=3`, `TRANSCRIPT_MAX_RETRIES=3`, `PLAYLIST_MAX_RETRIES=3`.
- All blocking YouTube I/O correctly isolated in `asyncio.to_thread`.
- `generate_chapter_notes_concurrent()` fully implemented in `generation.py` — just needs wiring.
- `PipelineSharedState` cleanly separates shared coordination from per-pipeline state.
- `_WorkerSlotManager` is functionally correct; only an O(n) inefficiency in `pop(0)`.

### Command Surface

| Command | Handler | Pays full startup cost? |
|---|---|---|
| `yt-study process <url\|file>` | `process()` | Yes — `_runtime` imported at module level |
| `yt-study setup [--force]` | `setup()` | Yes — `_load_cli_dependencies()` pulls everything |
| `yt-study config-path` | `config_path()` | No — only needs `get_state_dir()` |
| `yt-study version` | `version()` | Yes — `_runtime` import at module top already ran |

### Key File Map

```
src/yt_study/
├── cli/
│   ├── app.py                ← Typer commands; lazy globals; looks_like_batch_file_path (BUG-13)
│   ├── _runtime.py           ← CliProcessRunner  ← TOP-LEVEL IMPORT defeats startup (TASK-04)
│   ├── _context.py           ← CliProcessContext dataclass
│   ├── _single_runner.py     ← run_single_url() — headless mode correct
│   ├── _batch_runner.py      ← run_batch_file() — no-ui SILENT (BUG-24), serial enqueue (BUG-28)
│   ├── _source_resolution.py ← prepare_source() — creates dir unconditionally (BUG-25)
│   ├── _display.py           ← HEADLESS_LABELS dead entry (BUG-06); slot drop silent (BUG-07)
│   ├── _formatters.py        ← print_cost_summary() dead guard (BUG-02)
│   └── _types.py             ← _WorkerSlotManager pop(0) O(n) (BUG-33)
├── pipeline/
│   ├── core.py               ← CorePipeline facade + re-exports
│   ├── _execution.py         ← SEQUENTIAL chapter loop (BUG-03); double DB (BUG-04)
│   │                            export_transcript before mkdir (BUG-32/33); wrong dir (BUG-32)
│   ├── generation.py         ← generate_chapter_notes_concurrent() UNWIRED (BUG-03)
│   │                            generate_chapter_based_notes() DEAD CODE (BUG-19)
│   ├── _artifacts.py         ← export_transcript(): no mkdir guard (BUG-33)
│   ├── _helpers.py           ← coerce_usage_*, suffix_output_target
│   ├── _limiter.py           ← _GLOBAL_YOUTUBE_LIMITERS stale entries (BUG-08)
│   └── _state.py             ← PipelineSharedState
├── ui/
│   ├── dashboard.py          ← double-markup (BUG-05); wrong failure order (TASK-07)
│   └── setup_wizard.py       ← infinite loop (BUG-09); module-level console (BUG-10)
├── youtube/
│   ├── transcript.py         ← new client on every retry (BUG-22)
│   ├── metadata.py           ← swallows ExtractionError silently (BUG-23)
│   │                            dead functions: get_video_chapters/title/duration (BUG-36)
│   ├── playlist.py           ← extract_playlist_videos()
│   ├── parser.py             ← parse_youtube_url(), extract_video_id()
│   ├── _availability.py      ← raise_for_video_availability()
│   └── extractor/
│       ├── client.py         ← unused `import time  # noqa: F401` (BUG-31)
│       ├── _transport.py     ← no retry at HTTP level (TASK-12)
│       ├── _parsers.py       ← silent wrong-language fallback (BUG-20)
│       └── _playlist.py      ← naive privacy: "private" in title (BUG-21)
├── storage/
│   ├── repository.py         ← DatabaseRepository singleton; write lock
│   ├── models.py             ← VideoRecord missing cached_at timestamp (BUG-35)
│   └── migrations.py         ← one-off repair_runstats_schema, no versioning
├── llm/
│   └── provider.py           ← LLMGenerationError double-wrap (BUG-29); max_tokens falsy (BUG-30)
├── config.py                 ← UserConfigSource: _load_env_file 18× per init (BUG-01)
├── errors.py                 ← format_user_error() auth vs filesystem (BUG-18)
├── logging.py                ← no idempotency guard (BUG-27); thread-unsafe (BUG-14)
└── utils.py                  ← sanitize_filename double-truncation (BUG-15)
```

---

## Architecture Invariants — Must Never Be Violated

1. **Dependency direction:** `CLI → Pipeline → YouTube / LLM / Storage`. Never reverse.
2. **Blocking I/O:** All blocking YouTube network calls inside `asyncio.to_thread`. Never block the event loop.
3. **Event contract:** All pipeline progress flows through `PipelineEvent` via `on_event`. Never call dashboard methods directly from pipeline.
4. **Exception hierarchy:** All custom exceptions derive from `yt_study.errors`. Never define exceptions elsewhere.
5. **Constants:** All shared defaults in `yt_study._constants`. No scattered magic numbers.
6. **Repository API:** `DatabaseRepository` returns Pydantic schemas, never raw ORM objects.
7. **Logging:** Use `structlog.get_logger(__name__)` everywhere in library code. No bare `print()` outside CLI.
8. **Headless markers (frozen):** `"Done:"`, `"Batch Completed"`, `"Current log:"` must never change.
9. **CLI patch points:** Module-level globals in `cli/app.py` must remain patchable via `monkeypatch`.

---

## Stable Interfaces — Must Not Change Without a Migration Plan

| Interface | File | Contract |
|---|---|---|
| `app` (Typer object) | `cli/app.py` | Patched in tests via `CliRunner` |
| Command names | `cli/app.py` | `process`, `setup`, `config-path`, `version` |
| All existing CLI flags | `cli/app.py` | `--model`, `--output`, `--language`, `--temperature`, `--max-tokens`, `--force`, `--no-ui`, `--quiz`, `--export-transcript`, `--cookie-file` |
| 8 lazy patch globals | `cli/app.py` | `config`, `CorePipeline`, `Live`, `PipelineDashboard`, `parse_youtube_url`, `extract_playlist_videos`, `get_playlist_info`, `run_setup_wizard` |
| `PipelineDashboard.__init__` | `ui/dashboard.py` | `(total_videos, concurrency, playlist_name, model_name)` |
| `PipelineDashboard` public methods | `ui/dashboard.py` | `update_worker`, `add_completion`, `add_failure`, `set_total_videos`, `update_overall_status`, `__rich__` |
| Headless output markers | `_display.py`, `_single_runner.py` | `"Done:"`, `"Batch Completed"`, `"Current log:"` |
| `AppSettings` field names | `config.py` | Tests monkeypatch by name |
| Exception class names | `errors.py` | Tests use `pytest.raises(SpecificError)` |
| `PipelineEvent` fields | `domain/events.py` | All 9 fields; constructed by keyword everywhere |
| `PipelineResult` fields | `domain/results.py` | `.success_count`, `.failure_count`, `.total_count`, `.video_ids`, `.errors`, `.metrics` |
| `CorePipeline.run()` | `pipeline/core.py` | `async def run(video_ids, on_event) -> PipelineResult` |

---

## Bug Registry

**36 confirmed bugs** — all source-verified with exact file, line, root cause, and fix.
Severity: `Critical` → `High` → `Medium` → `Low` → `Very Low`.

---

### BUG-01 — `UserConfigSource._load_env_file()` Called ~18× Per Startup

**File:** `src/yt_study/config.py` → `UserConfigSource.get_field_value`, `__call__`
**Severity:** Medium

`get_field_value` calls `self._load_env_file()` on every field access. `AppSettings` has ~16 fields → ~16 disk reads per settings construction plus one more in `__call__`.

```python
def get_field_value(self, _field, field_name):
    data = self._load_env_file()   # ← disk read on EVERY field access
```

**Fix:** Cache with `object.__setattr__` to bypass pydantic's immutability:
```python
def _load_env_file(self) -> dict[str, str]:
    try:
        return object.__getattribute__(self, "_parsed_env_cache")
    except AttributeError:
        result = self._parse_env_file()
        object.__setattr__(self, "_parsed_env_cache", result)
        return result

def _parse_env_file(self) -> dict[str, str]:
    # move current body of _load_env_file here
    ...
```

---

### BUG-02 — `PipelineMetrics.__bool__` Undefined; `print_cost_summary` Guard Is Dead Code

**File:** `src/yt_study/cli/_formatters.py` → `print_cost_summary`; `src/yt_study/domain/results.py`
**Severity:** Low

`PipelineMetrics` is a plain `@dataclass` — no `__bool__`. Any instance is always truthy. `if not metrics: return` never fires. Cost table prints for zero-token all-skipped runs.

**Fix (`domain/results.py`):**
```python
def __bool__(self) -> bool:
    return bool(self.total_tokens or self.cost_usd or self.transcript_seconds)
```

---

### BUG-03 — Chapter Generation Is Sequential; `generate_chapter_notes_concurrent()` Exists but Is Never Wired

**File:** `src/yt_study/pipeline/_execution.py` (sequential loop); `src/yt_study/pipeline/generation.py` (complete concurrent method, unused)
**Severity:** High

`_execution.py` has a plain `for` loop. `StudyMaterialGenerator.generate_chapter_notes_concurrent()` was fully implemented with `asyncio.Semaphore` — but `_execution.py` never calls it. See TASK-03.

---

### BUG-04 — Force-Mode Executes a Redundant DB Cache Lookup

**File:** `src/yt_study/pipeline/_execution.py` → `process_single_video`
**Severity:** Medium

```python
cached_video = None if pipeline.force else await pipeline._get_cached_video(video_id)
...
if pipeline.force:
    current_cached_video = await pipeline._get_cached_video(video_id)  # ← 2nd call!
```

**Fix:** `current_cached_video = None if pipeline.force else await pipeline._get_cached_video(video_id)` — single fetch, serves both skip-check and output-reservation.

---

### BUG-05 — `update_worker(style=…)` Double-Wraps Rich Markup

**File:** `src/yt_study/ui/dashboard.py` → `PipelineDashboard.update_worker`
**Severity:** Low

```python
description = f"[{style}]{status}[/{style}]" if style else status
```

All callers pass pre-styled `status` strings. The `style` param is a dead trap that produces `[red][cyan]text[/cyan][/red]` if used.

**Fix:** Remove the `style` parameter entirely.

---

### BUG-06 — `HEADLESS_LABELS[EventType.VIDEO_FAILED]` Is Unreachable Dead Constant

**File:** `src/yt_study/cli/_display.py`
**Severity:** Very Low

`emit_headless_event` returns early for `VIDEO_FAILED` before the label lookup — making `EventType.VIDEO_FAILED: "Failed"` permanently dead.

**Fix:** Remove the entry.

---

### BUG-07 — `_WorkerSlotManager.acquire()` Returning `None` Silently Drops All Dashboard Events for That Video

**File:** `src/yt_study/cli/_display.py` → `build_ui_event_handler`
**Severity:** Medium

When `acquire()` returns `None` (all slots occupied), the video has no assigned slot. All subsequent events for that `video_id` are silently dropped — the dashboard never updates for that video. No warning logged.

**Fix:** `logger.warning("dashboard.slot_exhausted", video_id=video_id)` when `assigned is None`.

---

### BUG-08 — `_GLOBAL_YOUTUBE_LIMITERS` Accumulates Stale Entries Across Test Event Loops

**File:** `src/yt_study/pipeline/_limiter.py`
**Severity:** Low in production, Medium in tests

`id(loop)` is recycled by CPython after GC. New event loops in tests collide with stale entries.

**Fix:** Add `clear_youtube_limiters()` to `conftest.py::isolate_state_dir` teardown (alongside the existing `close_all_instances()` call).

---

### BUG-09 — `select_model` Infinite Loop on Unrecognized Input

**File:** `src/yt_study/ui/setup_wizard.py` → `select_model`
**Severity:** Medium

`while True` loop handles `"n"`, `"p"`, and digit inputs but has no `else` clause. Any other input loops silently.

**Fix:** Add `else: console.print("[red]Invalid input...[/red]"); continue`.

---

### BUG-10 — Module-Level `console` in `setup_wizard.py` Breaks Test Isolation

**File:** `src/yt_study/ui/setup_wizard.py`
**Severity:** Low

`console = Console()` at module level is shared globally. Tests must patch `yt_study.ui.setup_wizard.console` — a fragile path.

**Fix:** Accept `console: Console | None = None` in `run_setup_wizard`.

---

### BUG-11 — `export_transcript` Instance Attribute Name Collides with Imported Module Function

**File:** `src/yt_study/pipeline/_execution.py`
**Severity:** Low

`pipeline.export_transcript` is a string; `pipeline_module.export_transcript` is the function. Works at runtime but `pipeline.export_transcript(...)` yields `TypeError: 'str' object is not callable`.

**Fix:** Rename `CorePipeline.export_transcript` → `CorePipeline.export_transcript_format`.

---

### BUG-12 — `concurrency=0` Renders a Meaningless 0/0 Dashboard for Empty Playlists

**File:** `src/yt_study/cli/_single_runner.py`
**Severity:** Low

When `video_ids=[]`, `concurrency=0`. Dashboard flashes `0/0`, then `print_run_summary` returns silently. User sees a brief blank flash and nothing else.

**Fix:** Guard before creating dashboard:
```python
if not prepared.video_ids:
    context.console.print("[yellow]No videos found to process.[/yellow]")
    return True
```

---

### BUG-13 — `looks_like_batch_file_path` False-Positive for Schemeless Non-YouTube URLs

**File:** `src/yt_study/cli/app.py` → `looks_like_batch_file_path`
**Severity:** Low

`or ("/" in value)` → `vimeo.com/123456` misclassified as a batch file path.

**Fix:** Remove `("/" in value)` and `("\\" in value)`. The remaining checks handle real file paths correctly.

---

### BUG-14 — `configure_logging()` Global Write Is Not Thread-Safe

**File:** `src/yt_study/logging.py`
**Severity:** Very Low (pytest-xdist only)

`_SESSION_LOG_PATH` written without a lock.

**Fix:** `with _log_lock: _SESSION_LOG_PATH = session_log` using a module-level `threading.Lock`.

---

### BUG-15 — `sanitize_filename` Double-Truncation Can Strip the Reserved-Name Prefix

**File:** `src/yt_study/utils.py` → `sanitize_filename`
**Severity:** Very Low

```python
name = name[:100].rstrip(" .")          # First truncation
if _RESERVED.match(name):
    name = f"_{name}"[:100].rstrip(" .") # Prefix can be truncated away
```

**Fix:** Apply reserved check before truncation.

---

### BUG-16 — Env-Only Configuration Still Triggers the Interactive Setup Wizard

**File:** `src/yt_study/cli/app.py` → `ensure_setup()`
**Severity:** High — breaks CI, headless, containerized deployments

`check_config_exists()` only checks file existence. Ignores env vars entirely.

**Fix:** Check whether the effective config satisfies the model's API key:
```python
def ensure_setup() -> None:
    key_name = config.get_api_key_name_for_model(config.default_model)
    if key_name and not os.environ.get(key_name) and not check_config_exists():
        run_setup_wizard(force=False)
```

---

### BUG-17 — Setup Wizard Invoked Before Input Validation

**File:** `src/yt_study/cli/app.py` → `process()`
**Severity:** Medium

`ensure_setup()` fires before URL/file validation. Invalid inputs force the user through the setup wizard before hearing about the actual problem.

**Fix:** Reorder — preflight validation before `ensure_setup()`.

---

### BUG-18 — `format_user_error()` Misclassifies Provider Auth Failures as Filesystem Errors

**File:** `src/yt_study/errors.py` → `format_user_error()`
**Severity:** Medium

`"permission denied"` / `"access is denied"` string-match catches provider-side 403s. User gets wrong remediation.

**Fix:** Check `"api key"` / `"unauthorized"` branches before `"permission denied"`. Differentiate by exception type where available.

---

### BUG-19 — `generate_chapter_based_notes()` Is Dead Code

**File:** `src/yt_study/pipeline/generation.py`
**Severity:** Low

Never imported or called. Superseded by `generate_chapter_notes_concurrent()`.

**Fix:** Remove.

---

### BUG-20 — `_pick_language()` Silently Falls Back to Alphabetically First Language

**File:** `src/yt_study/youtube/extractor/_parsers.py` → `_pick_language()`
**Severity:** Medium

Requesting `["en"]` on a `["zh", "fr"]`-only video → silently returns French. English notes from a French transcript → silent quality disaster.

**Fix:** `logger.warning("transcript.language_fallback", requested=..., available=..., selected=fallback)` before returning the fallback.

---

### BUG-21 — Playlist Privacy Determined by Naive String-Match on Title

**File:** `src/yt_study/youtube/extractor/_playlist.py` → `_extract_playlist()`
**Severity:** High

```python
availability = "private" if "private" in title.lower() else "public"
```

Any playlist titled "Private vs Public Cloud APIs" → `VideoUnavailableError`. Refuses to process a legitimate public playlist.

**Fix:** Use real availability data from YouTube page alerts renderer, same approach as `_video.py::_availability()`.

---

### BUG-22 — New `AsyncYouTubeExtractorClient` Created on Every Retry Attempt

**File:** `src/yt_study/youtube/transcript.py` → `fetch_transcript()`, `_fetch_async()`
**Severity:** Low

New client + cookie jar + file read on every retry in the retry loop.

**Fix:** Create client once before the loop; pass it into `_fetch_async`.

---

### BUG-23 — `get_video_metadata()` Swallows `ExtractionError` Silently

**File:** `src/yt_study/youtube/metadata.py` → `get_video_metadata()`
**Severity:** High

On transient failure returns `VideoMetadata(title=video_id, duration=0, chapters=[])`. Pipeline continues with video ID as filename, zero duration (no chapters), and no error reported.

**Fix:** Re-raise `ExtractionError` for non-availability failures. Let `process_single_video`'s exception handler report it.

---

### BUG-24 — Batch `--no-ui` Mode Emits Zero Headless Output

**File:** `src/yt_study/cli/_batch_runner.py` → `run_batch_file()`, `run_batch_job()`
**Severity:** High

```python
on_event=on_batch_event if dashboard is not None else None
# ↑ when --no-ui: on_event=None → pipeline emits nothing at all
```

A 50-video batch run is completely silent in `--no-ui` mode. Single-URL mode works correctly.

**Fix:** Pass `on_batch_event` regardless of `no_ui`. Inside the handler, call `emit_headless_event(context, event)` when `context.no_ui`.

---

### BUG-25 — Playlist Output Directory Created Before Confirming Videos Exist

**File:** `src/yt_study/cli/_source_resolution.py` → `prepare_source()`
**Severity:** Low

`output_dir.mkdir(parents=True, exist_ok=True)` called unconditionally before returning. Empty directories accumulate for failed or cancelled runs.

**Fix:** Remove `mkdir` from `prepare_source()`. Defer to caller at first video write.

---

### BUG-26 — `load_config()` in `setup_wizard.py` Does Not Strip Quotes from Values

**File:** `src/yt_study/ui/setup_wizard.py` → `load_config()`
**Severity:** Low

```python
loaded_config[key.strip()] = value.strip()   # no quote stripping
# vs config.py UserConfigSource:
value = value.strip().strip("'\"")           # strips quotes correctly
```

**Fix:** `loaded_config[key.strip()] = value.strip().strip("'\"")`

---

### BUG-27 — `configure_logging()` Creates New Log File on Every Call

**File:** `src/yt_study/logging.py`
**Severity:** Low

Each call clears handlers and creates a new timestamped log file, splitting log messages. Docstring says "safe to call multiple times" but the behavior is reconfigure-on-each-call.

**Fix:** Idempotency guard using `_LOGGING_CONFIGURED` flag.

---

### BUG-28 — Batch Enqueue Loop Is Serial; Workers Sit Idle During Playlist Resolution

**File:** `src/yt_study/cli/_batch_runner.py` → `enqueue_batch_jobs()`
**Severity:** Medium

All playlist resolution happens sequentially before any job reaches the queue. Workers idle during the entire resolution phase for large batch files.

**Fix:** Resolve URLs concurrently via `asyncio.create_task` per URL with a bounded semaphore (cap 3 concurrent resolutions). Feed queue as each resolves.

---

### BUG-29 — `LLMGenerationError` Double-Wrapped in `LLMProvider.generate()`

**File:** `src/yt_study/llm/provider.py` → `LLMProvider.generate()`
**Severity:** Medium

```python
# Inside try block:
if not response.choices or ...:
    raise LLMGenerationError("Received empty response from LLM provider")
# ↑ This is caught by:
except Exception as e:
    raise LLMGenerationError(f"Failed to generate with {self.model}: {str(e)}") from e
# ↑ Wraps the LLMGenerationError in another LLMGenerationError
```

Result: every `LLMGenerationError` gets wrapped into a new one with the message prepended. Error becomes `"Failed to generate with model: Received empty response from LLM provider"`. The original error type is preserved (since re-wrapped as the same type) but the extra wrapping is confusing and loses clean error propagation. Also, any retriable `RateLimitError` from LiteLLM that somehow bypasses the retry logic gets wrapped and loses its original type.

**Fix:** Exclude `LLMGenerationError` from the outer catch:
```python
except LLMGenerationError:
    raise  # ← let it propagate cleanly
except Exception as e:
    logger.error(f"LLM generation failed with {self.model}: {e}", exc_info=True)
    raise LLMGenerationError(f"Failed to generate with {self.model}: {str(e)}") from e
```

---

### BUG-30 — `max_tokens` Uses Falsy Check, Silently Ignored When Set to Valid Small Value

**File:** `src/yt_study/llm/provider.py` → `LLMProvider.generate()`
**Severity:** Very Low

```python
if max_tokens:           # ← falsy check; True for all integers except 0
    kwargs["max_tokens"] = max_tokens
```

`max_tokens=0` is excluded by `gt=0` validation at config layer and Typer's `min=1`. But if `max_tokens` were ever explicitly set to `0` through the Python API directly, it would be silently ignored. More critically, this check would also ignore hypothetical negative values that slipped through. The intent is clearly `if max_tokens is not None`.

**Fix:** `if max_tokens is not None: kwargs["max_tokens"] = max_tokens`

---

### BUG-31 — Unused `import time` with `noqa` Suppressor in `client.py`

**File:** `src/yt_study/youtube/extractor/client.py` line 3
**Severity:** Very Low

```python
import time  # noqa: F401
```

`time` is not used anywhere in the file. The `noqa` suppressor hides this from linting. Likely a leftover from a refactor.

**Fix:** Remove the import and the noqa suppressor.

---

### BUG-32 — `export_transcript` Writes to Wrong Directory in Chapter Mode

**File:** `src/yt_study/pipeline/_execution.py` → `process_single_video`
**Severity:** Medium

For chapter-mode videos, notes go into `pipeline.output_dir/video_title/` (a subdirectory), but transcript export always goes to `pipeline.output_dir`:

```python
if pipeline.export_transcript:
    pipeline_module.export_transcript(
        pipeline.db, transcript_obj, title,
        pipeline.output_dir,   # ← always the parent dir, not the chapter dir
        video_id, pipeline.export_transcript,
    )
```

**Impact:** Chapter-mode output layout:
```
./output/
├── My Video Title/
│   ├── 01_Introduction.md
│   └── 02_Core_Concepts.md
└── My Video Title_transcript.json   ← WRONG: should be inside My Video Title/
```

**Fix:** Move transcript export after `output_target` is resolved. Pass `output_target` (for chapter mode) or `pipeline.output_dir` (for single mode):
```python
transcript_output_dir = output_target if (use_chapters and output_target) else pipeline.output_dir
pipeline_module.export_transcript(pipeline.db, transcript_obj, title,
    transcript_output_dir, video_id, pipeline.export_transcript)
```

---

### BUG-33 — `export_transcript` and `generate_and_write_quiz` Write to Directory That May Not Exist Yet

**File:** `src/yt_study/pipeline/_execution.py` and `src/yt_study/pipeline/_artifacts.py`
**Severity:** Medium

`export_transcript()` is called at line ~95 in `_execution.py`, before `output_target.mkdir()` is called at line ~131 (chapter mode) or line ~223 (single mode). On a fresh run with a non-existent output directory, the file write in `_artifacts.py` fails with `FileNotFoundError` because:

```python
# _artifacts.py — no mkdir call:
export_path = output_dir / f"{safe_title}_transcript.json"
export_path.write_text(json.dumps(data, ...), ...)   # ← FileNotFoundError if dir doesn't exist
```

**Fix:** Add `output_dir.mkdir(parents=True, exist_ok=True)` at the top of both `export_transcript()` and `generate_and_write_quiz()` in `_artifacts.py`:
```python
def export_transcript(db, transcript, title, output_dir, video_id, export_format):
    output_dir.mkdir(parents=True, exist_ok=True)   # ← add this
    safe_title = sanitize_filename(title)
    ...
```

---

### BUG-34 — `_WorkerSlotManager.acquire()` Uses `list.pop(0)` Which Is O(n)

**File:** `src/yt_study/cli/_types.py` → `_WorkerSlotManager`
**Severity:** Very Low (negligible for typical concurrency ≤10, cosmetic)

```python
self._available: list[int] = list(range(concurrency))
...
slot = self._available.pop(0)   # ← O(n) list shift
```

**Fix:** Use `collections.deque` for O(1) popleft:
```python
from collections import deque
self._available: deque[int] = deque(range(concurrency))
...
slot = self._available.popleft()
...
self._available.append(slot)   # release back
```

---

### BUG-35 — `VideoRecord` Has No `cached_at` Timestamp, Making Cache Expiry Impossible

**File:** `src/yt_study/storage/models.py` → `VideoRecord`
**Severity:** Medium (blocks TASK-11 cache prune feature)

```python
class VideoRecord(Base):
    __tablename__ = "video"
    id: Mapped[str]
    title: Mapped[str]
    duration: Mapped[int]
    # ← NO timestamp column at all
```

`RunStatsRecord` and `ExportRecord` have `timestamp` columns, but `VideoRecord` (the cache entry itself) has no creation/update timestamp. This makes it impossible to implement `yt-study cache prune --older-than 30` without adding a migration.

**Fix:** Add `cached_at` column to `VideoRecord` via migration:
```python
# In models.py:
cached_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    nullable=False,
    default=lambda: datetime.now(timezone.utc),
    index=True,
)
# In migrations.py:
_VIDEO_ADDITIVE_COLUMNS = {
    "cached_at": "ALTER TABLE video ADD COLUMN cached_at DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))"
}
```

---

### BUG-36 — `get_video_chapters()`, `get_video_title()`, `get_video_duration()` Are Dead Functions

**File:** `src/yt_study/youtube/metadata.py`
**Severity:** Low (maintenance debt)

The docstring for `get_video_metadata()` explicitly says it "Replaces three separate `get_video_title` / `get_video_duration` / `get_video_chapters` calls". These three functions are defined but never called anywhere in `src/`. They perform unnecessary extra network round-trips (each makes a separate HTTP call) and represent dead interface surface.

**Fix:** Remove `get_video_chapters()`, `get_video_title()`, and `get_video_duration()` from `metadata.py`. Verify no external consumer exists before removing.

---

## Task Backlog

---

### TASK-01 — Fix All 36 Bugs

**Priority:** P0 — complete before any feature work
**Commit groupings (suggested order):**

| Commit | Bugs | Description |
|---|---|---|
| `fix: config env-file read amplification` | BUG-01 | Cache `_parse_env_file` result; 1 disk read per init |
| `fix: cli startup ordering and env-only setup` | BUG-16, BUG-17 | Env keys satisfy setup check; preflight before wizard |
| `fix: batch no-ui headless event emission` | BUG-24 | `emit_headless_event` in `--no-ui` batch mode |
| `fix: playlist privacy real availability check` | BUG-21 | Remove naive title string-match |
| `fix: metadata silent failure propagation` | BUG-23 | Re-raise ExtractionError instead of empty metadata |
| `fix: language fallback warning` | BUG-20 | Log warning before returning wrong-language fallback |
| `fix: force-mode double DB query` | BUG-04 | Single `_get_cached_video` call |
| `fix: PipelineMetrics __bool__` | BUG-02 | Add `__bool__` to domain type |
| `fix: LLMGenerationError double-wrap` | BUG-29 | Exclude LLMGenerationError from outer catch |
| `fix: export_transcript dir and timing` | BUG-32, BUG-33 | Correct dir in chapter mode; mkdir before write |
| `fix: dashboard double-markup and empty playlist` | BUG-05, BUG-12 | Remove style param; early exit on empty video_ids |
| `fix: batch file path heuristic` | BUG-13 | Remove `"/" in value` |
| `fix: setup wizard infinite loop and isolation` | BUG-09, BUG-10 | else clause; console param |
| `fix: export_transcript attribute rename` | BUG-11 | Rename to export_transcript_format |
| `fix: thread-safe logging global` | BUG-14 | threading.Lock on _SESSION_LOG_PATH write |
| `fix: sanitize_filename reserved name order` | BUG-15 | Reserved check before truncation |
| `fix: client reuse on transcript retry` | BUG-22 | Create client once before retry loop |
| `fix: defer playlist dir creation` | BUG-25 | Remove mkdir from prepare_source |
| `fix: load_config quote stripping` | BUG-26 | `.strip("'\""` in setup_wizard.load_config |
| `fix: logging idempotency guard` | BUG-27 | _LOGGING_CONFIGURED flag |
| `fix: max_tokens identity check` | BUG-30 | `if max_tokens is not None:` |
| `fix: WorkerSlotManager O(1) deque` | BUG-34 | collections.deque with popleft() |
| `fix: error classification auth vs filesystem` | BUG-18 | Auth branches before permission-denied |
| `feat: concurrent batch enqueue` | BUG-28 | asyncio.create_task per URL, bounded semaphore |
| `chore: remove dead code` | BUG-06, BUG-19, BUG-31, BUG-36 | Dead constant, dead methods, unused import |
| `fix: test infra — clear limiters in conftest` | BUG-08 | `clear_youtube_limiters()` in isolate_state_dir |
| `fix: slot exhaustion warning` | BUG-07 | structlog warning on acquire() → None |
| `fix: VideoRecord add cached_at via migration` | BUG-35 | Migration + model column (prereq for TASK-11) |

---

### TASK-02 — Migrate `mypy` → `ty` (Astral)

**Priority:** P1
**Reference:** https://docs.astral.sh/ty/
**Depends on:** TASK-01 (clean baseline)

`ty` is Astral's Rust-based type checker (stable alpha 2026-03-19). 10–100× faster than mypy. Completes the Astral toolchain alongside `uv` and `ruff`.

**Commit 1 — `chore: add ty alongside mypy`**
```toml
# pyproject.toml dev deps: add "ty>=0.0.0a1"
[tool.ty]
python-version = "3.10"
[tool.ty.src]
include = ["src/yt_study"]
```
Run `uv run ty check src/yt_study`. Address all diagnostics. Known hotspots:
- `AppSettings()` call-arg ignores (`config.py` ~lines 257, 263)
- `Group(*elements)` in `dashboard.py` (ignore already present)
- `Any`-typed fields in `CliProcessContext` (intentional; suppress per-line)

**Commit 2 — `chore: replace mypy with ty in CI and pre-commit`**
```yaml
# ci-main.yml: - name: Type check (ty)
#               run: uv run ty check src/yt_study
# .pre-commit-config.yaml:
#   - id: ty
#     entry: uv run ty check src/yt_study
#     language: system; pass_filenames: false; types: [python]
```

**Commit 3 — `chore: remove mypy fully`**
- Remove `"mypy>=1.19.1"`, `"types-setuptools"`, `[tool.mypy]` from `pyproject.toml`
- Makefile: replace `MYPY` var with `TY := $(UV_RUN) ty`; add `.ty_cache` to `FIND_CACHE`
- `README.md` badge: `[![Type Checked](https://img.shields.io/badge/Type%20Checked-ty-orange)](https://docs.astral.sh/ty/)`
- Update `CONTRIBUTING.md`; run `uv lock`

---

### TASK-03 — Wire Parallel Chapter Generation

**Priority:** P1 — infrastructure already complete, just unwired
**Depends on:** TASK-01 BUG-03 commit

**Commit: `feat: wire generate_chapter_notes_concurrent in _execution.py`**

Replace sequential `for` loop in `_execution.py`:
```python
# Generate all chapters concurrently (semaphore inside the method)
chapter_notes = await pipeline.generator.generate_chapter_notes_concurrent(
    chapter_transcripts,
    max_concurrent=config.max_concurrent_chapters,
    video_title=title,
    on_chapter_start=lambda i, total: emit(
        EventType.CHAPTER_GENERATING, video_id,
        title=title, chapter_number=i, total_chapters=total
    ),
)

# Write in stable chapter order (gather doesn't guarantee dict order)
for i, chap_title in enumerate(chapter_transcripts.keys(), 1):
    safe_chapter = sanitize_filename(chap_title)
    chapter_file = output_target / f"{i:02d}_{safe_chapter}.md"
    if not pipeline.force and chapter_file.exists():
        continue
    chapter_file.write_text(chapter_notes[chap_title], encoding="utf-8")
```

**Test:** Integration test asserting that with `max_concurrent_chapters=2` and 3 chapters, the mock LLM is called at most 2 times concurrently.

---

### TASK-04 — Make the CLI Super Fast

**Priority:** P1 — `version`, `config-path`, `--help` all pay the full pipeline startup cost
**Depends on:** TASK-01 BUG-01, BUG-27

#### Root Causes

1. **Top-level `_runtime` import** — `from yt_study.cli._runtime import CliProcessRunner` at `app.py` module level triggers the full import chain: `_runtime → _batch_runner, _context, _single_runner → pipeline.core → SQLAlchemy, LiteLLM, YouTube modules, etc.`
2. **Config read amplification** — 18× disk reads per settings init (fixed in BUG-01)
3. **New `Console()` on every call** — `_get_console()` creates a fresh instance each time
4. **`configure_logging()` re-runs** — creates new log file on every invocation (fixed in BUG-27)
5. **`LLMProvider.__init__` calls `config.get_api_key_name_for_model()`** — triggers settings construction at provider creation time

#### Commits

**`perf: defer _runtime import to process() command body`**
```python
# app.py — REMOVE top-level import:
# from yt_study.cli._runtime import CliProcessRunner

# ADD inside process() command:
def process(...):
    from yt_study.cli._runtime import CliProcessRunner  # deferred
    ...
```
`version`, `config-path`, and `--help` now complete without loading the pipeline runtime.

**`perf: cache console instance and profile import chain`**
```python
_console: Any = None
def _get_console() -> Any:
    global _console
    if _console is None:
        from rich.console import Console
        _console = Console()
    return _console
```

Profile before and after every change:
```bash
# Establish baseline:
python -X importtime -m yt_study version 2>&1 | sort -k2 -n -r | head -30
time yt-study version      # target: ≤ 300ms cold start
time yt-study --help       # target: ≤ 500ms cold start
time yt-study config-path  # target: ≤ 200ms cold start
```

**`ci: add startup smoke gate`**
```yaml
- name: CLI startup smoke
  run: python -c "
  import subprocess, time
  t = time.perf_counter()
  r = subprocess.run(['yt-study', 'version'], capture_output=True)
  elapsed = time.perf_counter() - t
  assert r.returncode == 0, f'Non-zero exit: {r.returncode}'
  assert elapsed < 1.0, f'Startup too slow: {elapsed:.2f}s'
  "
```

---

### TASK-05 — Beautiful ASCII Banner and Enhanced CLI Landing

**Priority:** P1 — first impression on every invocation
**Depends on:** TASK-01, TASK-04

#### Banner Design

Create `src/yt_study/cli/_banner.py`:

```python
"""ASCII brand banner for yt-study CLI."""

from __future__ import annotations

from rich.console import Console
from rich.text import Text


# Primary banner — shown on yt-study (no args)
_BANNER_ART = r"""
 ██╗   ██╗████████╗    ███████╗████████╗██╗   ██╗██████╗ ██╗   ██╗
 ╚██╗ ██╔╝╚══██╔══╝    ██╔════╝╚══██╔══╝██║   ██║██╔══██╗╚██╗ ██╔╝
  ╚████╔╝    ██║       ███████╗   ██║   ██║   ██║██║  ██║ ╚████╔╝
   ╚██╔╝     ██║       ╚════██║   ██║   ██║   ██║██║  ██║  ╚██╔╝
    ██║      ██║       ███████║   ██║   ╚██████╔╝██████╔╝   ██║
    ╚═╝      ╚═╝       ╚══════╝   ╚═╝    ╚═════╝ ╚═════╝    ╚═╝"""

# Compact banner — shown inside commands where space is limited
_BANNER_COMPACT = "🎓  [bold cyan]yt-study[/bold cyan]"


def print_banner(console: Console, *, compact: bool = False) -> None:
    """Print the yt-study brand banner. No side effects at import time."""
    if compact:
        console.print(_BANNER_COMPACT)
        return

    try:
        from yt_study import __version__ as ver
    except ImportError:
        ver = "dev"

    console.print(_BANNER_ART, style="bold cyan", highlight=False)
    console.print()
    console.print(
        f"  [dim]🎓  AI-Powered YouTube Study Notes  "
        f"·  v{ver}  "
        f"·  400+ LLM models[/dim]"
    )
    console.print(
        "  [dim]──────────────────────────────────────────────────[/dim]"
    )
    console.print()
```

#### Enhanced No-Command Landing

Replace bare `ctx.get_help()` in `main()` callback:

```python
@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        console = _get_console()
        from yt_study.cli._banner import print_banner
        print_banner(console)
        console.print("[bold]Quick Start[/bold]")
        console.print()
        console.print('  [cyan]yt-study process "https://youtube.com/watch?v=ID"[/cyan]    [dim]Single video[/dim]')
        console.print('  [cyan]yt-study process "https://youtube.com/playlist?list=ID"[/cyan]  [dim]Full playlist[/dim]')
        console.print('  [cyan]yt-study process urls.txt[/cyan]                               [dim]Batch file[/dim]')
        console.print()
        console.print("[bold]Commands[/bold]")
        console.print()
        console.print("  [cyan]process[/cyan]      Generate study notes from YouTube content")
        console.print("  [cyan]setup[/cyan]        Configure API keys interactively")
        console.print("  [cyan]stats[/cyan]        Show processing statistics")
        console.print("  [cyan]history[/cyan]      Recently processed videos")
        console.print("  [cyan]info[/cyan]         Inspect a video or playlist URL")
        console.print("  [cyan]cache[/cyan]        Manage the local SQLite cache")
        console.print("  [cyan]logs[/cyan]         View session log files")
        console.print("  [cyan]doctor[/cyan]       Check configuration health")
        console.print("  [cyan]version[/cyan]      Show installed version")
        console.print()
        console.print(
            "  [dim]Run [cyan]yt-study COMMAND --help[/cyan] for details on any command.[/dim]"
        )
        console.print()
```

#### Rules
- No banner in `--no-ui` output paths
- No changes to command names, flags, or argument shapes
- Headless markers unchanged: `"Done:"`, `"Batch Completed"`, `"Current log:"`
- Banner is importable without side effects — no print at import time
- Compact banner available for use inside command output when space is tight

---

### TASK-06 — New CLI Commands

**Priority:** P1 — gap in user-facing functionality; all backed by existing DB and infrastructure

---

#### 6a. `yt-study stats` — Processing Statistics

**Commit: `feat: add stats command`**

```
yt-study stats
yt-study stats --model gemini/gemini-2.5-flash
yt-study stats --since 30d
```

Output (Rich table):
```
┌────────────────── Processing Statistics ──────────────────┐
│  Videos processed:     47                                  │
│  Total tokens used:    2,847,391                           │
│  Total cost (USD):     $4.23                               │
│  Transcript time:      8m 34s                              │
│  Generation time:      23m 12s                             │
├────────────────────────────────────────────────────────────┤
│  Model breakdown:                                          │
│  ├── gemini/gemini-2.5-flash    38 videos   $2.14          │
│  └── gpt-4o-mini                 9 videos   $2.09          │
└────────────────────────────────────────────────────────────┘
```

Implementation: query `RunStatsRecord` grouped by model, summed. Add `get_stats(since_days=None)` to `DatabaseRepository`.

---

#### 6b. `yt-study history [--limit N]` — Recently Processed Videos

**Commit: `feat: add history command`**

```
yt-study history
yt-study history --limit 20
```

Output (Rich table):
```
┌─────────────────── Recent Videos ──────────────────────────┐
│  #   Title                            Model         Cost   │
│  ─   ─────────────────────────────── ─────────────  ────  │
│  1   Introduction to Machine Learning  gemini-2.5-flash $0.04 │
│  2   Async Python Deep Dive            gpt-4o-mini  $0.11 │
│  ...                                                       │
└────────────────────────────────────────────────────────────┘
```

Implementation: join `VideoRecord` with latest `RunStatsRecord` ordered by `timestamp DESC`. Add `get_recent_videos(limit=10)` to `DatabaseRepository`.

---

#### 6c. `yt-study info <url>` — Inspect Without Processing

**Commit: `feat: add info command`**

```
yt-study info "https://youtube.com/watch?v=ID"
yt-study info "https://youtube.com/playlist?list=ID"
```

Output:
```
┌─────────────── Video Info ─────────────────┐
│  Title:       Introduction to ML           │
│  Duration:    1h 23m 45s                   │
│  Chapters:    8 chapters detected          │
│  Transcript:  en, en-auto, es, fr          │
│  Cached:      ✓  (processed 3 days ago)   │
└────────────────────────────────────────────┘
```

For playlists:
```
┌──────────────── Playlist Info ─────────────┐
│  Title:       Machine Learning Course      │
│  Videos:      24                           │
│  Cached:      12/24 already processed      │
└────────────────────────────────────────────┘
```

Implementation: calls `get_video_metadata()` and `extract_playlist_videos()` without running the pipeline. Checks DB cache for existing entries. Must show a progress spinner since this makes network calls.

---

#### 6d. `yt-study doctor` — Configuration Health Check

**Commit: `feat: add doctor command`**

```
yt-study doctor
```

Output:
```
┌──────────── yt-study Doctor ───────────────┐
│                                             │
│  ✅  Config file:   ~/.yt-study/config.env │
│  ✅  GEMINI_API_KEY set                     │
│  ✅  Output dir:    ./output (writable)     │
│  ✅  Cache DB:      ~/.yt-study/.yt_study_  │
│                     cache.db (128 KB)       │
│  ⚠️   Log dir:      26 log files            │
│  ❌  OPENAI_API_KEY not set                 │
│                                             │
│  Status: [green]Ready[/green]               │
└────────────────────────────────────────────┘
```

Checks: config file exists, API key for default model is set, output dir is writable, cache DB accessible, log dir size, network reachability (optional with `--network`).

---

#### 6e. `yt-study cache` — Cache Management Sub-Commands

**Commit: `feat: add cache sub-commands`**

```
yt-study cache info           DB path, row count, disk size, oldest/newest entry
yt-study cache clear          Interactive clear (requires confirmation)
yt-study cache clear --yes    Skip confirmation
yt-study cache prune --older-than 30  Remove entries older than N days
yt-study cache show <video-id>        Show cached metadata for a specific video
```

`cache info` output:
```
┌─────────────── Cache Info ───────────────┐
│  Location:   ~/.yt-study/.yt_study_cache.db │
│  Size:       4.2 MB                      │
│  Videos:     47 entries                  │
│  Oldest:     2025-08-14 (213 days ago)   │
│  Newest:     2026-03-20 (1 day ago)      │
└──────────────────────────────────────────┘
```

Implementation: thin Typer sub-app wrapping `DatabaseRepository`. `cache prune` depends on BUG-35 fix (adds `cached_at` column).

---

#### 6f. `yt-study logs` — Log File Management

**Commit: `feat: add logs sub-commands`**

```
yt-study logs                  Show log dir, 5 most recent files with sizes
yt-study logs --tail 100       Tail the latest session log (100 lines)
yt-study logs --open           Open log dir in file manager
yt-study logs clean            Remove all log files older than 7 days
yt-study logs clean --all      Remove all log files
```

`logs` output:
```
┌──────────────── Session Logs ────────────────┐
│  Directory: ~/.yt-study/logs/                │
│  Total:     26 files (14.3 MB)               │
│                                              │
│  Recent:                                     │
│  ├── yt-study-2026-03-21_14-32-11.log  2.1KB │
│  ├── yt-study-2026-03-20_09-15-44.log  8.7KB │
│  └── yt-study-2026-03-19_22-01-02.log  1.2KB │
└──────────────────────────────────────────────┘
```

---

#### 6g. `yt-study edit-config` — Open Config in Editor

**Commit: `feat: add edit-config command`**

```
yt-study edit-config
```

Opens `~/.yt-study/config.env` in `$EDITOR` (fallback: `nano` on Linux/macOS, `notepad` on Windows). If no config exists, runs setup wizard first with a hint.

---

#### 6h. `yt-study setup --show` — Show Current Configuration

**Commit: `feat: add setup --show flag`**

```
yt-study setup --show
```

Displays current configuration (with API keys partially masked) without running the wizard.

```
┌──────────── Current Configuration ──────────────┐
│  Config:   ~/.yt-study/config.env                │
│                                                   │
│  DEFAULT_MODEL         gemini/gemini-2.5-flash   │
│  GEMINI_API_KEY        AIzaSy...b4Kw (set)       │
│  OPENAI_API_KEY        (not set)                  │
│  OUTPUT_DIR            ./output                   │
│  MAX_CONCURRENT_VIDEOS  5                         │
└──────────────────────────────────────────────────┘
```

---

### TASK-07 — Dashboard Visual Refactor

**Priority:** P1 — failures render after completions (wrong urgency); markup leakage risk
**Depends on:** TASK-01 BUG-05, BUG-12

**Commit: `feat: dashboard — failures first, unicode ellipsis, escape worker titles`**

Changes to `dashboard.py`:
- **Failures before completions:** `recent_failures` section renders above `recent_completions`
- **Unicode ellipsis:** `title[:60] + "…"` (U+2026), not `"..."`
- **Escape worker titles:** Apply `rich.markup.escape()` to titles before insertion into `UI_STATUS_MAP` status strings (the `__rich__` activity log already uses `escape()`; worker status strings do not)
- Keep all public methods and constructor signature unchanged

Target layout:
```
╭─ 🎓 YouTube Study Material Pipeline ──────────────────────────╮
│ 📑 Playlist: Machine Learning Course   🤖 gemini-2.5-flash     │
│ ────────────────────────────────────────────────────────────── │
│ Total Progress  ████████████░░░░░  62%  •  13/21  •  0:02:14   │
│ ────────────────────────────────────────────────────────────── │
│ ⚡ Active Tasks                                                  │
│   ├── Worker 1  ⠸  Lecture 5: Transformers… (Chunk 2/3)        │
│   └── Worker 2  ⠼  Lecture 6: Fine-tuning… (Generating)        │
│ ────────────────────────────────────────────────────────────── │
│ ❌ Recent Failures                                               │
│   ✗ Lecture 2: Members-only content                             │
│ ✅ Recent Completions                                            │
│   ✓ Lecture 4: Async Programming                                │
│   ✓ Lecture 3: Type Hints in Python                             │
╰────────────────────────────────────────────────────────────────╯
```

---

### TASK-08 — Mintlify Documentation Scaffold

**Priority:** P0 — no docs surface beyond README
**Depends on:** Nothing — start in parallel

**Commit 1 — `docs: add docs.json and initial MDX tree`**

```
docs.json
docs/
├── getting-started/
│   ├── index.mdx              ← What is yt-study; 30-second overview
│   ├── installation.mdx       ← pip/uv install; Python ≥3.10
│   ├── quickstart.mdx         ← First video in 2 minutes
│   └── first-video.mdx        ← Annotated walkthrough
├── cli-reference/
│   ├── process.mdx            ← Full flags, examples, exit codes
│   ├── setup.mdx
│   ├── stats.mdx              ← New in TASK-06
│   ├── history.mdx
│   ├── info.mdx
│   ├── cache.mdx
│   ├── logs.mdx
│   ├── doctor.mdx
│   ├── config-path.mdx
│   └── version.mdx
├── configuration/
│   ├── overview.mdx           ← Load order: init args > env vars > config.env
│   ├── api-keys.mdx           ← All 8 providers, key names, links
│   ├── output.mdx
│   └── advanced.mdx
├── troubleshooting/
│   ├── api-keys.mdx
│   ├── transcripts.mdx
│   ├── private-videos.mdx
│   └── rate-limits.mdx
├── development/
│   ├── setup.mdx
│   ├── testing.mdx
│   ├── ty-type-checking.mdx
│   └── contributing.mdx
└── architecture/
    ├── overview.mdx
    ├── pipeline.mdx
    ├── storage.mdx
    └── youtube-extractor.mdx
```

Every page **must** include `description` frontmatter — Mintlify uses this to build `llms.txt` for AI agent discovery.

`docs.json` minimal scaffold:
```json
{
  "$schema": "https://mintlify.com/schema.json",
  "name": "yt-study",
  "colors": { "primary": "#0EA5E9" },
  "topbarLinks": [{"name": "GitHub", "url": "https://github.com/whoisjayd/yt-study"}],
  "navigation": [
    {"group": "Getting Started", "pages": ["getting-started/index", "getting-started/installation", "getting-started/quickstart"]},
    {"group": "CLI Reference", "pages": ["cli-reference/process", "cli-reference/setup", "cli-reference/stats", "cli-reference/history", "cli-reference/info", "cli-reference/cache", "cli-reference/logs", "cli-reference/doctor", "cli-reference/config-path", "cli-reference/version"]},
    {"group": "Configuration", "pages": ["configuration/overview", "configuration/api-keys", "configuration/output", "configuration/advanced"]},
    {"group": "Troubleshooting", "pages": ["troubleshooting/api-keys", "troubleshooting/transcripts", "troubleshooting/private-videos", "troubleshooting/rate-limits"]},
    {"group": "Development", "pages": ["development/setup", "development/testing", "development/ty-type-checking", "development/contributing"]},
    {"group": "Architecture", "pages": ["architecture/overview", "architecture/pipeline", "architecture/storage", "architecture/youtube-extractor"]}
  ]
}
```

**Commit 2 — `docs: slim README and update CONTRIBUTING`**

`README.md` ≤ 60 lines: install command, 3-line quick-start, link to docs.
`CONTRIBUTING.md`: `## Documentation` section with `mintlify dev` instructions (Node.js ≥20.17).

---

### TASK-09 — Per-Subfolder AGENTS.md Files

**Priority:** P1 — dramatically reduces AI agent token cost per subfolder
**Depends on:** Nothing — start now; drafts in companion zip files

**Commit: `docs: add per-subfolder AGENTS.md files`**

Merge and de-duplicate drafts from `chrome_agents/` and `edge_agents/` zip files.

| File | Max Lines | Key content |
|---|---|---|
| `src/yt_study/cli/AGENTS.md` | 300 | Data flow CLI→pipeline; all 9 files; `UI_STATUS_MAP`; headless markers; patch points; BUG-24 fix |
| `src/yt_study/pipeline/AGENTS.md` | 300 | `CorePipeline` facade; execution flow; `generate_chapter_notes_concurrent` (wired after TASK-03); event contract |
| `src/yt_study/youtube/AGENTS.md` | 300 | Extractor hierarchy; transcript retry; language selection (BUG-20); playlist; privacy check (BUG-21 fix) |
| `src/yt_study/storage/AGENTS.md` | 300 | Singleton pattern; write lock; schema migration; test isolation |
| `src/yt_study/ui/AGENTS.md` | 300 | Dashboard rendering; setup wizard; console injection fix |
| `src/yt_study/llm/AGENTS.md` | 200 | `LLMProvider`; `UsageTotals`; `StudyMaterialGenerator` chunking; BUG-29 fix |
| `src/yt_study/domain/AGENTS.md` | 150 | All domain dataclasses; `PipelineEvent` fields; `VideoMetadata`; `PipelineResult` |
| `tests/AGENTS.md` | 200 | Test structure; `conftest.py` autouse fixtures; `isolate_state_dir` pattern; E2E gate |

Each file covers: **Purpose · File map · Public API · Invariants · Gotchas · Test locations · What must NOT change.**

Update root `AGENTS.md` → navigation index for all child files.

---

### TASK-10 — Targeted Test Expansion

**Priority:** P1
**Depends on:** TASK-01 (correct behavior before writing tests)

**`test: cli/_source_resolution.py`** (new file)
- `prepare_source` with invalid URL, missing IDs → `UserVisibleCliError`
- Playlist extraction failure propagation
- `failure_rows_for_result` edge cases
- `ordered_batch_failures_from_error` sort key stability
- `batch_failure_label` playlist vs direct video

**`test: cli/_display.py`** (new file)
- `emit_headless_event` for all `EventType`s in `HEADLESS_LABELS`
- `VIDEO_FAILED` → no output (early return)
- `build_ui_event_handler` full acquire-update-release cycle
- Slot exhaustion → structlog warning
- `print_batch_summary` with and without failures
- Batch `--no-ui` emits headless events (post BUG-24)

**`test: cli/_formatters.py`** (new file)
- `print_cost_summary` skips on zero metrics (post BUG-02)
- `print_cost_summary` renders on non-zero tokens
- `print_run_summary` skips on `total_count=0`
- Failure panel variants

**`test: config.py extensions`**
- `_parse_env_file` called exactly once (post BUG-01)
- Full precedence chain: init args > env vars > config.env
- Quoted values stripped correctly
- `model_post_init` syncs all 8 API keys

**`test: errors.py extensions`**
- `format_user_error` auth vs filesystem disambiguation (post BUG-18)
- All `raise_if_video_unavailable` text variants
- Language fallback warning (post BUG-20)

**`test: ui/dashboard.py extensions`**
- `concurrency=0` renders without error
- Failures section before completions (post TASK-07)
- Unicode ellipsis at 60 chars
- Rich markup in title → escaped safely

**`test: integration/cli/test_cli.py extensions`**
- All 4 existing + new commands exit 0 with `--help`
- `version` prints semver string
- `looks_like_batch_file_path` parametrized: `vimeo.com/123456` → `False`

**`test: e2e smoke extensions (RUN_E2E=1)`**
- Batch file with two public videos → exits 0
- `--quiz` → quiz file present
- `--export-transcript json` → JSON with segment fields

---

### TASK-11 — Storage Hardening

**Priority:** P2
**Depends on:** TASK-01 BUG-35 (adds `cached_at` column)

**Commit 1: `feat: schema version table and migration runner`**

Replace `repair_runstats_schema` one-off with a proper `schema_version` table and numbered migration runner. Future schema changes apply in sequence:
```python
MIGRATIONS: list[tuple[int, str]] = [
    (1, "add runstats columns"),      # existing repair_runstats_schema logic
    (2, "add video.cached_at"),       # BUG-35 fix
]
```

**Commit 2: `feat: cache prune and repository methods`**

Add `get_recent_videos(limit=10)`, `get_stats(since_days=None)`, `prune_old_entries(older_than_days=30)` to `DatabaseRepository`. These back the new CLI commands.

---

### TASK-12 — YouTube Extractor HTTP Retry

**Priority:** P2 — transport layer is the only unguarded retry level
**Depends on:** TASK-01 BUG-22

**Commit: `feat: HTTP retry/backoff at transport layer`**

Add `_fetch_with_retry()` to `_transport.py`:
- Retry on: `TimeoutError`, `ConnectionResetError`, `RemoteDisconnected`, HTTP 429/500/502/503/504
- Exponential backoff with jitter: `HTTP_BACKOFF_BASE * (2 ** attempt) * random.uniform(0.8, 1.2)`
- Never retry: parse failures (`ExtractionError`), HTTP 401/403/404 → `VideoUnavailableError` immediately
- Add `HTTP_MAX_RETRIES = 3`, `HTTP_BACKOFF_BASE = 1.0` to `_constants.py`

Tests (`tests/unit/youtube/test_extractor_transport.py`):
- Success on first try
- Success after 2 transient 503 failures
- Exhausted retries → `ExtractionError`
- HTTP 404 → raises immediately, 0 retries

---

### TASK-13 — CI and Makefile Hardening

**Priority:** P2
**Depends on:** TASK-02 for ty steps

- `--cov-fail-under=93` in pytest coverage CI step
- Replace mypy step with ty (in TASK-02)
- Update `pyproject.toml` Documentation URL to Mintlify site once live
- Makefile: add `.ty_cache` to `FIND_CACHE` (replace `.mypy_cache`)
- Root `AGENTS.md`: update with docs-site location and ty workflow

---

### TASK-14 — Benchmark Harness

**Priority:** P3
**Depends on:** TASK-04

Document in `docs/development/performance.mdx`:
```bash
# Startup benchmarks (run before/after any import graph changes)
time yt-study version
time yt-study --help
time yt-study config-path

# Import-time profiling
python -X importtime -m yt_study version 2>&1 | sort -k2 -n -r | head -30
python -X importtime -m yt_study --help 2>&1 | sort -k2 -n -r | head -20
```

Record baseline numbers. Consider non-blocking CI job for performance snapshots.

---

## Commit Plan

```
Phase 1 — Correctness (land first, unblocks everything)
──────────────────────────────────────────────────────────────────
  1.  fix: config env-file read amplification                   [BUG-01]
  2.  fix: cli startup ordering, env-only setup                 [BUG-16, 17]
  3.  fix: batch --no-ui headless event emission                [BUG-24]
  4.  fix: playlist privacy real availability check             [BUG-21]
  5.  fix: metadata silent failure propagation                  [BUG-23]
  6.  fix: language fallback warning                            [BUG-20]
  7.  fix: force-mode double DB query                           [BUG-04]
  8.  fix: PipelineMetrics __bool__                             [BUG-02]
  9.  fix: LLMGenerationError double-wrap                       [BUG-29]
  10. fix: export_transcript dir and timing                     [BUG-32, 33]
  11. fix: dashboard double-markup, empty playlist guard        [BUG-05, 12]
  12. fix: batch file path heuristic false-positive             [BUG-13]
  13. fix: setup wizard infinite loop and console isolation     [BUG-09, 10]
  14. fix: export_transcript attribute rename                   [BUG-11]
  15. fix: thread-safe logging global                           [BUG-14]
  16. fix: sanitize_filename reserved-name order                [BUG-15]
  17. fix: client reuse on transcript retry                     [BUG-22]
  18. fix: defer playlist dir creation                          [BUG-25]
  19. fix: load_config quote stripping                          [BUG-26]
  20. fix: logging idempotency guard                            [BUG-27]
  21. fix: max_tokens identity check                            [BUG-30]
  22. fix: WorkerSlotManager O(1) deque                         [BUG-34]
  23. fix: error classification auth vs filesystem              [BUG-18]
  24. feat: concurrent batch enqueue                            [BUG-28]
  25. chore: remove dead code                                   [BUG-06, 19, 31, 36]
  26. fix: test infra — clear limiters in conftest              [BUG-08]
  27. fix: slot exhaustion warning                              [BUG-07]
  28. fix: VideoRecord cached_at migration                      [BUG-35]

Phase 2 — Performance
──────────────────────────────────────────────────────────────────
  29. feat: wire generate_chapter_notes_concurrent              [TASK-03]
  30. perf: defer _runtime import to process() body             [TASK-04 commit 1]
  31. perf: cache console instance                              [TASK-04 commit 2]
  32. ci: startup smoke gate                                    [TASK-04 commit 3]

Phase 3 — Type Safety
──────────────────────────────────────────────────────────────────
  33. chore: add ty alongside mypy                              [TASK-02 commit 1]
  34. chore: replace mypy with ty in CI and pre-commit          [TASK-02 commit 2]
  35. chore: remove mypy fully, update all references           [TASK-02 commit 3]

Phase 4 — New Features
──────────────────────────────────────────────────────────────────
  36. feat: ASCII banner and enhanced no-command landing        [TASK-05]
  37. feat: stats command                                       [TASK-06a]
  38. feat: history command                                     [TASK-06b]
  39. feat: info command                                        [TASK-06c]
  40. feat: doctor command                                      [TASK-06d]
  41. feat: cache sub-commands                                  [TASK-06e]
  42. feat: logs sub-commands                                   [TASK-06f]
  43. feat: edit-config and setup --show                        [TASK-06g/h]
  44. feat: dashboard visual refactor                           [TASK-07]

Phase 5 — DX and Documentation
──────────────────────────────────────────────────────────────────
  45. docs: per-subfolder AGENTS.md files                       [TASK-09]
  46. docs: docs.json and initial MDX tree                      [TASK-08 commit 1]
  47. docs: slim README and update CONTRIBUTING                 [TASK-08 commit 2]

Phase 6 — Test Expansion
──────────────────────────────────────────────────────────────────
  48–56. test: 9 commits, one per module (see TASK-10)

Phase 7 — Infrastructure
──────────────────────────────────────────────────────────────────
  57. feat: schema version table and migration runner           [TASK-11 commit 1]
  58. feat: repository methods for stats/history/prune          [TASK-11 commit 2]
  59. feat: HTTP retry at transport layer                       [TASK-12]
  60. ci: coverage threshold, metadata alignment               [TASK-13]
  61. docs: benchmark baseline                                  [TASK-14]
```

---

## Coverage Gap Summary

| Module | Top Uncovered Path | Risk |
|---|---|---|
| `cli/_batch_runner.py` | `--no-ui` headless path (BUG-24), concurrent enqueue (BUG-28) | High |
| `youtube/metadata.py` | `ExtractionError` swallow (BUG-23), empty metadata propagation | High |
| `youtube/extractor/_playlist.py` | Naive privacy check (BUG-21) | High |
| `cli/_source_resolution.py` | Invalid URL, missing IDs, playlist failures | High |
| `cli/_display.py` | Headless event formatting, slot exhaustion, UI handler flow | High |
| `config.py` | Config file caching (BUG-01), precedence chain, `YT_STUDY_HOME` | High |
| `youtube/extractor/_parsers.py` | Language fallback without warning (BUG-20) | Medium |
| `errors.py` | Auth vs filesystem permission branches | Medium |
| `ui/dashboard.py` | `concurrency=0`, unicode truncation, failure ordering | Medium |
| `cli/_formatters.py` | Zero-metrics guard (BUG-02), failure panel variants | Medium |
| `pipeline/_execution.py` | Concurrent chapter path (post TASK-03), force-mode DB flow | Medium |
| `llm/provider.py` | `LLMGenerationError` double-wrap (BUG-29), max_tokens identity | Medium |
| `youtube/extractor/_transport.py` | HTTP retry (TASK-12), timeout handling | Medium |
| `ui/setup_wizard.py` | Infinite loop (BUG-09), console injection (BUG-10) | Medium |
| `storage/repository.py` | Singleton teardown isolation | Low |
| `utils.py` | `sanitize_filename` reserved-name truncation boundary (BUG-15) | Low |
| `pipeline/_artifacts.py` | `mkdir` guard (BUG-33), chapter mode dir (BUG-32) | Medium |

---

## Definition of Done

- [ ] All 36 confirmed bugs fixed and regression-tested
- [ ] Batch `--no-ui` emits headless events (BUG-24)
- [ ] Playlist privacy uses real availability data (BUG-21)
- [ ] Metadata errors surface to user (BUG-23)
- [ ] `export_transcript` goes to correct directory in chapter mode (BUG-32)
- [ ] `export_transcript` creates directory before writing (BUG-33)
- [ ] Chapter generation is parallel via `generate_chapter_notes_concurrent` (TASK-03)
- [ ] `yt-study version` ≤ 300ms, `--help` ≤ 500ms, `config-path` ≤ 200ms
- [ ] `mypy` fully replaced by `ty` (CI, pre-commit, Makefile, badges, CONTRIBUTING)
- [ ] Beautiful ASCII banner on `yt-study` (no args)
- [ ] All 8 new commands ship: `stats`, `history`, `info`, `doctor`, `cache`, `logs`, `edit-config`, `setup --show`
- [ ] Mintlify docs exist and are the primary documentation surface
- [ ] README ≤ 60 lines, links to docs
- [ ] Every source subfolder has an `AGENTS.md`; root `AGENTS.md` is a navigation index
- [ ] Dashboard: failures before completions, unicode ellipsis, markup escaping
- [ ] Test coverage ≥ 93%, enforced by CI threshold
- [ ] Storage: schema versioning, `cached_at` column, prune support

---

## Compact Memory

- **Project:** `yt-study` — Python 3.10+ CLI. YouTube videos/playlists → AI-powered Markdown study notes.
- **Stack:** Typer · Rich · LiteLLM · Pydantic v2 · SQLAlchemy 2 · structlog · uv · ruff
- **Commands (current):** `process`, `setup`, `config-path`, `version`
- **Commands (new in TASK-06):** `stats`, `history`, `info`, `doctor`, `cache`, `logs`, `edit-config`, `setup --show`
- **Type checker:** migrating `mypy 1.19` → `ty` (TASK-02)
- **Docs:** none → Mintlify scaffold (TASK-08)
- **Total bugs:** 36 confirmed, source-verified
- **Top-priority bugs:** BUG-24 (batch silent), BUG-21 (playlist privacy), BUG-23 (metadata swallow), BUG-32/33 (export location/dir), BUG-16 (env-only setup), BUG-03 (sequential chapters — concurrent method exists, unwired), BUG-29 (LLMGenerationError double-wrap)
- **Parallel chapter infra:** `StudyMaterialGenerator.generate_chapter_notes_concurrent()` complete in `generation.py`. `_execution.py` ignores it. Wire it (TASK-03).
- **New bugs vs prior version:** BUG-29 (LLMGenerationError double-wrap), BUG-30 (max_tokens falsy), BUG-31 (unused import), BUG-32 (export wrong dir chapter mode), BUG-33 (export before mkdir), BUG-34 (O(n) slot manager), BUG-35 (VideoRecord no cached_at), BUG-36 (dead metadata functions)
- **Headless markers (frozen):** `"Done:"`, `"Batch Completed"`, `"Current log:"`
- **Arch rule:** CLI → Pipeline → YouTube/LLM/Storage. Never reverse.
- **conftest.py:** `isolate_state_dir` (autouse) redirects `YT_STUDY_HOME`. Add `clear_youtube_limiters()` here (BUG-08).
- **AGENTS.md:** Not yet per-subfolder. Draft content in companion zip files. Wire after TASK-01 stabilizes (TASK-09).
