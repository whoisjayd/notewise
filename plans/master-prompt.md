# yt-study — Master Agent Prompt

You are an expert Python engineer implementing the full `yt-study` refactor and feature roadmap
across **Plans 01–08**. This prompt governs every decision you make during implementation.
Read it fully before touching any file.

---

## 0. Core operating principles

### 0.1 Always use the latest stable versions

Before installing or importing any package, search for its current stable release.
**Never assume the version in your training data is current.**

Mandatory lookup pattern:

```
search: "<package-name> latest stable release pypi 2025"
fetch:  https://pypi.org/pypi/<package-name>/json   (use the `version` field)
```

Apply this to **every** dependency you touch or add:
`rich`, `typer`, `structlog`, `sqlalchemy`, `anthropic`, `openai`,
`httpx`, `anyio`, `pydantic`, `ty`, `ruff`, `pytest`, `pytest-asyncio`,
`pytest-cov`, `uv`, and any others that appear during implementation.

> ⚠️ `yt-dlp` is **NOT** a dependency of this project. See §1.5.

Lock the resolved version in `pyproject.toml` with `>=X.Y, <X+1` bounds,
not bare `>=X.Y` and not pinned to a patch version.

### 0.2 Always search before writing

For every API, configuration schema, or third-party integration, **search the live docs first**.
Do not rely on memory for:

| Topic                                     | Where to search                                                   |
| ----------------------------------------- | ----------------------------------------------------------------- |
| `rich` Panel / Live / Layout API          | `https://rich.readthedocs.io/en/latest/`                          |
| `typer` command/option signatures         | `https://typer.tiangolo.com/`                                     |
| `structlog` processor chain               | `https://www.structlog.org/en/stable/`                            |
| `httpx` async client, transport, timeouts | `https://www.python-httpx.org/`                                   |
| `anthropic` / `openai` SDK                | respective official docs sites                                    |
| `sqlalchemy` Core or ORM                  | `https://docs.sqlalchemy.org/`                                    |
| `pydantic` v2 model API                   | `https://docs.pydantic.dev/latest/`                               |
| `ty` type checker CLI flags               | `https://github.com/astral-sh/ty`                                 |
| `ruff` rule codes                         | `https://docs.astral.sh/ruff/`                                    |
| `pytest-asyncio` mode config              | `https://pytest-asyncio.readthedocs.io/`                          |
| `uv` add / lock commands                  | `https://docs.astral.sh/uv/`                                      |
| Mintlify `docs.json` schema               | `https://mintlify.com/docs`                                       |
| YouTube page structure / API changes      | search `"YouTube innertube API <year>"` or inspect live responses |

If the fetched docs contradict what you remember, **the live docs win**.

### 0.3 Search for breaking changes before upgrading

Before bumping a package version across a major boundary, search:

```
"<package> migration guide <old-major> to <new-major>"
"<package> breaking changes <new-major>"
```

Then update call sites before running tests.

### 0.4 Coding-agent execution profile (Codex style)

When running as a coding agent, follow this loop on every task:

1. Explore first, then edit:

- Read the smallest set of files that proves scope, dependencies, and invariants.
- Parallelize read-only discovery work when possible.

2. Patch minimally:

- Prefer focused diffs over broad rewrites.
- Do not reformat unrelated files.
- Preserve stable interfaces unless the plan explicitly changes them.

3. Verify immediately:

- Run the most targeted tests first, then broaden if needed.
- Confirm no new lint/type errors were introduced.

4. Report with evidence:

- Summarize what changed, why, and how it was validated.
- If a check could not be run, state it explicitly and include the blocker.

Additional agent rules:

- Prefer non-destructive git operations; never reset unrelated user changes.
- Keep task momentum: complete implementation plus verification in the same pass when feasible.
- If an assumption is uncertain, verify in source or docs before editing.
- For review requests, prioritize findings, regressions, and missing tests before summaries.

---

## 1. Repository ground rules

### 1.1 Architecture invariants — never violate

```
CLI  →  Pipeline  →  YouTube / LLM / Storage
```

- All user-facing output lives in the CLI/UI layer.
- All blocking I/O runs inside `asyncio.to_thread`.
- All pipeline progress flows through `PipelineEvent` / `on_event`.
- `DatabaseRepository` returns schema objects, never ORM objects.
- Logging in library code is `structlog`-only.

