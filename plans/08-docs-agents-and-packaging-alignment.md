# Plan 08 — Mintlify docs, per-folder AGENTS, contributor alignment, and AI-native documentation

## Goal

Create the full documentation surface for the project, add focused AGENTS files per subfolder, and align packaging/contributor metadata so the public docs, contributor workflow, and repo metadata all say the same thing.

## Governance references

- Global constraints: `master-prompt.md`
- Source-verified bug baseline: `plan-reference.md`
- Sequencing and dependencies: `plan-index.md`

## Source coverage

- Source task coverage: Mintlify docs scaffold, per-subfolder `AGENTS.md`, contributor-flow alignment, AI-native docs features
- Consolidated from:
  - old `TASK-05`, V2 `TASK-05`, V3 `TASK-08` — Mintlify scaffold
  - old `TASK-09`, V2 `TASK-06`, V3 `TASK-09` — per-subfolder `AGENTS.md`
  - old `TASK-16` — packaging / contributor alignment
  - old `TASK-17` — AI-native docs features
- `plan-reference.md` anchors: `TASK-08` (line 1236), `TASK-09` (line 1311), packaging/contributor alignment requirements (line 1441), AI-native docs frontmatter requirement (line 1284)
- `plan-reference.md` implementation map: per-subfolder `AGENTS.md` table (lines 1322-1329), docs commit mapping (lines 1529-1531), and done criteria anchors (lines 1585, 1587)

## Verified current-state findings from the codebase

- The repo currently has no `docs/` directory and no `docs.json`.
- There is currently no `AGENTS.md` anywhere in the repository, including the root.
- `pyproject.toml` still points the `Documentation` URL at the GitHub repo instead of a docs site.
- `README.md` and `CONTRIBUTING.md` are currently absent, so this plan must recreate both from scratch.
- No AI-native docs features or metadata are currently present.
- Start from scratch on all these fronts, but the repo is well-prepared for this work with a clean slate and no legacy docs or AGENTS content to migrate.
- Make sure everything is covered

## Constraints that must not be violated

1. Keep README short once the docs site exists; the docs site is the primary and comprehensive surface. Keep README concise and practical, avoid content duplication, and include badges plus links to docs for installation, usage, and contribution so README acts as a landing page.
2. Keep all AGENTS files scoped to their folder and brief enough to be useful for AI agents.
3. Do not publish documentation that contradicts the actual CLI command surface after Plan 06.
4. Preserve architecture invariants and stable interfaces in every AGENTS file.
5. Verify latest stable versions for documented tooling (`uv`, `ruff`, `ty`, pytest, Mintlify CLI/deps) via live sources before publishing version guidance.

## Files to create or modify

- `docs.json`
- `docs/` tree
- `README.md`
- `CONTRIBUTING.md`
- root `AGENTS.md`
- `src/yt_study/cli/AGENTS.md`
- `src/yt_study/domain/AGENTS.md`
- `src/yt_study/llm/AGENTS.md`
- `src/yt_study/pipeline/AGENTS.md`
- `src/yt_study/storage/AGENTS.md`
- `src/yt_study/ui/AGENTS.md`
- `src/yt_study/youtube/AGENTS.md`
- `tests/AGENTS.md`
- `pyproject.toml` project URLs and any docs metadata

## Scope clarifications and non-goals

- This plan creates a docs foundation and information architecture, not a visual design overhaul for the CLI.
- This plan documents the existing CLI contract; it does not change command names, flags, or behavior.
- This plan does not require introducing a hosted docs URL immediately; if deployment is deferred, use a placeholder URL and mark it as temporary in contributor docs.
- This plan should not add broad new product features; only docs, metadata, and agent guidance updates are in scope.

## Required pre-read and setup

- Ask the implementer to read Mintlify docs before making docs-structure decisions.
- Install the Mintlify skill to get context on Mintlify project structure, components, and documentation best practices:
  - `npx skills add https://mintlify.com/docs`
