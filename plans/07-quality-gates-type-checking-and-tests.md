# Plan 07 — Type-checking migration, targeted test expansion, and CI/Makefile hardening

## Goal

Replace `mypy` with `ty`, close the explicitly identified coverage gaps, and harden CI so the new behavior cannot regress silently.

## Governance references

- Global constraints: `master-prompt.md`
- Source-verified bug baseline: `plan-reference.md`
- Sequencing and dependencies: `plan-index.md`

## Source coverage

- Source task coverage: `TASK-02`, `TASK-10`, `TASK-13`
- Related carry-forward: coverage threshold enforcement and startup smoke gate
- This plan validates all prior plans rather than introducing user-facing behavior by itself
- `plan-reference.md` anchors: `TASK-02` (line 759), `TASK-10` (line 1337), `TASK-13` (line 1434)
- `plan-reference.md` CI details: `--cov-fail-under=93` (line 1439), `RUN_E2E=1` smoke extension note (line 1385), and commit mapping (lines 1511-1513, 1535, 1542)

## Verified current-state findings from the codebase

- `pyproject.toml` still contains `[tool.mypy]` and no `[tool.ty]` section.
- `.pre-commit-config.yaml`, CI, and Makefile still reflect the old type-checking surface.
- Coverage gaps named in the backlogs still align to the current repo layout, especially around CLI routing, display bridging, config precedence, dashboard edge cases, and extractor transport behavior.

## Constraints that must not be violated

1. Do not lower the documented coverage quality bar.
2. Keep CI deterministic; avoid flaky timing-sensitive assertions unless they are deliberately marked or smoothed.
3. Preserve test patch points in `cli/app.py` and current pytest structure.
4. Use `uv` for dependency management and command execution (`uv add`, `uv run`), not `pip install`.
5. Verify latest stable releases via PyPI JSON before dependency/version updates, and use `>=X.Y, <X+1` bounds.

## Files to modify

- `pyproject.toml`
- `.pre-commit-config.yaml`
- `Makefile`
- `.github/workflows/ci-main.yml`
- test files across `tests/unit/`, `tests/integration/`, `tests/e2e/`
- `CONTRIBUTING.md` references that still mention mypy

## Implementation steps

### 1. Introduce `ty` alongside `mypy`

Add `ty` first without removing `mypy`.

Required steps:

- add the dependency in dev tooling
- add `[tool.ty]` configuration targeting `src/yt_study`
- run `ty check src/yt_study`
- fix or explicitly suppress legitimate diagnostics surfaced by `ty`

Likely hotspots from the backlog:

- `AppSettings()` call shapes in `config.py`
- `Any` patch-point fields in CLI context objects
- Rich render typing around dashboard/group construction

### 2. Switch CI and pre-commit to `ty`

Once `ty` passes reliably:

- replace mypy in CI
- replace mypy in pre-commit
- update Makefile type-check targets
- update cache-clean targets from `.mypy_cache` to `.ty_cache`

### 3. Remove mypy fully

After the new `ty` path is green:

- remove mypy dependencies
- delete `[tool.mypy]`
- remove stale mypy references from docs and contributor files

### 4. Add the targeted missing tests named in the backlog

Add or extend tests for the following modules and behaviors:

- `cli/_source_resolution.py`
- `cli/_display.py`
- `cli/_formatters.py`
- `config.py`
- `errors.py`
- `ui/dashboard.py`
- `pipeline/_execution.py`
- `youtube/extractor/_transport.py`
- `storage/repository.py`
- `utils.py`

Minimum expected scenarios:

- invalid URL / missing IDs / playlist failure propagation
- headless event formatting and slot exhaustion logging
- zero-metrics cost summary suppression
- settings precedence and env/config parsing
- auth-vs-filesystem error formatting
- dashboard edge rendering
- concurrent chapter limit enforcement
- transport retry success and non-retriable failure behavior
- singleton teardown isolation
- filename sanitation at reserved-name boundary

### 5. Extend integration and e2e smoke coverage

Integration:

- env-only config path
- non-interactive `process` setup failure message
- batch `--no-ui` output
- new command surface sanity checks

E2E:

- batch file with two public videos
- `--quiz` artifact creation
- transcript JSON export

Keep `RUN_E2E=1` gating where already used.

### 6. Harden CI policy

Required CI additions:

- `--cov-fail-under=93`
- startup smoke gate for `yt-study version`
- `ty` check step
- ensure docs validation hooks are added later when the docs plan lands

## Exit criteria

- `ty` fully replaces `mypy`.
- Coverage targets are enforced in CI.
- The backlog’s named high-risk branches all have direct tests.
- Startup smoke and key CLI regressions are gated automatically.

## References

- ty docs: https://docs.astral.sh/ty/
- pytest-cov reporting and fail-under: https://pytest-cov.readthedocs.io/en/latest/config.html
- pre-commit configuration: https://pre-commit.com/#configuration
- GitHub Actions workflow syntax: https://docs.github.com/actions/using-workflows/workflow-syntax-for-github-actions