### 1.2 Frozen public contracts — do not change signatures

```python
# Existing CLI commands — names and existing flags are frozen
process | setup | config-path | version

# PipelineDashboard constructor
PipelineDashboard.__init__(total_videos, concurrency, playlist_name, model_name)

# PipelineDashboard public methods
update_worker | add_completion | add_failure | set_total_videos
update_overall_progress | update_overall_status | __rich__

# CorePipeline
CorePipeline.run()   # signature frozen

# PipelineEvent field names — frozen
```

Plan 06 may add new commands (`stats`, `history`, `info`, `doctor`, `cache`,
`logs`, `edit-config`, `setup --show`) as additive surface area, but it must
not rename or remove the existing command names or existing flag contracts.

### 1.3 Frozen headless output markers — do not modify

```
Done:
Batch Completed
Current log:
```

### 1.4 Dependency direction — enforce at every change

```
yt_study.cli      →  yt_study.pipeline  →  yt_study.youtube
                  →  yt_study.llm
                  →  yt_study.storage
yt_study.ui       →  (CLI uses ui, pipeline does NOT)
yt_study.domain   →  (shared, no upward imports)
yt_study.errors   →  (shared, no upward imports)
```

### 1.5 Native YouTube extractor — yt-dlp is FORBIDDEN

The YouTube layer in this project is a **fully native, custom implementation**.
It does **not** use `yt-dlp`, `youtube-dl`, or any third-party extraction wrapper.

#### Extractor module map

```
src/yt_study/youtube/
├── extractor/
│   ├── async_client.py  # canonical async extractor client
│   ├── client.py        # compatibility shim / legacy wrapper if still present
│   ├── _transport.py    # raw HTTP transport with retry/backoff (native httpx)
│   ├── _playlist.py     # playlist parsing — availability from page structure only
│   └── _parsers.py      # response parsers, language selection
├── transcript.py        # transcript fetch orchestration, cookie-file support
└── metadata.py          # video metadata — must propagate ExtractionError
```

#### Hard rules for the YouTube layer

- **Never add `yt-dlp` or `youtube-dl` as a dependency** for any reason.
- Never call any `yt_dlp.*` or `youtube_dl.*` API — not even as a fallback.
- All HTTP is done through the project's own `_transport.py` (backed by `httpx`).
- Playlist availability must come from parsed page/API response fields —
  never inferred from title text.
- `_transport.py` retry is bounded and covers only transient errors:
  HTTP 429, 500, 502, 503, 504, timeout, connection reset, remote disconnect.
  Do **not** retry on 401, 403, 404, parse failures, or `ExtractionError`.
- All YouTube I/O is wrapped in `asyncio.to_thread` at the extractor boundary.
- `ExtractionError` and availability errors use `yt_study.errors` hierarchy —
  never raw `Exception` or library-specific exception types leaked upward.
- When YouTube page structure changes, **inspect live responses** and fix
  the native parsers. Do not swap in yt-dlp.

#### When searching for YouTube API / page-structure information

```
search: "YouTube innertube API <endpoint> <year>"
search: "YouTube transcript API format <year>"
search: "YouTube playlist page JSON structure"
```

Inspect real response payloads. Do not assume field names are stable.

---

## 2. Toolchain

| Tool                                       | Role                                               |
| ------------------------------------------ | -------------------------------------------------- |
| `uv`                                       | package management and virtual-env                 |
| `ruff`                                     | linting + formatting (replaces black/isort/flake8) |
| `ty`                                       | type checking (replaces mypy)                      |
| `pytest` + `pytest-asyncio` + `pytest-cov` | tests                                              |
| `rich`                                     | all terminal output                                |
| `typer`                                    | CLI framework                                      |
| `structlog`                                | all library logging                                |

Always use `uv add <pkg>` to add dependencies and `uv run pytest` to run tests.
Never call `pip install` directly.

---

## 3. Plan execution order and dependencies

```
Plan 01  →  Plan 02  →  Plan 03  →  Plan 04  →  Plan 05
                                                    ↓
                                               Plan 06
                                                    ↓
                                               Plan 07  (validates all prior)
                                                    ↓
                                               Plan 08  (docs, final alignment)
```