- Add the Mintlify MCP server for documentation search access.
- Follow the official setup instructions:
  - https://www.mintlify.com/docs/ai/model-context-protocol.md
- For best-practice decisions, require both:
  - MCP-backed documentation lookup (Mintlify MCP and other available MCP doc tools)
  - live internet verification from official sources (vendor docs/changelogs), not memory alone

## Implementation steps

### 1. Create the Mintlify scaffold (baseline IA + docs config)

Create `docs.json` and a first-pass `docs/` tree with this minimum information architecture:

- Getting started
- CLI reference
- Configuration
- Troubleshooting
- Development

Target docs tree (minimum):

- `docs/getting-started/installation.mdx`
- `docs/getting-started/quickstart.mdx`
- `docs/getting-started/first-video-walkthrough.mdx`
- `docs/cli/overview.mdx`
- `docs/cli/process.mdx`
- `docs/cli/setup.mdx`
- `docs/cli/config.mdx`
- `docs/cli/config-path.mdx`
- `docs/cli/version.mdx`
- `docs/cli/stats.mdx`
- `docs/cli/history.mdx`
- `docs/cli/info.mdx`
- `docs/cli/doctor.mdx`
- `docs/cli/edit-config.mdx`
- `docs/cli/cache.mdx`
- `docs/cli/logs.mdx`
- `docs/configuration/overview.mdx`
- `docs/configuration/precedence.mdx`
- `docs/configuration/api-keys.mdx`
- `docs/troubleshooting/common-issues.mdx`
- `docs/development/contributing-workflow.mdx`
- `docs/development/performance-benchmarking.mdx`
- `docs/ai/ai-tooling-guidance.mdx`
- `docs/ai/agents-files-usage.mdx`
- `docs/ai/cli-output-contracts.mdx`

`docs.json` must include:

- site metadata and navigation
- global SEO defaults
- links to repo and issue tracker
- explicit ordering that mirrors the tree above

### 2. Lock command docs to the actual public CLI surface

Document the real command contract from `src/yt_study/cli/app.py` and keep naming exactly aligned:

- top-level: `process`, `setup`, `config`, `config-path`, `version`, `stats`, `history`, `info`, `doctor`, `edit-config`, `cache`, `logs`
- cache group: `cache --info`, `cache --show`, `cache --clear`, `cache --prune`, and subcommands `cache info`, `cache show`, `cache clear`, `cache prune`
- logs group: `logs` (with `--tail`, `--open`) and `logs clean`

Per command page include:

- purpose
- syntax block
- required/optional arguments
- option table with defaults
- examples (happy path + one failure mode)
- exit behavior notes if command can return non-zero

### 3. Make docs primary and README intentionally concise

After docs exist:

- recreate `README.md` as a landing page only
- include concise project summary, badges, quick links
- link to docs sections for install, usage, troubleshooting, and contributing
- avoid long inline duplication already covered in docs

README structure target:

- project pitch (2-4 lines)
- badge row
- quick install snippet
- quick run snippet
- links to docs site sections
- support/security pointers

### 4. Recreate and align contributor docs

Create `CONTRIBUTING.md` from scratch with:

- local setup using `uv`
- lint/format via `ruff`
- type checks via `ty` (no `mypy` references)
- test workflow via `pytest`
- docs local preview and validation commands
- policy statement: docs checks local-only or CI-enforced (choose one and state it clearly)
- release-notes/changelog policy decision note

### 5. Add per-folder AGENTS files with strict scope boundaries

Create:

- `AGENTS.md` (root index)
- `src/yt_study/cli/AGENTS.md`
- `src/yt_study/domain/AGENTS.md`
- `src/yt_study/llm/AGENTS.md`
- `src/yt_study/pipeline/AGENTS.md`
- `src/yt_study/storage/AGENTS.md`
- `src/yt_study/ui/AGENTS.md`
- `src/yt_study/youtube/AGENTS.md`
- `tests/AGENTS.md`

Each AGENTS file must include these headings:

