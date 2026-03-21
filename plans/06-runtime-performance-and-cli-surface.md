# Plan 06 — Runtime performance, batch preflight responsiveness, banner, and expanded CLI surface

## Goal

Make the CLI fast, responsive, and operationally useful. This plan covers startup speed, batch-preflight responsiveness, the brand/landing experience, the new command surface, and benchmark documentation.

## Governance references

- Global constraints: `master-prompt.md`
- Source-verified bug baseline: `plan-reference.md`
- Sequencing and dependencies: `plan-index.md`

## Source coverage

- V3 bug scope: `BUG-01`, `BUG-28`
- Source task coverage: `TASK-04`, `TASK-05`, `TASK-06`, `TASK-14`
- Older backlog carry-forward: original `TASK-10` cache/log UX, original `TASK-14` source-resolution & batch preflight performance, original `TASK-15` benchmark harness
- Depends on Plan 05 for repository methods used by `stats`, `history`, `cache`, and `logs`
- `plan-reference.md` anchors: `BUG-01` (line 169), `BUG-28` (line 523)
- `plan-reference.md` task anchors: `TASK-04` (line 831), `TASK-05` (line 893), `TASK-06` (line 992), `TASK-10` (line 1337), `TASK-14` (line 1447), with execution mapping (lines 1505-1524, 1535, 1543)

## Verified current-state findings from the codebase

- `src/yt_study/cli/app.py` still imports `CliProcessRunner` at module load time.
- `_get_console()` still creates a fresh `Console()` each time.
- `pyproject.toml` still only contains mypy config and no ty config.
- `cli/_batch_runner.py` still resolves batch jobs serially before workers benefit from the queue.
- There is no docs tree yet to hold benchmark output.
- The command surface still consists only of `process`, `setup`, `config-path`, and `version`.

## Constraints that must not be violated

1. Preserve current public command names and flags while adding new commands.
2. Keep CLI patch points in `app.py` patchable for tests.
3. Do not undo the non-interactive `process` behavior established in Plan 01.
4. Keep fast commands free of pipeline-runtime imports wherever possible.
5. Treat command expansion as additive only: do not rename or remove `process`, `setup`, `config-path`, `version`, or their existing flags.
6. Before touching dependency versions or docs claims, verify latest stable releases using PyPI JSON and keep bounds in `>=X.Y, <X+1` form.

## Files to modify

- `src/yt_study/cli/app.py`
- `src/yt_study/cli/_runtime.py`
- `src/yt_study/cli/_batch_runner.py`
- `src/yt_study/cli/_banner.py` (new)
- any new CLI helper modules for command formatting
- `src/yt_study/storage/repository.py` consumers
- docs/performance page or benchmark doc file
- tests under `tests/integration/cli/` and `tests/e2e/`

## Implementation steps

### 1. Eliminate startup import drag

In `cli/app.py`:

- remove the module-level import of `CliProcessRunner`
- defer that import into `process()` only
- cache the Rich console instance so `_get_console()` is not recreating it every call

Performance target from the backlog:

- `yt-study version` ≤ 300ms
- `yt-study --help` ≤ 500ms
- `yt-study config-path` ≤ 200ms

### 2. Fix config read amplification

In `config.py`:

- cache parsed env/config-file content per settings-source instance
- ensure one parse per settings construction, not one parse per field lookup
- add tests proving only one parse occurs

### 3. Make batch preflight feed workers sooner

In `_batch_runner.py`:

- replace the fully serial enqueue loop with bounded concurrent resolution
- use `asyncio.create_task()` and a small semaphore to resolve multiple inputs concurrently
- feed the queue as each source resolves instead of waiting for all resolution to finish first

Also improve the user-visible preflight experience:

- avoid blocking the worker pool while resolving large batch inputs
- add a concise preflight summary for long runs when feasible
- keep failure labeling clear for mixed direct-video and playlist inputs

### 4. Add the banner and no-args landing experience

Create `_banner.py` and wire it into the no-args path.

Requirements:

- large ASCII banner for `yt-study` with no args
- compact banner for tighter command surfaces if needed
- include short product description and next-step commands
- do not add side effects at import time

### 5. Add the expanded command surface

Implement these commands or subcommands:

- `yt-study stats`
- `yt-study history`
- `yt-study info`
- `yt-study doctor`
- `yt-study cache info|clear|prune`
- `yt-study logs`
- `yt-study edit-config`
- `yt-study setup --show`

Command requirements:

- `stats` uses repository aggregate methods and supports time/model filtering where practical
- `history` shows recent processed videos from cache/history tables
- `info` reports config path, DB path, output dir, selected model, and key runtime settings
- `doctor` performs non-destructive checks: config presence, API key presence, writable state dir, DB health, latest log path
- `cache` exposes info/clear/prune UX
- `logs` shows recent log files and optional tailing of the latest log
- `edit-config` opens or prints the config path in a platform-appropriate and non-destructive way; keep behavior deterministic in tests
- `setup --show` reveals current resolved setup/config without rewriting it

### 6. Keep `process` UX aligned with the earlier plans

Do not reintroduce automatic setup launching.
Do not make fast commands pay pipeline startup cost.
Do not make cache/log/history/info commands require network or LLM initialization.

### 7. Add benchmark harness documentation

Create a repeatable benchmark procedure covering:

- CLI cold start: `yt-study version`
- help latency: `yt-study --help`
- config-path latency
- single-video preflight latency with mocked network
- batch preflight latency for N=10 and N=50 inputs
- optional import-time profiling via `python -X importtime`

Record before/after numbers once the performance work lands.

## Tests to add or update

### Integration tests

- `version`, `config-path`, and `--help` still succeed after import deferral.
- new commands return useful output without forcing pipeline runtime imports.
- batch enqueue uses bounded concurrency and begins producing work before full resolution completes.
- `setup --show` is read-only.

### E2E tests

- batch file with two public videos succeeds
- single video with `--quiz` writes quiz file
- single video with `--export-transcript json` writes transcript JSON

### Performance smoke

- add a startup smoke assertion in CI or documented benchmark gate once stable

## Exit criteria

- Fast commands no longer pay full runtime import cost.
- Batch preflight no longer keeps workers idle unnecessarily.
- Expanded CLI command surface exists and is useful.
- The no-args landing experience is branded and informative.
- Benchmark steps and baseline numbers are documented.

## References

- Typer subcommands and command groups: https://typer.tiangolo.com/tutorial/subcommands/
- Typer command options: https://typer.tiangolo.com/tutorial/options/
- Rich Console API: https://rich.readthedocs.io/en/stable/console.html
- Python import-time profiling: https://docs.python.org/3/using/cmdline.html#cmdoption-X
