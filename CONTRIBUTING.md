# Contributing to yt-study

> Contributor workflow for local setup, quality checks, tests, docs, hooks, and PR expectations.

---

## Principles

- Keep behavior grounded in the current codebase.
- Preserve the `core/` vs `ui/` separation.
- Treat docs as product surface, not afterthought.
- Add tests for behavior changes.
- Prefer small, reviewable PRs.

## Quick Start

Clone the repository and initialize the wiki submodule:

```bash
git clone https://github.com/whoisjayd/yt-study.git
cd yt-study
git submodule update --init --recursive
```

Install dependencies:

```bash
make sync
```

Install hooks:

```bash
make hooks-install
```

Show tool versions:

```bash
make info
```

## Daily Workflow

| Command | Use it for |
| --- | --- |
| `make quick` | fast local validation |
| `make ci` | CI-equivalent validation |
| `make verify` | autofix + quality pass |
| `make test-cov` | coverage run |
| `make help` | full target list |

## Branching and Commits

- Branch from `main`.
- Keep each branch focused on one concern.
- Prefer conventional commit style:
  - `feat: ...`
  - `fix: ...`
  - `docs: ...`
  - `refactor: ...`
  - `test: ...`
  - `chore: ...`

Commit-message enforcement:

- `conventional-pre-commit` validates the commit message format
- `scripts/hooks/check-single-line-commit.sh` rejects multiline commit messages

Examples:

- `fix: preserve video id fallback when metadata title fetch fails`
- `docs: polish wiki usage and troubleshooting guides`

---

## Make Targets

### Setup

- `make sync`
- `make install`
- `make install-dev`
- `make dev-setup`

### Quality

- `make format`
- `make format-check`
- `make lint`
- `make lint-check`
- `make type-check`
- `make deps-check`
- `make security`
- `make check`
- `make verify`
- `make audit`

### Testing

- `make test`
- `make test-fast`
- `make test-cov`
- `make test-watch`
- `make test-failed`
- `make test-verbose`

### Hooks

- `make hooks-install`
- `make hooks-run`
- `make pre-commit`

### Build and publish

- `make build`
- `make publish`
- `make publish-test`

### Cleanup

- `make clean`
- `make clean-all`

## Coding Standards

### Architecture

- `src/yt_study/core/` must remain UI-free.
- Do not import Rich or console rendering into `core/`.
- Keep blocking YouTube library calls off the event loop with `asyncio.to_thread(...)`.
- Keep CLI concerns inside `src/yt_study/cli.py`.
- Keep Rich dashboard concerns inside `src/yt_study/ui/dashboard.py`.

### Configuration

- `Config` lives in `src/yt_study/core/config.py`.
- If you add a provider key to `Config.ALLOWED_KEYS`, also update:
  - `Config.get_api_key_name_for_model()`
  - `Config._sync_env_vars()`
- Do not document unsupported config keys as user-configurable.

### Pipeline

- `CorePipeline` communicates progress through `PipelineEvent`.
- UI layers turn events into dashboard and summary output.
- Chapter-based saved output is handled directly in `CorePipeline._process_single_video()`.
- Do not route saved pipeline chapter output through `generate_chapter_based_notes()`.

### Docs

- Update `README.md` for user-facing summary changes.
- Update `wiki/` pages for detailed behavior, usage, or troubleshooting changes.
- Update `CONTRIBUTING.md` when the contributor workflow changes.
- Update `AGENTS.md` when the repo map or engineering rules change.

## Testing Expectations

Run before opening a PR:

```bash
make ci
```

Test map:

| Location | Focus |
| --- | --- |
| `tests/test_cli.py` | Typer command behavior |
| `tests/test_config.py` | config parsing and env overrides |
| `tests/test_setup_wizard.py` | wizard flow |
| `tests/test_llm/` | provider and chunking behavior |
| `tests/test_pipeline/` | orchestration and events |
| `tests/test_youtube/` | parser, playlist, transcript, metadata |
| `tests/test_ui.py` | dashboard rendering/state |

Use deterministic tests. Network and provider interactions should be mocked.

## Pre-commit and Hooks

The repo uses `.pre-commit-config.yaml` with:

- repo hygiene checks
- Ruff format/lint
- Bandit
- conventional commit validation
- local `mypy`
- local `deptry`
- local `pytest-fast` on `pre-push`
- local `single-line-commit` on `commit-msg`

Install once:

```bash
make hooks-install
```

Run manually:

```bash
make hooks-run
```

## Wiki and Documentation Workflow

The `wiki/` directory is a Git submodule:

```text
path = wiki
url = https://github.com/whoisjayd/yt-study.wiki.git
```

That means docs work can create changes in:

- the parent repo, such as `README.md`, `CONTRIBUTING.md`, and `AGENTS.md`
- the wiki submodule content inside `wiki/`

Recommended workflow:

1. update or initialize the submodule
2. edit wiki pages inside `wiki/`
3. verify links from `wiki/Home.md`
4. check Git status both at repo root and inside `wiki/` if preparing commits manually

## CI and Release Overview

Current workflows:

- `.github/workflows/ci-main.yml`
  - format check
  - lint check
  - mypy type check
  - pytest coverage on Python 3.12
  - matrix tests on Ubuntu, Windows, and macOS for Python 3.10 to 3.12
- `.github/workflows/pr-gate.yml`
  - format check
  - lint check
  - type check
  - unit tests
- `.github/workflows/release.yml`
  - reuses `ci-main.yml`
  - builds distributions
  - publishes to PyPI on `v*` tags
  - creates a GitHub release

## Pull Requests

Before opening a PR:

1. run `make ci`
2. add or update tests
3. update affected docs
4. confirm the PR template still fits the change

PR descriptions should clearly state:

- what changed
- why it changed
- risks or migration concerns
- how it was tested

For linked issues:

```text
Closes #123
```

## Issues and Security Reports

Use the issue forms in `.github/ISSUE_TEMPLATE/` for bugs, features, docs, and non-sensitive security topics.

For private vulnerability reports, follow [SECURITY.md](SECURITY.md) and do not open a public issue.
