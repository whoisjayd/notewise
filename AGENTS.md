# AGENTS.md — Guide for AI Coding Agents

This file provides structured guidance for AI agents (Claude, Codex, Cursor, Copilot, etc.) working on the **notewise** codebase. Read it before making changes.

---

## Project Summary

`notewise` is a Python CLI application that converts YouTube videos and playlists into Markdown study notes using LLM APIs. It is packaged as a `src`-layout Python project, managed with `uv`, and published to PyPI.

The repository also includes the public website under `website/` and docs source under `docs/`.

- **Entry point:** `notewise/__main__.py` → `main()` → Typer app in `cli/app.py`
- **Core pipeline:** `pipeline/core.py` → `CorePipeline`
- **Version:** `src/notewise/__init__.py` (`__version__`)
- **Python:** 3.11+ (`match` is okay)

---

## Repository Layout (Critical Paths)

```text
src/notewise/
├── _constants.py       ← ALL numeric/string defaults live here
├── config.py           ← AppSettings (Pydantic-settings), config file parsing
├── errors.py           ← ALL custom exceptions (add new ones here only)
├── logging.py          ← structlog setup; never configure logging elsewhere
├── utils.py            ← sanitize_filename and small utilities
├── cli/app.py          ← Typer commands; lazy imports inside command bodies
├── domain/             ← Pure value objects; no I/O allowed
├── llm/provider.py     ← LLMProvider wrapping LiteLLM; UsageTotals dataclass
├── llm/prompts/        ← Prompt templates as plain Python string constants
├── pipeline/core.py    ← CorePipeline; delegates heavy work to _execution.py
├── pipeline/generation.py ← StudyMaterialGenerator (chunking, LLM calls)
├── storage/repository.py  ← DatabaseRepository singleton (SQLAlchemy + SQLite)
├── ui/dashboard.py     ← Rich Live dashboard; reads PipelineEvent stream
├── ui/oauth_flow.py    ← LiteLLM OAuth/device-flow login helpers
├── ui/setup_wizard.py  ← Interactive provider/config setup wizard
├── ui/litellm_models_snapshot.json ← Bundled text-only LiteLLM setup catalog
└── youtube/            ← Transcript & metadata extraction; no LLM calls here
```

Other important root-level paths:

```text
scripts/extract_litellm_model_snapshot.py ← Refresh bundled setup model catalog
scripts/make_help.py                      ← Render grouped `make help` output from Makefile comments
docs/config/providers.mdx                 ← Provider/user-facing model docs
docs/config/configuration.mdx             ← Config key reference
docs/operate/commands.mdx                 ← CLI command reference
website/src/routes/__root.tsx             ← Website shell, metadata, JSON-LD
website/src/routes/index.tsx              ← Website landing page route
website/src/routes/install.tsx            ← Smart /install route; serves shell/PowerShell bootstraps or InstallPage
website/src/routes/sitemap[.]xml.tsx      ← Website sitemap route
website/src/components/SitemapPage.tsx    ← Browser-friendly sitemap UI and URL inventory
website/src/components/sitemapData.ts     ← Shared sitemap URL inventory for XML and browser UI
website/src/components/                   ← Website page/section components
website/src/ui/                           ← Website reusable UI primitives including Terminal and FineIcon
website/vite.config.ts                    ← TanStack Start, Nitro, Vite plugins
docs/umami.js                             ← Mintlify custom analytics script
```

---

## Inviolable Rules

These rules are enforced by CI and must never be broken:

