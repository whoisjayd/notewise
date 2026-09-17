# NoteWise Ideas Backlog

This is a **living backlog of potential features and improvements**, not a changelog and not a commitment. Nothing here is scheduled; it exists so the maintainer can scan for what to build next.

**How to read this document:**

- Ideas are grouped into categories that match the codebase's actual module boundaries (`pipeline/`, `llm/`, `storage/`, `youtube/`, `ui/`, `cli/`, docs/DX).
- Within each category, entries are ordered **highest-impact/lowest-effort first**, so the top of each list is the best place to look for a quick win, and the bottom holds bigger bets.
- Every entry has the same four fields: a title, what it is, the concrete gap it addresses ("Why"), and an `Effort` / `Impact` pair on an S/M/L scale (S = small, roughly a focused day or less; M = a few days; L = a week-plus or cross-cutting).
- Grounded in a read of `README.md`, `AGENTS.md`, `docs/`, and the `src/notewise/` source as of this session (post the interactive-prompting, model-picker, custom-endpoint pricing, and performance-fix work already shipped).

---

## Core Pipeline

### 1. Resumable/checkpointed chapter generation across process restarts
Persist per-chapter completion state so an interrupted `process` run (Ctrl-C, crash, network drop) on a long chaptered video/playlist can resume from the last completed chapter instead of restarting the whole video.
**Why:** `pipeline/_chapter_outputs.py` already writes completed chapter files incrementally and `_execution.py` checks for existing artifacts (`_cached_video_has_requested_artifacts`), but there's no resumption at the chapter-worker level if the process itself dies mid-run on a large multi-hour course video — the user must rerun `process` and rely on file-existence checks alone, which don't cover partially-flushed state.
**Effort: M / Impact: M**

### 2. Configurable output post-processing hooks (e.g. auto-open, auto-copy, webhook)
Let users register a shell command or webhook that fires after notes are generated for a video (path, title, format list as args/env).
**Why:** Today the pipeline only writes to `./output`; there's no way to chain notes into Obsidian vaults, Notion imports, or a personal script without polling the output directory. This is a common "glue" ask for local-first tools.
**Effort: S / Impact: M**

### 3. Cross-video synthesis / merged notes for a playlist
Add an optional pass that produces a single consolidated summary/index note across all videos in a playlist or batch, linking to each per-video note.
**Why:** `youtube/playlist.py` and the batch-file path in `cli/app.py` already process multiple videos, but each video's notes are fully independent — there's no playlist-level table of contents or synthesis, which is exactly what a "course" use case (explicitly called out in the README) most needs.
**Effort: L / Impact: L**

### 4. Selective re-generation of a single chapter or section
Allow `notewise process` to regenerate just one chapter file (by index or title) without redoing the whole video, using the cached transcript.
**Why:** `storage/models.py` caches `TranscriptRecord` per video, so the transcript is already reusable, but there's no CLI surface to target one chapter — a user unhappy with one chapter's notes must force a full re-run or hand-edit the file.
**Effort: M / Impact: M**

---

## Providers & Cost

### 5. Per-run cost/token summary persisted and queryable via `notewise stats`
Extend `RunStatsRecord` reporting to break down cost by provider/model over a date range (`stats --since`, `stats --by-model`), not just the current aggregate view.
**Why:** `storage/models.py` already has a `RunStatsRecord` table and `llm/provider.py` has `UsageTotals` with real cost tracking (including the new per-token custom-endpoint pricing), but `notewise stats` currently only shows totals — there's no time-windowed or per-provider breakdown to help users compare providers/models on cost.
**Effort: S / Impact: M**

### 6. Budget/cost-cap guardrail for a run
Add an optional `--max-cost` (or config default) that aborts or warns before a `process` run when the estimated cost (using the existing pricing-lookup and token-count machinery) would exceed a threshold.
**Why:** Cost estimation already exists (`_extract_cost`, `_custom_endpoint_saved_cost`, LiteLLM-native fallback) but is purely observational after the fact — nothing stops a large playlist/course batch from running up an unexpectedly large bill on an expensive model.
**Effort: M / Impact: L**

### 7. Provider health/fallback chain
Let a user configure an ordered list of fallback models (e.g. `gemini/gemini-2.5-flash,openai/gpt-4o-mini`) so a rate-limited or erroring provider automatically falls through to the next one for the current chunk/video.
**Why:** `errors.py` already distinguishes daily-quota vs rate-limit errors with clean messaging (a recent improvement), but the pipeline still just fails the video — there's no automatic retry-on-different-provider path, which would meaningfully increase reliability for long unattended batch runs.
**Effort: L / Impact: L**

### 8. `notewise inference test <name>` for saved custom endpoints
Add a lightweight command that re-runs endpoint discovery/verification against an already-saved profile without requiring `update`, to confirm it's still reachable and priced correctly.
**Why:** `inference add`/`update` already discover and verify live, but a saved profile can silently go stale (endpoint moved, key rotated, pricing changed) with no way to re-check it short of re-running `update` with new values.
**Effort: S / Impact: S**