**Do not start Plan 06 until Plan 05 repository methods exist.**
**Do not start Plan 07 until all prior plans are green.**
**Do not start Plan 08 until the CLI command surface from Plan 06 is stable.**

---

## 4. Per-plan implementation checklist

### Plan 01 — CLI setup, source resolution, headless correctness

Before writing code, search:

- `typer` current option / callback API
- `rich` Console instantiation best practices (singleton pattern)

Key rules:

- `process` must NEVER auto-launch the setup wizard.
- Env-only config is valid; check env vars before deciding setup is missing.
- Invalid input must fail BEFORE any setup or provider evaluation.
- Batch `--no-ui` must emit headless progress; `on_event=None` is forbidden.
- Playlist directories must not be created until a write is actually needed.

Fix order inside each file:

1. `app.py` — remove runtime import at module load; fix setup gating
2. `_source_resolution.py` — defer mkdir; fix `looks_like_batch_file_path()`
3. `_batch_runner.py` — always provide an event handler
4. `_single_runner.py` — guard empty `video_ids`
5. `_display.py` — clean up dead `HEADLESS_LABELS`

Test gate: all unit + integration CLI tests green before moving to Plan 02.

---

### Plan 02 — Pipeline, LLM, artifact correctness

Before writing code, search:

- `anthropic` Python SDK latest `messages.create` parameter names
- `openai` Python SDK latest completion API
- `asyncio.gather` vs `asyncio.TaskGroup` for bounded concurrency

Key rules:

- Use `generate_chapter_notes_concurrent()` — delete the dead sequential version.
- `export_transcript` attribute → rename to `export_transcript_format`; leave CLI flag unchanged.
- `LLMGenerationError` must not be double-wrapped.
- `max_tokens=0` must not be silently ignored (use `is not None`).
- Every file writer must `mkdir(parents=True, exist_ok=True)` before writing.
- Chapter-mode transcript export goes into the chapter output directory.
- Force mode must not hit SQLite twice.

Test gate: unit tests for metrics truthiness, provider error handling, and artifact writers.

---

### Plan 03 — UI, dashboard, setup wizard

Before writing code, search:

- `rich` Live / Group / Panel rendering latest API
- `rich.markup.escape` usage

Key rules:

- Remove `style` parameter from `update_worker()`.
- Escape all worker titles before embedding in Rich markup strings.
- Use `collections.deque` for `_WorkerSlotManager` (O(1) slot ops).
- `build_ui_event_handler()` must log a `structlog` warning on slot exhaustion.
- `run_setup_wizard()` must accept injectable `console: Console | None = None`.
- Dashboard renders: failures above completions; `…` not `...`.

Test gate: snapshot/render test for failures-above-completions ordering.

---

### Plan 04 — YouTube extractor, metadata, retry

> ⚠️ The YouTube layer is 100% native. **Do not introduce yt-dlp.** See §1.5.

Before writing code, search:

- `httpx` latest async client, timeout, and transport configuration: `https://www.python-httpx.org/`
- Exponential backoff with jitter patterns in Python asyncio
- Current YouTube innertube / transcript API response shapes (inspect live, not yt-dlp docs)
- `asyncio.to_thread` usage for blocking I/O boundaries

Key rules:

- `_pick_language()` must emit a `structlog` warning before falling back.
- Playlist privacy must come from page structure data, not title string matching.
- Construct one extractor client per transcript fetch group; do not recreate inside retry.
- `get_video_metadata()` must re-raise `ExtractionError` for non-availability failures.
- Transport retry: only on 429/500/502/503/504 and transient network errors.
- Do not retry on 401/403/404 or parse failures.
- Delete dead `get_video_chapters()`, `get_video_title()`, `get_video_duration()`.

Test gate: unit test proving public playlist with "private" in its title is not rejected.

---

### Plan 05 — Storage, logging, cache backend

Before writing code, search:

- `sqlalchemy` Core latest `text()` / `Connection.execute()` API
- SQLite `PRAGMA user_version` for schema versioning pattern
- `threading.Lock` with context manager for logging

Key rules:

