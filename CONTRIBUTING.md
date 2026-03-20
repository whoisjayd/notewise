# Contributing to yt-study

Keep changes small, typed, tested, and documented.

## Working Rules

- Preserve the current package boundaries and naming conventions.
- Add or update tests whenever behavior changes.
- Prefer focused PRs with one clear goal.
- Use Conventional Commits.

## Setup

```bash
make sync
make hooks-install
```

## Day-to-Day Checks

- `make hooks-run`
- `make ci`
- `python -m pytest tests/unit tests/integration -q`
- `RUN_E2E=1 python -m pytest tests/e2e -q`
  - Requires `RUN_E2E=1` and a real provider key.

If you touch CLI, pipeline, or YouTube code, run the live public smoke checks
before you commit:

```bash
yt-study process "https://www.youtube.com/watch?v=8uiZC0l4Ajw" --no-ui
yt-study process "https://www.youtube.com/playlist?list=PL7s8EzBd1s8op6WSiYxr3U9E_T1DoIkJG" --no-ui
```

## Commit Style

- `feat: ...`
- `fix: ...`
- `docs: ...`
- `refactor: ...`
- `test: ...`
- `chore: ...`

Examples:

- `refactor(cli): split process runtime flow`
- `fix(youtube): restore async metadata fetch`

## Pull Requests

- Describe what changed and why.
- Mention any user-visible behavior changes.
- Link validation commands if you ran a narrower test slice.
- Prefer a draft PR while a refactor is still in progress.
- Call out whether `tests/e2e` was run with `RUN_E2E=1`.

## What Good Looks Like

- Code compiles cleanly.
- `ruff`, `mypy`, `deptry`, and `bandit` are green.
- Tests pass, including unit, integration, and live public smoke checks.
- The README and inline module docs reflect the new behavior and module layout.
