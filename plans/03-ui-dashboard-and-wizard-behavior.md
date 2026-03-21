# Plan 03 — UI, dashboard behavior, worker-slot lifecycle, and setup-wizard interaction

## Goal

Stabilize the Rich dashboard and setup wizard behavior, then ship the visual refactor from the backlog without breaking any public dashboard interfaces.

## Governance references

- Global constraints: `master-prompt.md`
- Source-verified bug baseline: `plan-reference.md`
- Sequencing and dependencies: `plan-index.md`

## Source coverage

- V3 bug scope: `BUG-05`, `BUG-06`, `BUG-07`, `BUG-09`, `BUG-10`, `BUG-34`
- Source task coverage: `TASK-07` / dashboard visual refactor
- Related coverage-gap rows: `ui/dashboard.py`, `ui/setup_wizard.py`, `cli/_display.py`, `cli/_types.py`
- `plan-reference.md` anchors: `BUG-05` (line 238), `BUG-06` (line 253), `BUG-07` (line 264), `BUG-09` (line 286), `BUG-10` (line 297), `BUG-34` (line 650)
- `plan-reference.md` task anchor: `TASK-07` (line 1202), with dependency note (line 1205) and commit mapping (line 1525)

## Verified current-state findings from the codebase

- `PipelineDashboard.update_worker()` still exposes the dead `style` path that can double-wrap Rich markup.
- `HEADLESS_LABELS` still contains dead/unreachable constants according to the backlog.
- `_WorkerSlotManager.acquire()` still uses `list.pop(0)`.
- `build_ui_event_handler()` still drops updates silently when no slot is assigned.
- `setup_wizard.py` still uses a module-level `console = Console()` and `load_config()` still parses raw values without quote stripping.
- `select_model()` still needs an explicit invalid-input branch.

## Constraints that must not be violated

1. Preserve `PipelineDashboard.__init__(total_videos, concurrency, playlist_name, model_name)`.
2. Preserve public dashboard methods: `update_worker`, `add_completion`, `add_failure`, `set_total_videos`, `update_overall_status`, `__rich__`.
3. Keep display logic in the CLI/UI layer only; no dashboard calls from pipeline code.
4. Preserve existing headless markers and event types.

## Files to modify

- `src/yt_study/ui/dashboard.py`
- `src/yt_study/ui/setup_wizard.py`
- `src/yt_study/cli/_display.py`
- `src/yt_study/cli/_types.py`
- tests under `tests/unit/ui/` and `tests/unit/cli/`

## Implementation steps

### 1. Remove the double-markup trap

In `dashboard.py`:

- Remove the `style` parameter from `update_worker()`.
- Require callers to pass fully formatted status strings.
- Update any internal or test call sites accordingly.

### 2. Clean up dead headless-label state

In `cli/_display.py`:

- Remove unreachable `HEADLESS_LABELS` entries that can never be emitted because the handler returns early.
- Keep the early-return behavior itself if that is the intended contract.

### 3. Make slot exhaustion visible

In `build_ui_event_handler()`:

- When `_WorkerSlotManager.acquire()` returns `None`, emit a structured `structlog` warning with the video ID.
- Do not change pipeline semantics; this is an observability fix.
- Avoid noisy duplicate warnings for the same video if possible.

### 4. Make worker-slot allocation O(1)

In `_WorkerSlotManager`:

- Replace the list-based available-slot queue with `collections.deque`.
- Use `popleft()` for acquisition and `append()` for release.
- Keep the public method names unchanged.

### 5. Fix setup wizard invalid-input handling and console injection

In `setup_wizard.py`:

- Add a visible invalid-input branch in `select_model()`.
- Accept a `console: Console | None = None` parameter in `run_setup_wizard()` and thread the chosen console through helper calls.
- Stop depending on the module-level shared console.
- Keep the user flow and output semantics otherwise intact.

### 6. Apply the dashboard visual refactor

Required final dashboard changes:

- render recent failures above recent completions
- use a Unicode ellipsis `…` instead of `...`
- escape worker titles before embedding them in status strings
- keep the public constructor and public methods unchanged

Also preserve:

- active task rows
- progress summary
- model and playlist context
- recent completions and failures sections

### 7. Keep compatibility with tests and CLI patch points

Because existing tests patch CLI globals and render the dashboard through `Live`, avoid introducing constructor or method signature changes outside the explicit `style` removal inside dashboard internals.

## Tests to add or update

### Unit tests

- `update_worker()` does not produce nested markup when given a pre-styled string.
- `_WorkerSlotManager` acquire/release order works with the deque implementation.
- `build_ui_event_handler()` logs a warning when no slot is available.
- `select_model()` prints an invalid-input message on unexpected input.
- `run_setup_wizard(console=mock_console)` works without patching a module-global console.

### Snapshot or render tests

- dashboard render places failures above completions
- long titles use Unicode ellipsis
- worker titles are escaped correctly

## Exit criteria

- No dashboard markup leakage remains.
- Slot exhaustion is visible in logs instead of failing silently.
- Worker slot allocation is O(1).
- Setup wizard invalid input is recoverable and visible.
- The dashboard visual refactor lands without breaking public dashboard interfaces.

## References

- Rich Live display docs: https://rich.readthedocs.io/en/stable/live.html
- Rich markup escaping: https://rich.readthedocs.io/en/stable/markup.html
- Python `queue` docs: https://docs.python.org/3/library/queue.html
- Python `threading` docs: https://docs.python.org/3/library/threading.html
- Python `re` docs: https://docs.python.org/3/library/re.html
