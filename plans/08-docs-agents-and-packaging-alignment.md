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
- The only `AGENTS.md` present is the root file.
- `pyproject.toml` still points the `Documentation` URL at the GitHub repo instead of a docs site.
- README and contributor materials still reflect the pre-Mintlify, pre-ty state.

## Constraints that must not be violated

1. Keep README short once the docs site exists; the docs site becomes the primary surface.
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

## Implementation steps

### 1. Create the Mintlify scaffold

Create `docs.json` and an initial `docs/` tree covering at minimum:

- getting started
- CLI reference
- configuration
- troubleshooting
- development

Required page coverage:

- installation
- quickstart
- first video walkthrough
- all public CLI commands from Plan 06
- configuration precedence and API keys
- troubleshooting for API keys, transcripts, private videos, and rate limits
- development/performance page for benchmark procedure

### 2. Make the docs the primary documentation surface

After the docs tree exists:

- shorten README and make it a landing page that points into the docs site
- update contributor instructions to reference Mintlify workflows and `ty`
- keep README concise, practical, and accurate

### 3. Add per-subfolder AGENTS files

Create one `AGENTS.md` for each major source subfolder and for `tests/`.
Each file must include:

- purpose and ownership boundary
- file map
- data flow
- public API surface
- architecture invariants for that folder
- gotchas / traps / legacy behavior
- where tests live
- what must not change

Also update the root `AGENTS.md` so it becomes a navigation index to all child AGENTS files.

### 4. Align packaging and contributor metadata

Once the docs site URL exists:

- update `pyproject.toml` `Documentation` URL
- update badges and references from `mypy` to `ty`
- add docs validation guidance to `CONTRIBUTING.md`
- decide whether docs validation is local only or CI-enforced and document that choice clearly
- consider whether a `CHANGELOG.md` or release-notes policy should be added; if not added now, leave an explicit note

### 5. Add AI-native docs improvements

For every docs page:

- add useful `description` frontmatter
- ensure Mintlify can generate strong AI-facing metadata such as `llms.txt`

Also add docs content for:

- how AI tools should interact with `yt-study`
- what CLI outputs look like
- how the repository’s `AGENTS.md` files are intended to be used
- whether Mintlify contextual AI/MCP features should be enabled after launch

## Validation

- docs nav renders correctly
- every public CLI command has a reference page
- README points to docs instead of duplicating them
- all AGENTS files stay within their intended scope and line budget
- contributor docs match the actual toolchain (`uv`, `ruff`, `ty`, pytest, Mintlify)

## Exit criteria

- Mintlify docs exist and are the primary documentation surface.
- Every major source subfolder has a focused `AGENTS.md`.
- Root metadata and contributor guidance are aligned with the actual workflow.
- AI-native docs metadata and guidance are present and intentional.

## References

- Mintlify docs settings/global config: https://mintlify.com/docs/settings/global
- Mintlify docs navigation config: https://mintlify.com/docs/settings/navigation
- Python packaging project metadata: https://packaging.python.org/en/latest/specifications/declaring-project-metadata/
- GitHub markdown syntax: https://docs.github.com/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github