---

## CLI & Interactivity

### 9. `notewise process --dry-run` cost/time estimate
Before generating, print estimated token count, estimated cost (reusing the pricing/cost-estimation code from `llm/provider.py`), and estimated chunk count for the target video(s), then exit without calling the LLM.
**Why:** `notewise info URL` already inspects metadata/cache status without generation, but there's no pre-flight estimate of what a *paid* run will actually cost/take, which is the more decision-relevant question before committing to a long playlist.
**Effort: S / Impact: M**

### 10. Shell completion generation
Wire up Typer's built-in `--install-completion`/`--show-completion` (or document it) for bash/zsh/PowerShell/fish.
**Why:** The CLI has a fairly large, categorized command surface (process, config, inference, cache, logs, auth, stats, history) documented in `docs/operate/commands.mdx`, but there's no mention of shell completion anywhere in the docs or README — a one-line Typer feature that's currently unused.
**Effort: S / Impact: S**

### 11. Config profiles (multiple named configs, e.g. "work"/"personal")
Support `notewise --profile work process ...` or `NOTEWISE_PROFILE` to point at an alternate `config.db`, so users can keep separate provider/model/output setups.
**Why:** `config.py`/`storage/config_store.py` currently resolve a single `config.db` path; anyone juggling a personal API key and a work API key (or different default output directories) has to manually swap env vars or edit config each time.
**Effort: M / Impact: M**

### 12. Non-interactive `--yes`/`--force` consistency audit across all prompted commands
Now that `inference add/update/delete`, `config get/set/unset`, `cache show`, and `process`/`transcript` URL all gained interactive prompting this session, do a pass ensuring every one of them has a scriptable non-interactive escape hatch (flag-only path) that CI/automation can rely on without a TTY.
**Why:** Interactive prompting is great for humans but risks silently blocking in non-TTY contexts (CI, cron, Docker) if any command lacks a full flag-only path; this is exactly the kind of regression that's easy to introduce while adding prompts.
**Effort: S / Impact: M**

---

## Reliability & Caching

### 13. Cache export/import for team sharing or migration
Add `notewise cache export`/`cache import` to snapshot `cache.db` (or a filtered subset by video ID/date) to a portable file, for moving to a new machine or sharing a pre-warmed transcript cache with a teammate.
**Why:** Caching is entirely local SQLite with no backup/sync story; `cache prune`/`cache clear`/`cache show` manage it in place, but there's no way to move cached transcripts/notes between machines short of copying the raw `.db` file (undocumented and version-fragile).
**Effort: M / Impact: S**

### 14. Automatic stale-cache invalidation on video re-upload/edit detection
When metadata (title, duration, chapter list) fetched fresh from YouTube disagrees with the cached `VideoRecord`, prompt or auto-flag the cache entry as stale instead of silently reusing old notes.
**Why:** `_cached_video_has_requested_artifacts` currently keys off local file/DB presence, not upstream content drift — if a creator edits/re-uploads a video (rare but real, especially for corrected lecture content), NoteWise would happily serve now-inaccurate cached notes.
**Effort: M / Impact: S**

### 15. Structured retry/backoff policy visible in `doctor`
Surface the current retry configuration (max attempts, backoff base, which errors are retried) as part of `notewise doctor`'s diagnostic output, and make it independently tunable via config rather than only `_constants.py`.
**Why:** Retry logic already exists across `llm/provider.py`, `youtube/extractor/_transport.py`, `youtube/playlist.py`, and `youtube/transcript.py`, but it's invisible to the end user — `doctor` checks config/provider/output/cache/logs but says nothing about resilience posture, making it hard to diagnose "is this hanging or retrying" during a stuck run.
**Effort: S / Impact: S**

---

## Output & Formats

### 16. EPUB export for playlist/course notes
Add `epub` as a sibling to the existing `md`/`html`/`pdf`/`docx` writers in `pipeline/_documents.py`, bundling a playlist's chapter notes into a single e-reader-friendly book.
**Why:** The multi-format renderer architecture (`NOTES_OUTPUT_EXTENSIONS`-style dispatch table with per-format writer functions) is already pluggable and chapter bundling exists (`build_chapter_bundle`), so EPUB is a natural, contained addition that directly serves the "long course → organized reference material" use case called out in the README.
**Effort: M / Impact: M**

### 17. Anki-compatible flashcard export alongside quiz
Extend the existing `--quiz` generation path to optionally emit an Anki-importable `.apkg`/CSV deck instead of (or alongside) the current quiz document.
**Why:** Quiz generation already exists end-to-end (`llm/prompts/quiz.py`, shared per-chunk generation loop per the recent refactor), but its output is a static document, not a spaced-repetition-ready format — flashcards are one of the highest-value study outputs for the "students" persona in the README.
**Effort: M / Impact: L**