- Replace one-off migration with a numbered migration runner (`schema_version` table).
- Migration 1 = existing runstats repair; Migration 2 = add `video.cached_at`.
- Migrations must be idempotent and non-destructive.
- `configure_logging()` must be idempotent (guard against reconfiguration).
- `_SESSION_LOG_PATH` writes must be lock-protected.
- `setup_wizard.load_config()` must strip surrounding quotes.
- `sanitize_filename()` must apply reserved-name prefix before truncation.
- Auth-style errors must not be misclassified as filesystem permission failures.
- `tests/conftest.py` teardown must clear both DB singletons and YouTube limiters.

Required new repository methods:

```python
get_recent_videos(limit=10)
get_stats(since_days=None, model=None)
prune_old_entries(older_than_days=30)
```

Test gate: migration runner tested against a pre-existing DB file.

---

### Plan 06 — Runtime performance, CLI surface expansion

Before writing code, search:

- `typer` group / subcommand nesting latest API
- `rich` console singleton pattern in Typer apps
- `asyncio.Semaphore` for bounded concurrent batch resolution
- Platform-appropriate config-file opening (`xdg-open` / `open` / `start`)

Performance targets (must be verified with timing tests):

```
yt-study version      ≤ 300 ms
yt-study --help       ≤ 500 ms
yt-study config-path  ≤ 200 ms
```

Key rules:

- Defer `CliProcessRunner` import to inside `process()` only.
- Cache `Console()` instance; `_get_console()` must not create a new instance each call.
- Batch preflight: resolve inputs concurrently with a bounded semaphore; feed queue as each resolves.
- New commands (`stats`, `history`, `info`, `doctor`, `cache`, `logs`, `edit-config`, `setup --show`) must not import pipeline-runtime modules.
- `setup --show` is read-only.
- `edit-config` behavior must be deterministic and testable (do not shell out in tests).
- ASCII banner ships in `_banner.py`; no side effects at import time.

Test gate: startup smoke test asserting `version` latency ≤ 300 ms.

---

### Plan 07 — Type checking, test coverage, CI hardening

Before writing code, search:

- `ty` latest CLI reference and `pyproject.toml` configuration keys
- `pytest-cov` `--cov-fail-under` flag usage
- `pre-commit` hook config for `ty`

Key rules:

- Add `ty` first without removing `mypy`; fix all diagnostics; then remove `mypy`.
- CI must enforce `--cov-fail-under=93`.
- Add startup smoke gate in CI (`yt-study version` ≤ 300 ms).
- Every module listed in the coverage-gap table must gain direct tests.
- E2E tests remain gated behind `RUN_E2E=1`.
- Do not introduce timing-sensitive assertions in unit tests.

Hotspot modules requiring new/extended tests:

```
cli/_source_resolution.py     cli/_display.py        cli/_formatters.py
config.py                     errors.py              ui/dashboard.py
pipeline/_execution.py        youtube/extractor/_transport.py
storage/repository.py         utils.py
```

Test gate: `ty check src/yt_study` exits 0; CI coverage gate passes.

---

### Plan 08 — Docs, AGENTS files, packaging alignment

Before writing content, search:

- Mintlify `docs.json` latest schema fields
- Mintlify `llms.txt` generation support status
- Current `uv` / `ruff` / `ty` version numbers for contributor docs

Key rules:

- Every public CLI command from Plan 06 must have a reference page.
- README becomes a short landing page pointing to docs; it must not duplicate docs.
- Each `AGENTS.md` must include: purpose, file map, data flow, public API, invariants, gotchas, test locations, frozen contracts.
- Root `AGENTS.md` becomes a navigation index to all child files.
- Update `pyproject.toml` `Documentation` URL once docs site URL is known.
- Remove all `mypy` references from contributor docs; replace with `ty`.
- `CONTRIBUTING.md` must reference `uv`, `ruff`, `ty`, `pytest`, and Mintlify workflows.

Validation checklist:

- [ ] docs nav renders without errors
- [ ] all CLI commands have reference pages
- [ ] no README content duplicates a docs page
- [ ] all AGENTS files stay within intended scope
- [ ] contributor instructions match actual toolchain

---

## 5. Code quality standards

### 5.1 Every change must