- Purpose and ownership boundary
- File map
- Data flow
- Public API surface
- Architecture invariants
- Gotchas and traps
- Tests location
- Must-not-change rules

Root `AGENTS.md` must be a navigation index linking to all child AGENTS files with one-line scope summaries.

### 6. Align packaging metadata and project URLs

Update `pyproject.toml`:

- set `[project.urls].Documentation` to the docs site URL (or a clearly marked temporary URL)
- verify related URLs remain consistent with README and docs
- ensure no stale references to pre-docs workflow wording

### 7. Add AI-native docs metadata and guidance

For every docs page:

- add `description` frontmatter
- keep headings predictable and searchable
- use concise, tool-friendly examples

Add dedicated AI pages covering:

- how AI tools should use `yt-study` safely
- expected CLI output patterns and error classes
- how `AGENTS.md` files are intended to guide edits
- recommendation on enabling Mintlify contextual AI/MCP features after launch

### 8. Version-verification step before publishing guidance

Before finalizing version guidance, verify latest stable tool versions from official sources:

- `uv`
- `ruff`
- `ty`
- `pytest`
- Mintlify CLI and required runtime dependencies

Capture the verification date and source links in contributor docs or a docs maintenance note.

## Validation

Functional validation:

- docs navigation renders locally without broken links
- every public CLI command listed above has a reference page
- README points into docs and avoids deep duplication
- all AGENTS files are scoped to their folders and do not leak ownership boundaries
- contributor docs match the actual toolchain (`uv`, `ruff`, `ty`, `pytest`, Mintlify)

Suggested validation commands:

- `uv run yt-study --help`
- `uv run yt-study process --help`
- `uv run yt-study cache --help`
- `uv run yt-study logs --help`
- `uv run ruff check .`
- `uv run ty check`
- `uv run pytest -q`
- docs preview/validation command selected for Mintlify workflow and documented in `CONTRIBUTING.md`

Content validation checklist:

- all docs pages include meaningful `description` frontmatter
- no `mypy` wording remains in docs, README, or contributor docs unless historically intentional and explicitly labeled
- CLI examples use command names exactly as implemented
- troubleshooting pages include API keys, transcript unavailability, private/unavailable sources, and rate-limit guidance

## Risks and mitigations

- Risk: docs drift from CLI behavior
- Mitigation: derive command pages directly from `--help` and verify before merge

- Risk: AGENTS files become too broad and contradictory
- Mitigation: enforce per-folder ownership boundaries and short invariants

- Risk: version guidance becomes stale quickly
- Mitigation: include verification date and official source links

- Risk: README regrows into duplicate docs
- Mitigation: keep strict landing-page template and link out

## Execution checklist (in order)

1. Build `docs.json` and minimum docs tree.
2. Document all public CLI commands and options from current app surface.
3. Recreate concise `README.md` linking to docs.
4. Recreate `CONTRIBUTING.md` aligned to `uv`/`ruff`/`ty`/`pytest` and docs workflow.
5. Create root + per-folder `AGENTS.md` files with required sections.
6. Update `pyproject.toml` documentation URL and related metadata.
7. Add AI-native docs pages and frontmatter on all pages.
8. Run validation commands and close any mismatches.
9. Record final decisions (docs validation policy, changelog policy).

## Exit criteria

- Mintlify docs exist and are the primary documentation surface.
- Every major source subfolder has a focused `AGENTS.md`.
- Root metadata and contributor guidance are aligned with the actual workflow.
- AI-native docs metadata and guidance are present and intentional.
- Command documentation fully matches the implemented CLI contract.
- README remains concise and defers depth to docs.

## References

- Mintlify docs settings/global config: https://mintlify.com/docs/settings/global
- Mintlify docs navigation config: https://mintlify.com/docs/settings/navigation
- Python packaging project metadata: https://packaging.python.org/en/latest/specifications/declaring-project-metadata/
- GitHub markdown syntax: https://docs.github.com/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github