### 18. Custom Markdown/HTML templates for note rendering
Let power users supply a Jinja-style template (or a config-selectable style) that controls heading structure/styling in rendered notes, rather than the single built-in layout in `_documents.py`.
**Why:** All four writers currently hardcode one document structure; users who pipe notes into their own static-site or wiki system (Obsidian, Notion, personal blog) have no way to match their existing conventions without post-processing the output by hand.
**Effort: L / Impact: S**

---

## Observability

### 19. `notewise logs tail` for live session-log following
Add a `--follow`/`tail`-style mode to the `logs` command group so a user can watch the active session's structured log in real time from a second terminal, mirroring `tail -f`.
**Why:** The dashboard now shows the full session log path (a recent addition), which implies users are already expected to go look at the raw log file — but there's no CLI-native way to stream it live; they must reach for `tail -f` themselves outside NoteWise.
**Effort: S / Impact: S**

### 20. Machine-readable run summary (`--json` on `process`)
Add a `--json`/`--no-ui --json` output mode to `process` that prints a single structured summary object (videos processed, artifacts written, tokens, cost, duration, failures) to stdout instead of/alongside the Rich dashboard.
**Why:** `--no-ui` already exists to suppress the live dashboard for non-interactive contexts, but its output is still human-oriented text — there's no stable machine-parsable summary for wrapping NoteWise in scripts, CI notebook-generation jobs, or other tooling.
**Effort: S / Impact: M**

### 21. Failure-reason breakdown in `history`
Extend `notewise history` to show *why* a video failed (from the structured error taxonomy in `errors.py`: quota, rate-limit, validation, extraction, etc.), not just that it failed.
**Why:** `errors.py` already has a rich, specific exception hierarchy and the dashboard/CLI recently improved error message clarity in real time, but that granularity appears to be lost once a run is over — `history` is the natural place to review past failures and currently can't answer "were these mostly quota errors or mostly transcript-unavailable errors?"
**Effort: S / Impact: M**

---

## Developer Experience

### 22. Golden-file snapshot tests for each output format
Add a small fixture-based test suite that renders a fixed sample notes payload through all four `_documents.py` writers (md/html/pdf/docx) and diffs against committed golden files, catching unintended formatting regressions.
**Why:** `_documents.py` has non-trivial markdown-to-HTML/PDF normalization logic (fence handling, href sanitization, font coverage checks) that's easy to regress silently; AGENTS.md mandates tests for new commands but there's no equivalent structural guarantee for the rendering layer itself.
**Effort: M / Impact: M**

### 23. `scripts/extract_litellm_model_snapshot.py` freshness check in CI
Add a CI job that re-runs the snapshot extraction script against the live LiteLLM catalog and fails (or opens a diff-only report) if `ui/litellm_models_snapshot.json` has drifted, rather than relying on someone to remember to refresh it.
**Why:** AGENTS.md rule 9 explicitly says provider/model docs and the bundled snapshot "must stay snapshot-valid" and calls out updating them together, but that's currently a manual discipline rather than an enforced check — exactly the kind of rule that silently rots.
**Effort: S / Impact: M**

### 24. Contributor-facing architecture diagram for the pipeline event flow
Add a diagram (Mermaid in `docs/understand/`) showing how `PipelineEvent`s flow from `pipeline/_execution.py` workers through to `ui/dashboard.py` and structured logging, since this event-driven wiring spans several files.
**Why:** `docs/understand/pipeline-output.mdx` and `docs/understand/storage-events.mdx` exist but the actual producer/consumer relationship between the async pipeline workers, the dashboard's `update_worker`/`start_chapter_worker` API, and log events isn't visually documented anywhere, making onboarding new contributors to this part of the codebase slower than it needs to be.
**Effort: S / Impact: S**

### 25. Interactive pan/zoom presentation site for the architecture diagrams
Build a standalone site (e.g. hosted at `architecture.notewise.click`) that renders the six `architecture/diagrams/*.mmd` files as one navigable Excalidraw-style canvas — a hub-and-spoke layout anchored on the System Architecture diagram, with click-to-focus navigation (animated pan/zoom to each diagram) and a side panel showing that diagram's spoken walkthrough and interviewer Q&A from `architecture/explanations/*.md`.
**Why:** The architecture docs are strong as static files, but a first attempt at this as a live "Prezi-style" build-tonight deliverable was abandoned — not because the technical approach was wrong (research confirmed `@excalidraw/excalidraw` view-mode + `@excalidraw/mermaid-to-excalidraw` + `scrollToContent({animate:true})` is a viable, natively-animated path, and `@excalidraw/mermaid-to-excalidraw` only fully decomposes flowchart syntax — the one sequence diagram (`02-end-to-end-processing-flow.mmd`) would need redrawing as a flowchart to avoid rasterizing as a flat image), but because it needs proper design/UX iteration rather than a same-night rush build. Worth revisiting deliberately: confirm Excalidraw renders with its authentic hand-drawn roughness/font by default (or set it explicitly), and redraw diagram 02 as a flowchart first so all six diagrams decompose into real, individually stylable nodes.
**Effort: M / Impact: M**
