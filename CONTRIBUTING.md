# Contributing to notewise

Thank you for taking the time to contribute! This document covers everything you need to get your environment set up, understand how the project is structured, and submit high-quality contributions.

> [!IMPORTANT]
> Read and follow this guide before opening a pull request.
>
> - **All feature, fix, docs, and maintenance PRs must target `dev`.**
> - **Only maintainer-managed release PRs should target `main`.**
> - PRs that ignore this workflow, skip required validation, or do not follow these contribution rules may be closed without review.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How to Contribute](#how-to-contribute)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Website and Docs](#website-and-docs)
- [Code Quality Standards](#code-quality-standards)
- [Testing](#testing)
- [Commit Messages](#commit-messages)
- [Pull Request Process](#pull-request-process)
- [Reporting Bugs](#reporting-bugs)
- [Requesting Features](#requesting-features)

---

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold it. Please report unacceptable behaviour to [contactjaydeepsolanki@gmail.com](mailto:contactjaydeepsolanki@gmail.com).

---

## How to Contribute

There are many ways to help:

- **Bug reports** — open a [bug report issue](https://github.com/whoisjayd/notewise/issues/new?template=bug_report.yml)
- **Feature requests** — open a [feature request issue](https://github.com/whoisjayd/notewise/issues/new?template=feature_request.yml)
- **Documentation fixes** — typos, unclear explanations, missing examples
- **Code contributions** — bug fixes, new features, performance improvements
- **Tests** — increase coverage, add edge cases

If you plan to work on something large, **open an issue first** so we can discuss the design before you invest time writing code.

---

## Development Setup

### Prerequisites

- Python **3.10** or newer
- [uv](https://github.com/astral-sh/uv) — the project's package manager
- [Bun](https://bun.sh/) **1.3.6** for the website in `website/`

### Clone and Install

```bash
git clone https://github.com/whoisjayd/notewise
cd notewise
uv sync --dev
```

This installs all runtime and development dependencies into an isolated virtual environment.

### Install Git Hooks

```bash
make hooks-install
```

This installs the repository's `pre-commit`, `pre-push`, and `commit-msg` hooks. They run automatically during normal Git operations and enforce formatting, validation, dependency hygiene, fast tests, commit conventions, and the single-line commit-message rule.

### Verify the Setup

```bash
uv run notewise version
```

---

## Project Structure

```
notewise/
├── src/notewise/            # Application source (src layout)
│   ├── __init__.py          # Package version
│   ├── __main__.py          # Entry point (python -m notewise)
│   ├── _constants.py        # Global constants
│   ├── config.py            # Pydantic-settings configuration
│   ├── errors.py            # All custom exceptions
│   ├── logging.py           # structlog configuration
│   ├── utils.py             # General utilities (filename sanitisation, etc.)
│   ├── cli/                 # Typer CLI layer
│   │   ├── app.py           # Command definitions
│   │   ├── _admin.py        # Admin/info command implementations
│   │   ├── _banner.py       # ASCII banner
│   │   ├── _batch_runner.py # Batch processing orchestration
│   │   ├── _context.py      # Shared CLI context
│   │   ├── _display.py      # Rich display helpers
│   │   ├── _formatters.py   # Output formatting
│   │   ├── _runtime.py      # CliProcessRunner
│   │   ├── _single_runner.py# Single-video run orchestration
│   │   ├── _source_resolution.py # URL/batch-file source handling
│   │   └── _types.py        # CLI-layer type aliases
│   ├── domain/              # Domain value objects (no I/O)
│   │   ├── events.py        # PipelineEvent & EventType enum
│   │   ├── results.py       # PipelineResult & PipelineMetrics
│   │   └── youtube.py       # YouTube domain objects (VideoTranscript, etc.)
│   ├── llm/                 # LLM provider abstraction
│   │   ├── provider.py      # LLMProvider & UsageTotals
│   │   └── prompts/         # Prompt templates
│   │       ├── study_notes.py
│   │       ├── chapter_notes.py
│   │       └── quiz.py
│   ├── pipeline/            # Core processing pipeline
│   │   ├── core.py          # CorePipeline class
│   │   ├── generation.py    # StudyMaterialGenerator
│   │   ├── _execution.py    # Single-video & batch execution
│   │   ├── _artifacts.py    # Quiz generation & transcript export
│   │   ├── _helpers.py      # Utility functions for pipeline
│   │   ├── _limiter.py      # YouTube rate limiter
│   │   └── _state.py        # PipelineSharedState
│   ├── storage/             # SQLite persistence layer
│   │   ├── repository.py    # DatabaseRepository (SQLAlchemy)
│   │   ├── models.py        # ORM models
│   │   ├── schemas.py       # Pydantic schemas
│   │   └── migrations.py    # Schema migrations
│   ├── ui/                  # Rich terminal UI
│   │   ├── dashboard.py     # PipelineDashboard (live progress)
│   │   ├── oauth_flow.py    # OAuth/device-flow login helpers
│   │   ├── setup_wizard.py  # Interactive setup wizard
│   │   └── litellm_models_snapshot.json # Bundled text-model catalog
│   └── youtube/             # YouTube extraction
│       ├── parser.py        # URL & ID parsing
│       ├── transcript.py    # Transcript fetching
│       ├── metadata.py      # Video/playlist metadata
│       ├── playlist.py      # Playlist video extraction
│       ├── _availability.py # Availability checks
│       ├── _constants.py    # YouTube-specific constants
│       └── extractor/       # Low-level HTTP extractor client
├── tests/                   # Test suite
│   ├── unit/                # Unit tests (mocked I/O)
│   ├── integration/         # Integration tests (real SQLite, etc.)
│   ├── e2e/                 # End-to-end smoke tests
│   └── conftest.py          # Shared fixtures
├── scripts/
│   ├── extract_litellm_model_snapshot.py # Refresh LiteLLM setup catalog
│   ├── make_help.py       # Render grouped make help output from Makefile comments
│   └── hooks/               # Git hook scripts
├── website/                  # TanStack/Vite marketing site
│   ├── src/routes/           # Site routes, metadata, sitemap
│   ├── src/components/       # Page sections and route-level components
│   ├── src/ui/               # Reusable UI primitives
│   ├── package.json          # Bun scripts and website dependencies
│   └── bun.lock              # Canonical website lockfile
├── docs/                     # Mintlify documentation site source
│   ├── docs.json             # Mintlify navigation, SEO, redirects
│   ├── umami.js              # Custom analytics script loaded by Mintlify
│   └── docs/                 # Documentation pages
├── .github/
│   ├── workflows/           # CI/CD workflows
│   └── ISSUE_TEMPLATE/      # Issue templates
├── Dockerfile               # Two-stage production image
├── Makefile                 # Developer workflow shortcuts
├── pyproject.toml           # Project metadata & tool config
└── uv.lock                  # Locked dependencies
```

### Key Design Principles

- **Src layout** — all importable code lives under `src/notewise/`
- **Domain objects are I/O-free** — nothing in `domain/` touches the network or disk
- **All exceptions in one place** — define custom exceptions only in `errors.py`
- **Lazy imports in CLI** — heavy dependencies are imported inside command functions to keep startup fast
- **Configuration via Pydantic Settings** — `AppSettings` in `config.py`; all defaults are in `_constants.py`
- **Provider docs stay in sync** — model/provider changes must update README, CLI docs, configuration reference, `.env.example`, and provider tests together

## Website and Docs

The website is a separate Bun project in `website/`. Use Bun because `bun.lock` is the canonical lockfile; do not introduce a second package manager without updating the lockfile and contributor docs together.

```bash
cd website
bun install --frozen-lockfile
bun run lint
bunx tsc --noEmit
bun run build
bun run preview
```

Run `bun run build` before `bun run preview`; preview serves the built TanStack output and catches production-only routing issues before Vercel deployment.

Website structure:

- `website/src/routes/` — TanStack routes, shell metadata, content negotiation, sitemap XML, and JSON-LD.
- `website/src/routes/install.tsx` — smart `/install` route that serves shell/PowerShell bootstraps to CLI clients and falls through to the browser route component.
- `website/src/routes/sitemap[.]xml.tsx` — `/sitemap.xml` route that serves XML to crawlers and browser-friendly HTML to people.
- `website/src/components/` — page sections and route-level components such as `Hero`, `Nav`, `FAQ`, `InstallPage`, and `DefaultError`.
- `website/src/components/SitemapPage.tsx` — browser-friendly sitemap table UI and URL inventory shared with the sitemap route.
- `website/src/components/sitemapData.ts` — shared website/docs URL inventory for sitemap XML and the browser-friendly sitemap component.
- `website/src/ui/` — reusable primitives including both `Terminal` and `FineIcon`.
- `website/src/server/` — server functions used by the site.

Keep website changes small and reviewable. Preserve route behavior, metadata, accessibility affordances, system-theme inheritance, and Vercel/Nitro build output unless the change explicitly needs them. Store local website environment values in ignored `website/.env*` files; never commit API keys, OAuth tokens, analytics secrets, or provider credentials.

Docs live in `docs/` and use Mintlify. Add user-facing CLI docs under the matching `docs/` section folder, and update `docs/docs.json` navigation when adding a new page. Mintlify custom JavaScript belongs as `.js` files in the docs content directory; analytics currently use `docs/umami.js`. Do not commit analytics provider secrets in `docs/docs.json`.

Do not run Prettier on `docs/` or docs MDX. Mintlify component children can contain fenced code blocks, and Prettier may rewrite them into parser-breaking forms. For docs-only validation, use JSON parsing for `docs/docs.json` and `node --check docs/umami.js`.

---

## Code Quality Standards

The project enforces a strict quality baseline through Ruff, ty (type checker), Bandit (security), and deptry (dependency hygiene).

### Run All Quality Checks

```bash
make quality       # lint, format-check, type-check, deps-check, security
```

### Auto-fix Formatting and Lint

```bash
make fix           # ruff format + ruff check --fix
```

### Individual Commands

```bash
# Formatting
uv run ruff format src/notewise tests scripts

# Lint
uv run ruff check src/notewise tests scripts

# Type checking
uv run ty check src/notewise

# Security scanning
uv run bandit -c pyproject.toml -r src/notewise

# Dependency hygiene
uv run deptry .
```

### Style Rules

- Line length: **88** characters (Ruff default)
- Target: **Python 3.10** syntax
- Quote style: **double quotes**
- Isort: first-party imports in a separate section
- No unused arguments (ARG rule) — prefix intentionally unused params with `_`

### Provider and OAuth Changes

When changing LiteLLM provider support, OAuth behavior, model examples, or config preflight logic:

- Put new constants, env-var names, provider aliases, and numeric defaults in `src/notewise/_constants.py`.
- Keep OAuth token defaults under `NOTEWISE_HOME`/`~/.notewise` unless the user explicitly sets `CHATGPT_TOKEN_DIR` or `GITHUB_COPILOT_TOKEN_DIR`.
- Do not log raw prompts, provider payloads, API keys, OAuth tokens, or AWS credentials. Add/update redaction tests when touching logging.
- Refresh `src/notewise/ui/litellm_models_snapshot.json` with `uv run python scripts/extract_litellm_model_snapshot.py` when setup model availability changes. The snapshot should include text-generation models only.
- Update docs in the same PR: `README.md`, `.env.example`, `docs/config/providers.mdx`, `docs/config/configuration.mdx`, `docs/config/oauth.mdx`, and `docs/operate/commands.mdx` when the CLI surface changes.

---

## Testing

The test suite is split into three layers:

| Layer       | Path                 | Description                              |
| ----------- | -------------------- | ---------------------------------------- |
| Unit        | `tests/unit/`        | Fully mocked — fast, no network, no disk |
| Integration | `tests/integration/` | Uses real SQLite and filesystem          |
| E2E         | `tests/e2e/`         | Public smoke tests against YouTube       |

### Run Tests

```bash
# Full test suite (parallel)
make test

# Unit tests only with coverage
make test-unit

# Integration tests only
make test-integration

# Single test file
uv run pytest tests/unit/cli/test_display.py -v
```

### Coverage

The CI enforces **90% minimum coverage** on unit tests. Check coverage locally:

```bash
uv run python -m pytest --cov=src/notewise --cov-report=html
open htmlcov/index.html
```

### Writing Tests

- **Unit tests must not make network calls.** Use `pytest-mock` (`mocker.patch`) to patch YouTube extraction and LLM calls.
- **OAuth and provider tests must mock LiteLLM calls.** Do not require live ChatGPT, Copilot, or API-key credentials in unit/integration tests.
- **Fixtures** shared across the test suite live in `tests/conftest.py`.
- **Async tests** use `pytest-asyncio` — mark coroutines with `async def test_...` (the `asyncio_mode = "auto"` setting in `pyproject.toml` handles the rest).
- Test files, classes, and functions must follow the naming convention: `test_*.py`, `Test*`, `test_*`.

---

## Commit Messages

All commit messages must be a **single line** of 72 characters or fewer. This is enforced by the pre-commit hook at `scripts/hooks/check-single-line-commit.sh`.

The recommended format follows [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>
```

Examples:

```
feat(cli): add --export-transcript option to process command
fix(pipeline): handle transcript fetch retry on IPBlockError
docs: update README quick start section
test(storage): add coverage for cache prune edge cases
refactor(llm): extract UsageTotals into provider module
chore: bump litellm to 1.81.1
```

Common types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`, `perf`, `style`.

---

## Pull Request Process

1. **Fork** the repository and create your branch from `dev`:

   ```bash
   git checkout dev
   git pull origin dev
   git checkout -b feat/my-feature
   ```

2. **Write your changes** — code, tests, and documentation together.

3. **Run the full quality suite** locally before pushing:

   ```bash
   make ci
   ```

   For exact hook parity, you can also run:

   ```bash
   make hooks-run
   ```

4. **Push and open a PR** against `dev`. Fill in the PR template completely.

5. **CI must pass** — the `pr-gate.yml` workflow runs format, lint, type-check, version-sync validation, and unit tests for PRs targeting `dev`.

6. **One review approval** is required before merge.

7. **Squash merge** is preferred for a clean history.

8. **Do not open routine contribution PRs against `main`.** Maintainers use `dev -> main` PRs for release promotion.

### Enforcement

- PRs targeting the wrong base branch may be automatically closed.
- PRs that skip tests, ignore the PR template, or do not follow this guide may be closed without review.
- Do not bypass hooks with `--no-verify` unless a maintainer explicitly asks you to do so.

### PR Checklist

- [ ] Tests added or updated for the change
- [ ] `make ci` passes locally
- [ ] Documentation updated if the public interface changed
- [ ] Provider/model examples are snapshot-valid if provider docs changed
- [ ] Commit message follows the single-line convention
- [ ] The PR targets `dev` (unless this is a maintainer-managed release PR)
- [ ] I installed the repository hooks with `make hooks-install`

---

## Reporting Bugs

Use the [bug report template](https://github.com/whoisjayd/notewise/issues/new?template=bug_report.yml). Please include:

- Your OS and Python version (`python --version`)
- The notewise version (`notewise version`)
- The command you ran (redact any API keys)
- The full error output / log file content

The current session log is shown in error messages; you can also find it with `notewise logs --tail 50`.

---

## Requesting Features

Use the [feature request template](https://github.com/whoisjayd/notewise/issues/new?template=feature_request.yml). Describe the problem you're trying to solve, not just the solution.

---

## Security Issues

Please **do not** open a public issue for security vulnerabilities. See [SECURITY.md](SECURITY.md) for the responsible disclosure process.
