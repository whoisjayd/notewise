# yt-study — Consolidated Execution Plan Index

This index reconciles all three backlog files and splits the work into independent, execution-ready plan files.

## Document authority

- `master-prompt.md` is the global implementation contract and guardrail source.
- `plan-index.md` is the navigation and execution sequencing source.
- `plan-reference.md` is the source-verified backlog and bug registry baseline.

When wording differs, resolve in that order.

## Consolidated baseline used

Use **V3 as the canonical bug baseline** because the current codebase confirms the later additions are real, including the LLM/provider issues, transcript export path issues, `cached_at` gap, dead helper functions, and `_WorkerSlotManager` performance issue.

Also carry forward **three tasks that existed in the older consolidated file but were dropped or renumbered in V3**:

- original `TASK-14` — source-resolution and batch preflight performance
- original `TASK-16` — CI, packaging, and contributor-flow alignment
- original `TASK-17` — Mintlify AI-native features

## Verified ambiguity resolutions from the codebase

1. **Bug count drift (18 → 28 → 36)**
   - The codebase matches the later expanded scope. Examples verified directly in source:
     - `src/yt_study/llm/provider.py` has both the `LLMGenerationError` double-wrap and `if max_tokens:` falsy bug.
     - `src/yt_study/pipeline/_execution.py` still runs chapters sequentially and exports transcript before chapter output target exists.
     - `src/yt_study/pipeline/_artifacts.py` writes quiz/transcript files without ensuring directories exist.
     - `src/yt_study/storage/models.py` has no `cached_at` on `VideoRecord`.
     - `src/yt_study/youtube/metadata.py` still silently returns fallback metadata on extractor failure.

2. **Task numbering drift across documents**
   - Older docs use task numbers for docs/branding/cache differently from V3.
   - The plan files below are organized by **execution theme**, not source numbering, so they remain stable even though the source task numbers drift.

3. **CLI feature scope drift**
   - The repo currently exposes only `process`, `setup`, `config-path`, and `version` in `src/yt_study/cli/app.py`.
   - Therefore the expanded V3 command set (`stats`, `history`, `info`, `doctor`, `cache`, `logs`, `edit-config`, `setup --show`) should be treated as the target command surface.

4. **Docs scope drift**
   - The repo currently has no `docs/` tree, no `docs.json`, and no per-subfolder `AGENTS.md` files.
   - The docs plan therefore includes both the older Mintlify scaffold task and the newer AI-native docs additions.

## Execution order

Run the plans in this order:

1. `01-cli-setup-and-headless-correctness.md`
2. `02-pipeline-generation-and-artifact-correctness.md`
3. `03-ui-dashboard-and-wizard-behavior.md`
4. `04-youtube-extractor-and-metadata-hardening.md`
5. `05-storage-logging-and-cache-backend.md`
6. `06-runtime-performance-and-cli-surface.md`
7. `07-quality-gates-type-checking-and-tests.md`
8. `08-docs-agents-and-packaging-alignment.md`

Each file is self-contained within scope, but prerequisites and execution order still apply.

## Dependency notes

- Plans 01 and 02 establish correctness baselines for later feature work.
- Plan 05 must land before Plan 06 command-surface work that depends on repository methods.
- Plan 07 validates all prior plans and should run only after Plans 01 through 06 are green.
- Plan 08 documentation must reflect the stabilized command surface from Plan 06.

## Coverage map

### Source tasks covered by plan

| Source task family                                                | Covered in                      |
| ----------------------------------------------------------------- | ------------------------------- |
| All bug-fix work from V3 `TASK-01`                                | Plans 01–05, split by subsystem |
| `TASK-02` / ty migration                                          | Plan 07                         |
| `TASK-03` / parallel chapters                                     | Plan 02                         |
| `TASK-04` / CLI startup speed                                     | Plan 06                         |
| Old `TASK-05`, V2 `TASK-05`, V3 `TASK-08` / Mintlify docs         | Plan 08                         |
| Old `TASK-06`, V2 `TASK-12`, V3 `TASK-05` / CLI branding & banner | Plan 06                         |
| `TASK-07` / dashboard refactor                                    | Plan 03                         |
| Old `TASK-08`, V2 `TASK-08`, V3 `TASK-10` / targeted tests        | Plan 07                         |
| Old `TASK-09`, V2 `TASK-06`, V3 `TASK-09` / per-subfolder AGENTS  | Plan 08                         |
| Old `TASK-10`, V2 `TASK-09`, V3 `TASK-06e/6f` / cache & logs UX   | Plans 05–06                     |
| Old `TASK-11`, V2 `TASK-10`, V3 `TASK-11` / storage hardening     | Plan 05                         |
| Old `TASK-12`, V2 `TASK-11`, V3 `TASK-12` / extractor retry       | Plan 04                         |
| Old `TASK-13`, V2 `TASK-13`, V3 `TASK-13` / CI & Makefile         | Plan 07                         |
| Old `TASK-14` / source-resolution & batch preflight perf          | Plan 06                         |
| Old `TASK-15`, V2 `TASK-14`, V3 `TASK-14` / benchmark harness     | Plan 06                         |
| Old `TASK-16` / CI-packaging-contributor alignment                | Plan 08                         |
| Old `TASK-17` / Mintlify AI-native features                       | Plan 08                         |

### Bug coverage by plan

| Plan    | Bugs                                                   |
| ------- | ------------------------------------------------------ |
| Plan 01 | BUG-12, 13, 16, 17, 24, 25                             |
| Plan 02 | BUG-02, 03, 04, 11, 19, 29, 30, 32, 33                 |
| Plan 03 | BUG-05, 06, 07, 09, 10, 34                             |
| Plan 04 | BUG-20, 21, 22, 23, 31, 36                             |
| Plan 05 | BUG-08, 14, 15, 18, 26, 27, 35                         |
| Plan 06 | BUG-01, 28                                             |
| Plan 07 | regression coverage and validation for all prior plans |
| Plan 08 | documentation and contributor-surface alignment        |

## Files generated

- `01-cli-setup-and-headless-correctness.md`
- `02-pipeline-generation-and-artifact-correctness.md`
- `03-ui-dashboard-and-wizard-behavior.md`
- `04-youtube-extractor-and-metadata-hardening.md`
- `05-storage-logging-and-cache-backend.md`
- `06-runtime-performance-and-cli-surface.md`
- `07-quality-gates-type-checking-and-tests.md`
- `08-docs-agents-and-packaging-alignment.md`

## References

- Master prompt: `master-prompt.md`
- Source backlog baseline: `plan-reference.md`
- Plan 01 references: Typer commands/options and Rich console docs
- Plan 02 references: LiteLLM completion API, asyncio semaphores, and SQLAlchemy ORM docs
- Plan 03 references: Rich Live and markup escape docs
- Plan 04 references: httpx async/timeouts and asyncio `to_thread` docs
- Plan 05 references: SQLAlchemy migrations/metadata and structlog configuration docs
- Plan 06 references: Typer subcommands and Python importtime profiling docs
- Plan 07 references: `ty` CLI and pytest-cov coverage gate docs
- Plan 08 references: Mintlify docs config/navigation and Python packaging metadata docs
