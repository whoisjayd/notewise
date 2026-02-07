# Contributing to yt-study

Thank you for contributing to `yt-study`.

This project values correctness, maintainability, and reproducible workflows.
Please use this guide to keep contributions fast to review and safe to merge.

## Table of Contents

- [Development Setup](#development-setup)
- [Branch and Commit Workflow](#branch-and-commit-workflow)
- [Local Development Commands](#local-development-commands)
- [Pre-commit Hooks](#pre-commit-hooks)
- [Code Quality Standards](#code-quality-standards)
- [Testing Expectations](#testing-expectations)
- [Documentation Expectations](#documentation-expectations)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Issue Reporting](#issue-reporting)
- [Project Map](#project-map)

## Development Setup

1. Fork and clone the repository.

```bash
git clone https://github.com/whoisjayd/yt-study.git
cd yt-study
```

2. Install dependencies and local package.

```bash
make dev-setup
```

3. Verify local environment.

```bash
make info
```

4. (Optional) Run setup wizard for local manual testing.

```bash
yt-study setup
```

## Branch and Commit Workflow

- Create feature/fix branches from `main`.
- Keep PRs scoped to one concern.
- Prefer clear Conventional Commit style messages:
  - `feat: ...`
  - `fix: ...`
  - `docs: ...`
  - `chore: ...`
- Commit messages are enforced as single-line by `commit-msg` hook.

Examples:

- `fix: handle transcript fallback when manual captions are unavailable`
- `docs: expand README troubleshooting and FAQ`

## Local Development Commands

Core workflow:

```bash
make sync      # install locked dependencies
make quick     # fast checks before small push
make ci        # CI-equivalent local checks
make all       # alias for ci
```

Full command list:

```bash
make help
```

## Pre-commit Hooks

Install hooks once per clone:

```bash
make hooks-install
```

Run all hooks manually:

```bash
make hooks-run
```

Run full quality gate + fast tests:

```bash
make pre-commit
```

Run quality checks only (includes dependency + security checks):

```bash
make check
```

Run auto-fix quality checks + dependency/security checks:

```bash
make verify
```

Direct tool commands (if needed):

```bash
uv run ruff format --check src/yt_study tests
uv run ruff check src/yt_study tests
uv run mypy src/yt_study
uv run deptry src
uv run bandit -c pyproject.toml -r src/yt_study --severity-level high
uv run pytest tests -q
```

## Code Quality Standards

- Follow existing architecture and module boundaries.
- Prefer explicit typing and keep MyPy strictness intact.
- Keep functions small and behavior-focused.
- Preserve async safety:
  - Do not add blocking network I/O directly inside async paths.
  - Use `asyncio.to_thread(...)` for blocking library calls.
- Keep CLI behavior stable and user-friendly (`yt-study process`, `setup`, etc.).
- Avoid adding noisy logging in hot paths.

## Testing Expectations

Before opening a PR:

1. Add tests for behavior changes.
2. Update tests for modified behavior or output contracts.
3. Ensure `make ci` passes locally (includes deps/security checks).

Guidelines:

- Put tests under `tests/` mirroring source structure.
- Prefer deterministic tests with clear assertions.
- Include regression tests for bug fixes.

## Documentation Expectations

Update docs when behavior changes:

- `README.md` for user-facing changes.
- `wiki/*.md` for deeper guides and references.
- `CONTRIBUTING.md` when development flow changes.
- `.github/pull_request_template.md` if PR expectations change.

## Submitting a Pull Request

1. Run local checks:

```bash
make ci
```

2. Fill in the PR template completely.
3. Link related issues (`Closes #...` when applicable).
4. Keep PR description practical:
   - what changed
   - why it changed
   - risk/impact
   - test coverage added/updated

## Issue Reporting

Use the issue forms in GitHub for:

- bugs
- features
- docs
- security (public, non-sensitive only)

For sensitive security reports, follow `SECURITY.md` private disclosure process.

When filing bugs, include:

1. Exact command used.
2. Full sanitized error output/traceback.
3. `yt-study version`, Python version, and OS.
4. Relevant non-sensitive config values.

## Project Map

- `src/yt_study/cli.py`: Typer CLI entrypoint.
- `src/yt_study/config.py`: runtime config loading and env mapping.
- `src/yt_study/pipeline/`: orchestration and concurrency flow.
- `src/yt_study/llm/`: provider integration and note generation logic.
- `src/yt_study/youtube/`: parsing, metadata, transcripts, playlists.
- `src/yt_study/ui/`: Rich live dashboard components.
- `tests/`: unit/integration tests.
- `.github/workflows/`: CI, PR gate, release, and labeling automation.