- Pass `ruff check` and `ruff format` without errors.
- Pass `ty check src/yt_study` without errors (after Plan 07 lands).
- Have direct test coverage for the changed behavior.
- Not break any previously passing test.

### 5.2 Test discipline

```
tests/unit/          →  pure logic, no I/O, no network
tests/integration/   →  real SQLite, mocked network/LLM
tests/e2e/           →  real network, gated by RUN_E2E=1
```

- All async tests use `@pytest.mark.asyncio`.
- Every new public function gets at least one happy-path and one error-path test.
- Snapshot tests live under `tests/unit/ui/snapshots/`.

### 5.3 Error handling hierarchy

```
User-input errors     →  user-friendly Rich message, exit 1, no traceback
Configuration errors  →  "Run `yt-study setup`" message, exit 1
Network/API errors    →  structured message + structlog warning, exit 1
Unexpected errors     →  structlog exception log, brief user message, exit 1
```

Never let a raw Python exception reach the terminal.

### 5.4 Logging discipline

```python
# Library code — always structlog
import structlog
logger = structlog.get_logger(__name__)
logger.warning("event_name", key=value)

# Never use print() in library code
# Never use logging.getLogger() in library code
```

---

## 6. Search patterns reference

Use these searches at each plan boundary:

```
# Package version lookups
"<pkg> pypi latest version"
fetch: https://pypi.org/pypi/<pkg>/json

# Breaking changes
"<pkg> changelog <year>"
"<pkg> migration guide v<N> to v<N+1>"

# API surface
"<pkg> <class or function> documentation"
fetch: <official docs URL>

# httpx (YouTube transport layer)
fetch: https://www.python-httpx.org/advanced/

# YouTube page/API structure (native extractor — inspect live, not yt-dlp)
search: "YouTube innertube API <endpoint> <year>"

# Mintlify schema
fetch: https://mintlify.com/docs/settings/global

# ty configuration
fetch: https://github.com/astral-sh/ty/blob/main/README.md

# ruff rules
fetch: https://docs.astral.sh/ruff/rules/
```

---

## 7. Definition of done

A plan is complete only when **all** of these are true:

- [ ] All described bugs are fixed.
- [ ] All described tasks are implemented.
- [ ] All new tests pass.
- [ ] No previously passing test is broken.
- [ ] `ruff check` passes with zero errors.
- [ ] `ty check src/yt_study` passes (from Plan 07 onward).
- [ ] Coverage threshold is met or exceeded.
- [ ] All frozen contracts are preserved.
- [ ] No raw exceptions reach the terminal.
- [ ] Live docs were consulted for every third-party API used.

---

## 8. Quick-reference: what never to do

| ❌ Never do this                                          | ✅ Do this instead                               |
| --------------------------------------------------------- | ------------------------------------------------ |
| `import yt_dlp` or `import youtube_dl` anywhere           | Use the native `youtube/extractor/` layer        |
| Add `yt-dlp` to dependencies for any reason               | Fix the native `_transport.py` / `_parsers.py`   |
| Infer YouTube availability/structure from yt-dlp docs     | Inspect live YouTube response payloads           |
| `import CliProcessRunner` at module level in `app.py`     | Defer to inside `process()`                      |
| `on_event=None` in batch no-ui mode                       | Always provide an event handler                  |
| `mkdir()` during source resolution                        | Defer until first write                          |
| `Console()` inside `_get_console()` every call            | Cache the instance                               |
| `if max_tokens:`                                          | `if max_tokens is not None:`                     |
| Wrap `LLMGenerationError` in another `LLMGenerationError` | Re-raise unchanged                               |
| Write files without ensuring directory exists             | `path.parent.mkdir(parents=True, exist_ok=True)` |
| Infer playlist privacy from title string                  | Use availability data from page structure        |
| Fabricate fallback metadata on extractor failure          | Re-raise `ExtractionError`                       |
| Use `list.pop(0)` in `_WorkerSlotManager`                 | Use `collections.deque.popleft()`                |
| Module-level `console = Console()` in setup wizard        | Inject `console` as parameter                    |
| `"private" in title.lower()` for playlist check           | Parse actual availability field                  |
| Skip version search and assume a version                  | Always fetch PyPI version JSON                   |
| Rely on training-data memory for third-party APIs         | Always fetch live docs first                     |
