# AGENTS.md — Guide for AI Coding Agents

This file provides structured guidance for AI agents (Claude, Codex, Cursor, Copilot, etc.) working on the **yt-study** codebase. Read it before making changes.

---

## Project Summary

`yt-study` is a Python CLI application that converts YouTube videos and playlists into Markdown study notes using LLM APIs. It is packaged as a `src`-layout Python project, managed with `uv`, and published to PyPI.

- **Entry point:** `yt_study/__main__.py` → `main()` → Typer app in `cli/app.py`
- **Core pipeline:** `pipeline/core.py` → `CorePipeline`
- **Version:** `src/yt_study/__init__.py` (`__version__`)
- **Python:** 3.10+ (no walrus operators in type annotations, `match` is okay)

---

## Repository Layout (Critical Paths)

```
src/yt_study/
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
└── youtube/            ← Transcript & metadata extraction; no LLM calls here
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

---

## Adding a New CLI Command

1. Define the function in `cli/app.py` using the `@app.command()` decorator.
2. Import only `typer` and `_get_console()` at call time; load pipeline/storage modules lazily inside the function body.
3. Add a test in `tests/unit/cli/` mocking all I/O.
4. Document the command in `docs/cli/`.

Example skeleton:

```python
@app.command()
def my_command(
    option: Annotated[str, typer.Option("--option", help="…")] = "default",
) -> None:
    """One-line docstring shown in --help."""
    console = _get_console()
    from yt_study.some_module import some_function  # lazy import
    result = some_function(option)
    console.print(result)
```

---

## Adding a New LLM Provider

yt-study routes providers via [LiteLLM](https://github.com/BerriAI/litellm). To register a new native provider:

1. Add the API key env-var name to `_NATIVE_PROVIDER_API_KEYS` in `config.py`.
2. Add the key field to `AppSettings` with the correct `alias`.
3. Add the key to `_ALLOWED_KEYS` in `config.py`.
4. Sync the key to `os.environ` in `AppSettings.model_post_init`.
5. Add detection logic in `get_api_key_name_for_model`.
6. Add an entry to `PROVIDER_CONFIG` in `ui/setup_wizard.py`.
7. Add the key to `.env.example`.
8. Update `docs/reference/providers.mdx` and `docs/getting-started/configuration.mdx`.

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

---

## Configuration Changes

Adding a new user-configurable key:

1. Add the constant default to `_constants.py`.
2. Add the field to `AppSettings` in `config.py` with an `alias` matching the env-var name.
3. Add the key to `_ALLOWED_KEYS` in `config.py`.
4. Add the key to `.env.example` (commented out with a description).
5. Update `docs/reference/configuration.mdx`.

---

## Testing Conventions

- **Unit tests** — mock all external I/O. Use `pytest-mock`'s `mocker.patch`. Never make real network calls.
- **Async tests** — mark as `async def test_...`. No `@pytest.mark.asyncio` needed (`asyncio_mode = "auto"`).
- **Fixtures** — shared fixtures go in `tests/conftest.py`. Module-level fixtures stay in the test file.
- **Coverage** — CI fails below 90%. Check: `uv run pytest --cov=src/yt_study --cov-fail-under=90`.

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
- Do not create `.env` files in the repository root (the config is at `~/.yt-study/config.env`).
- Do not add `print()` statements to production code — use `structlog.get_logger(__name__)`.
- Do not suppress exceptions silently — log with `logger.warning(…, exc_info=True)` or re-raise.
- Do not write multi-line commit messages — the pre-commit hook rejects them.

---

## Useful Make Targets

| Target | Action |
|--------|--------|
| `make test` | Run full test suite in parallel |
| `make test-unit` | Unit tests with coverage |
| `make test-integration` | Integration tests |
| `make fix` | Auto-fix formatting and lint |
| `make quality` | All quality checks |
| `make ci` | Full CI pipeline locally |
| `make clean` | Remove all build/cache artifacts |
| `make build` | Build wheel and sdist |