1. **Never define custom exceptions outside `errors.py`.** Import from there in all other modules.
2. **Never add constants (numbers, strings) directly into module code.** Add them to `_constants.py` and import.
3. **Never import heavy dependencies at module top-level in `cli/app.py`.** Use the lazy-import pattern already established there.
4. **Never configure logging outside `logging.py`.** Call `configure_logging()` from the CLI entry point only.
5. **Never put I/O (network, disk) in `domain/`.** The domain layer must remain pure.
6. **Never hardcode API keys or secrets** — not even in tests.
7. **All new CLI commands** must follow the lazy-import pattern: load heavy dependencies inside the command body using the `_load_*_dependencies()` helper pattern.
8. **Never log raw LLM prompts, provider payloads, OAuth tokens, or credentials.** Redact through `logging.py`; provider failures should use summarized/redacted errors.
9. **Provider/model docs must stay snapshot-valid.** If examples or setup model availability change, update the bundled LiteLLM snapshot, README, `.env.example`, docs, and tests together.
10. **Website work uses Bun.** `website/bun.lock` is the canonical website lockfile; do not introduce npm/pnpm/yarn drift without updating docs and lockfiles together.
11. **Do not run Prettier on Mintlify docs.** Docs MDX in `docs/` is intentionally excluded because Prettier can rewrite fenced blocks inside Mintlify components into parser-breaking forms.

---

## Adding a New CLI Command

1. Define the function in `cli/app.py` using the `@app.command()` decorator.
2. Import only `typer` and `_get_console()` at call time; load pipeline/storage modules lazily inside the function body.
3. Add a test in `tests/unit/cli/` mocking all I/O.
4. Document the command in `docs/operate/commands.mdx` and any relevant workflow page under `docs/use/`.

Example skeleton:

```python
@app.command()
def my_command(
    option: Annotated[str, typer.Option("--option", help="…")] = "default",
) -> None:
    """One-line docstring shown in --help."""
    console = _get_console()
    from notewise.some_module import some_function  # lazy import
    result = some_function(option)
    console.print(result)
```

---

## Adding a New LLM Provider

