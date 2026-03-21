# Plan 01 — CLI setup, source resolution, and headless execution correctness

## Goal

Fix the CLI behaviors that currently create wrong setup prompts, wrong input classification, silent batch runs, and unnecessary filesystem churn.

## Governance references

- Global constraints: `master-prompt.md`
- Source-verified bug baseline: `plan-reference.md`
- Sequencing and dependencies: `plan-index.md`

## Source coverage

- V3 bug scope: `BUG-12`, `BUG-13`, `BUG-16`, `BUG-17`, `BUG-24`, `BUG-25`
- Older backlog carry-forward: original `TASK-10c` explicit setup direction from `process`
- Related coverage-gap rows: `cli/_batch_runner.py`, `cli/_source_resolution.py`, `cli/app.py`, `cli/_display.py`
- `plan-reference.md` anchors: `BUG-12` (line 319), `BUG-13` (line 335), `BUG-16` (line 372), `BUG-17` (line 389), `BUG-24` (line 470), `BUG-25` (line 486)
- `plan-reference.md` implementation map: commit rows for these fixes (lines 729-730, 739, 745), plus execution-order mapping (lines 1474-1475, 1484, 1490)

## Verified current-state findings from the codebase

- `src/yt_study/cli/app.py` still imports `_runtime` at module import time and still uses file-existence-only setup gating.
- `check_config_exists()` only checks for the config file path.
- `ensure_setup()` still auto-launches the setup wizard.
- `looks_like_batch_file_path()` still has the schemeless-URL false positive path described in the backlog.
- `src/yt_study/cli/_batch_runner.py` still passes `on_event=None` when `dashboard is None`, so batch `--no-ui` is silent.
- `src/yt_study/cli/_source_resolution.py` still creates playlist output directories too early.

## Constraints that must not be violated

1. Preserve the current command names: `process`, `setup`, `config-path`, `version`.
2. Preserve module-level patch points in `src/yt_study/cli/app.py`.
3. Do not change frozen headless markers: `Done:`, `Batch Completed`, `Current log:`.
4. Keep dependency direction `CLI → Pipeline → YouTube / LLM / Storage`.

## Files to modify

- `src/yt_study/cli/app.py`
- `src/yt_study/cli/_batch_runner.py`
- `src/yt_study/cli/_display.py`
- `src/yt_study/cli/_single_runner.py`
- `src/yt_study/cli/_source_resolution.py`
- tests under `tests/integration/cli/` and `tests/unit/cli/`

## Implementation steps

### 1. Fix setup gating so env-only configuration is valid

In `cli/app.py`:

- Stop treating config-file existence as the only signal that setup is complete.
- Use the effective model configuration to decide whether setup is required.
- Check the selected model’s API key name via config, then check both environment variables and config-backed settings before deciding setup is missing.

Target behavior:

- If required API credentials are already available through environment variables, `process` must not launch the wizard.
- If configuration is missing, `process` should fail with a clear message telling the user to run `yt-study setup`.
- Do not auto-launch the setup wizard from `process` anymore. Keep the wizard opt-in through the `setup` command.

### 2. Move input validation ahead of setup prompting

In `process()`:

- Perform lightweight input preflight first.
- Reject invalid URL/file inputs before any setup or provider checks.
- Only after source validation succeeds should the command evaluate whether configuration is missing.

Desired order:

1. parse/validate the user input
2. detect whether it is URL / playlist / batch file
3. fail fast on invalid input
4. evaluate setup requirement
5. run pipeline

### 3. Fix batch-file path misclassification

In `looks_like_batch_file_path()`:

- Remove the bare `"/" in value` and `"\" in value` heuristics.
- Keep only robust path signals such as suffix, absolute path, drive prefix, and leading `.` / `~`.

Acceptance examples:

- `vimeo.com/123456` → not a batch file path
- `./urls.txt` → batch file path
- `path/to/list.txt` → batch file path only if the remaining logic still intentionally treats it as one
- `https://youtube.com/...` → not a batch file path

### 4. Make empty-playlist and empty-source exits explicit

In `_single_runner.py` and any shared source-resolution path:

- Guard before creating a dashboard when `video_ids` is empty.
- Print a clear user-facing message such as `No videos found to process.`
- Return a clean success/failure code according to the current CLI convention, but do not flash a meaningless `0/0` dashboard.

### 5. Restore headless event output for batch `--no-ui`

In `_batch_runner.py`:

- Always pass an event handler to the pipeline, even when `dashboard is None`.
- When `context.no_ui` is true, the handler must call `emit_headless_event(context, event)`.
- Keep the existing UI path unchanged when the dashboard is active.

Do not change the frozen headless markers.

### 6. Defer playlist directory creation until work is confirmed

In `_source_resolution.py` and any writer path:

- Remove eager `mkdir()` calls from source preparation.
- Create directories only at the first actual write boundary.
- Ensure failed playlist resolution no longer leaves empty directories behind.

### 7. Keep final UX consistent

Final `process` behavior when configuration is missing should be:

```text
yt-study: no configuration found.
Run `yt-study setup` to get started.
```

The exact formatting can use Rich, but the behavior must be explicit and non-interactive.

## Tests to add or update

### Unit tests

- `looks_like_batch_file_path()` table tests for schemeless URLs vs true file paths.
- `emit_headless_event()` or batch event-handler bridging tests proving events are emitted under `--no-ui`.
- Source-resolution tests for empty result sets and failure propagation.

### Integration tests

- `process` with valid env-only configuration and no config file does not launch the setup wizard.
- Invalid input fails before any setup prompt.
- Batch file under `--no-ui` emits headless progress lines.
- Failed playlist/source resolution does not create empty output directories.

## Exit criteria

- `process` never auto-launches the setup wizard.
- Env-only config works cleanly.
- Invalid inputs fail before any setup logic.
- Batch `--no-ui` is no longer silent.
- Empty playlists produce a clear message instead of a broken dashboard.
- Failed or cancelled playlist resolution leaves no empty directories.

## References

- Typer commands and options: https://typer.tiangolo.com/tutorial/commands/
- Typer callback and root command flow: https://typer.tiangolo.com/tutorial/commands/context/
- Rich Console API: https://rich.readthedocs.io/en/stable/console.html
- Python `os` module: https://docs.python.org/3/library/os.html
- Python `pathlib` module: https://docs.python.org/3/library/pathlib.html