notewise routes providers via [LiteLLM](https://github.com/BerriAI/litellm). To register or improve provider support:

1. Add provider/API-key routing in `_constants.py`, which is the source of truth:
   - `PROVIDER_API_KEY_ENV_VAR_PROVIDERS` for static API keys
   - `PROVIDER_REQUIRED_ENV_VARS` for extra required env such as account IDs/base URLs
   - `PROVIDER_AUTH_ENV_KEYS` for accepted pass-through auth/config keys
2. If the key should be a first-class `AppSettings` field, add it to `config.py` with the correct `alias` and sync it in `AppSettings.model_post_init`. Many pass-through provider keys are already accepted via `_ALLOWED_KEYS` derived from `_constants.py` and written into `os.environ` by `UserConfigSource`.
3. Add or update UI setup metadata only when relevant: update `PROVIDER_CONFIG` in `_constants.py`, ensure `ui/setup_wizard.py` consumes the shared constants, and keep examples in `ui/litellm_models_snapshot.json` valid.
4. If model catalog behavior changes, regenerate the snapshot with:

   ```bash
   uv run python scripts/extract_litellm_model_snapshot.py
   ```

   The snapshot must contain text-generation models only; filter out image, audio, realtime, embedding, search/research, robotics, computer-use, container, and other non-text model families.

5. Add the relevant config examples to `.env.example`.
6. Update user docs together:
   - `README.md`
   - `docs/config/providers.mdx`
   - `docs/config/configuration.mdx`
   - `docs/config/oauth.mdx` when OAuth behavior changes
   - `docs/operate/commands.mdx` when commands or flags change
   - `docs/use/process.mdx` or related workflow pages when user-facing behavior changes
7. Add/update tests in `tests/unit/config/`, `tests/unit/ui/`, `tests/unit/llm/`, and CLI tests when preflight or setup behavior changes.

### OAuth/device-flow providers

ChatGPT subscription and GitHub Copilot use LiteLLM OAuth/device-flow instead of static API keys.

1. Add provider metadata to `OAUTH_PROVIDER_CONFIGS` in `_constants.py`.
2. Keep `OAUTH_DEVICE_PROVIDER_PREFIXES`, `OAUTH_LOGIN_ALLOWED_PROVIDERS`, and safe login models aligned.
3. Default token storage must stay under `NOTEWISE_HOME` / `~/.notewise/oauth/...` via `configure_oauth_token_storage()` unless the user explicitly sets `CHATGPT_TOKEN_DIR` or `GITHUB_COPILOT_TOKEN_DIR`.
4. OAuth login flows belong in `ui/oauth_flow.py` and should be exposed through `notewise auth login` in `cli/app.py` with lazy imports.
5. Unit tests must mock LiteLLM (`aresponses`/`acompletion`). Do not require live ChatGPT, Copilot, or browser/device login in tests.

---

## Adding a New Pipeline Event

All pipeline events are typed enums in `domain/events.py`:

1. Add a value to `EventType`.
2. Emit the event in the appropriate place in `pipeline/_execution.py` or `pipeline/generation.py` using the `emit()` closure.
3. Handle the event in `ui/dashboard.py` if a UI update is needed.
4. Add tests in `tests/unit/pipeline/` and `tests/unit/ui/`.

---

## Storage / Database Changes

The SQLite schema is managed by a hand-rolled migration runner in `storage/migrations.py`. **Do not use Alembic.**

1. Add the migration SQL as a new entry in `migrations.py`.
2. Update the SQLAlchemy ORM model in `models.py`.
3. Update the Pydantic schema in `schemas.py` if read paths are affected.
4. Add a migration test in `tests/unit/storage/test_migrations.py`.
5. Add an integration test in `tests/integration/storage/`.

---

## Prompt Changes

All prompt templates live in `llm/prompts/`. They are plain Python string constants with `{placeholder}` substitution. Changes to prompts may significantly change output quality — always add or update golden-output style tests when modifying prompts.

The three prompt modules are:

- `study_notes.py` — main study guide generation
- `chapter_notes.py` — per-chapter notes
- `quiz.py` — multiple-choice quiz

Prompt changes should avoid source-referential filler such as “as stated in the transcript” and vague marketing labels. Keep generated Markdown structurally valid, especially fenced code blocks. Add/update tests in `tests/unit/llm/test_prompts.py` for prompt quality guardrails.

---

## Configuration Changes

Adding a new user-configurable key:

1. Add the constant default to `_constants.py`.
2. Add the field to `AppSettings` in `config.py` with an `alias` matching the env-var name.
3. Add the key to `_ALLOWED_KEYS` in `config.py` or to the relevant `_constants.py` key set used to derive `_ALLOWED_KEYS`.
4. Add the key to `.env.example` (commented out with a description).
5. Update `docs/config/configuration.mdx` and any affected workflow or CLI reference pages.

---

## Website Changes

The website is a TanStack/Vite app in `website/`.

1. Preserve package metadata and deploy names branded as notewise (`notewise-website`).
2. Maintain landing sections directly in `website/src/components/`; keep reusable primitives such as `Terminal` and `FineIcon` in `website/src/ui/`.
3. Ensure `/install` split by responsibility: `website/src/routes/install.tsx` owns content negotiation for shell/PowerShell/browser requests, while `website/src/components/InstallPage.tsx` owns the browser UI and copy buttons.
4. Restrict `/sitemap.xml` split by responsibility: `website/src/routes/sitemap[.]xml.tsx` owns XML/browser negotiation, while `website/src/components/SitemapPage.tsx` owns the browser-friendly sitemap UI.
5. Use Bun commands from `website/`: `bun install --frozen-lockfile`, `bun run lint`, `bunx tsc --noEmit`, `bun run build`, and then `bun run preview` for local production preview.
6. Keep SEO metadata honest; do not add synthetic reviews, ratings, or misleading OSS/license claims.
7. Preserve accessibility basics such as landmarks, focus states, skip links, and descriptive link/button labels.
8. The website should inherit the system theme on first load. Only user toggles should persist `nw-theme` in local storage.
9. Avoid committing local website env files, Vercel credentials, tokens, provider keys, or analytics secrets.
10. Docs analytics use Mintlify custom JavaScript in `docs/umami.js`; do not add analytics provider blocks to `docs/docs.json` unless intentionally changing providers.
11. Do not run Prettier on `docs/` files; validate docs config with JSON parsing and JavaScript syntax checks instead.

---

## Testing Conventions

- **Unit tests** — mock all external I/O. Use `pytest-mock`'s `mocker.patch`. Never make real network calls.
- **Async tests** — mark as `async def test_...`. No `@pytest.mark.asyncio` needed (`asyncio_mode = "auto"`).
- **Fixtures** — shared fixtures go in `tests/conftest.py`. Module-level fixtures stay in the test file.
- **Coverage** — CI fails below 90%. Check: `uv run pytest --cov=src/notewise --cov-fail-under=90`.
- **Provider/OAuth tests** — mock LiteLLM calls and token flows; never depend on live credentials, browser login, or real provider quota.

### Review-Fix Discipline

- **Verify every bot review against the current branch before editing.** Treat AI review comments as suggestions to validate, not instructions to apply blindly.
- **Use TDD for behavioral/security review fixes.** Add or update a focused failing regression test first, confirm it fails for the expected reason, then change production code.
- **Keep review fixes scoped to the exact affected lines.** Avoid broad regex replacements across whole files unless the review explicitly asks for a file-wide migration; broad edits can create noisy diffs and mask unrelated history.
- **Do not use denied/destructive git shortcuts to revert mistakes.** Prefer `git restore -- <path>` for safe file restoration; never use `git checkout -- <path>` or reset-style commands in agent sessions.
- **Do not run the full test suite repeatedly while iterating.** Run focused tests for the files/behaviors you changed after each review-fix cluster. Save `uv run pytest` for the final verification gate once the diff is stable, unless a full-suite failure itself is being debugged.
- **Run final verification once before pushing.** For Python changes, include affected tests, `uv run ruff format --check src tests scripts`, `uv run ruff check src tests scripts`, `uv run ty check src/notewise`, and one final `uv run pytest` when feasible.
- **Before pushing, search for the reviewed anti-patterns.** Examples: `@pytest.mark.asyncio`, API-key-shaped test literals, constants left outside `_constants.py`, path joins from untrusted metadata, and repo-wide ignore rules such as `*.db`.

---

## Running CI Locally

```bash
make ci           # full suite: format-check, lint, type-check, tests
make test         # tests only (parallel)
make quality      # lint + format + type-check + security + deps
make fix          # auto-fix formatting and lint issues
```

---

## What NOT to Do

- Do not `pip install` anything — use `uv add` and commit `uv.lock`.
- Do not bypass type annotations — the `ty` type checker runs in CI.
- Do not create `.env` files in the repository root (the config is at `~/.notewise/config.env`).
- Do not add `print()` statements to production code — use `structlog.get_logger(__name__)`.
- Do not suppress exceptions silently — log with `logger.warning(…, exc_info=True)` or re-raise.
- Do not log provider request/response payloads or prompt text from LLM failures; use redacted summaries.
- Do not write multi-line commit messages — the pre-commit hook rejects them.

---

## Useful Make Targets

| Target                  | Action                           |
| ----------------------- | -------------------------------- |
| `make test`             | Run full test suite in parallel  |
| `make test-unit`        | Unit tests with coverage         |
| `make test-integration` | Integration tests                |
| `make fix`              | Auto-fix formatting and lint     |
| `make quality`          | All quality checks               |
| `make ci`               | Full CI pipeline locally         |
| `make clean`            | Remove all build/cache artifacts |
| `make build`            | Build wheel and sdist            |

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:7510c1e2 -->

## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:

   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```

5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**

- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds

<!-- END BEADS INTEGRATION -->
