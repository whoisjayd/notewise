# Plan 02 — Pipeline generation, LLM/provider handling, and artifact correctness

## Goal

Fix pipeline behavior that currently causes unnecessary DB work, wrong artifact output paths, silent metric formatting mistakes, dead generation paths, and avoidable provider errors. Then wire the existing concurrent chapter-generation implementation.

## Governance references

- Global constraints: `master-prompt.md`
- Source-verified bug baseline: `plan-reference.md`
- Sequencing and dependencies: `plan-index.md`

## Source coverage

- V3 bug scope: `BUG-02`, `BUG-03`, `BUG-04`, `BUG-11`, `BUG-19`, `BUG-29`, `BUG-30`, `BUG-32`, `BUG-33`
- Source task coverage: `TASK-03` / parallel chapter generation
- Related coverage-gap rows: `pipeline/_execution.py`, `pipeline/_artifacts.py`, `cli/_formatters.py`, `llm/provider.py`
- `plan-reference.md` anchors: `BUG-02` (line 198), `BUG-03` (line 213), `BUG-04` (line 222), `BUG-11` (line 308), `BUG-19` (line 411), `BUG-29` (line 534), `BUG-30` (line 562), `BUG-32` (line 593), `BUG-33` (line 627)
- `plan-reference.md` task anchor: `TASK-03` (line 798), with dependency note (line 801) and wiring summary (line 1604)

## Verified current-state findings from the codebase

- `src/yt_study/pipeline/_execution.py` still uses a sequential chapter `for` loop.
- `src/yt_study/pipeline/generation.py` already contains `generate_chapter_notes_concurrent()` and still contains dead `generate_chapter_based_notes()`.
- `process_single_video()` still does a redundant `_get_cached_video()` fetch in force mode.
- `pipeline.export_transcript` is still a string attribute that can be confused with the exported helper function.
- `src/yt_study/llm/provider.py` still wraps `LLMGenerationError` inside another `LLMGenerationError` and still uses `if max_tokens:`.
- `src/yt_study/pipeline/_artifacts.py` still writes files without first ensuring the output directory exists.
- `src/yt_study/pipeline/_execution.py` still exports the transcript before the chapter-mode output directory is created.

## Constraints that must not be violated

1. Preserve `CorePipeline.run()` signature.
2. Preserve `PipelineEvent` field names.
3. Preserve existing CLI flags such as `--quiz` and `--export-transcript`.
4. Keep all pipeline progress flowing through `PipelineEvent` and `on_event`.

## Files to modify

- `src/yt_study/pipeline/_execution.py`
- `src/yt_study/pipeline/generation.py`
- `src/yt_study/pipeline/_artifacts.py`
- `src/yt_study/pipeline/core.py`
- `src/yt_study/llm/provider.py`
- `src/yt_study/domain/results.py`
- `src/yt_study/cli/_formatters.py`
- tests under `tests/unit/pipeline/`, `tests/unit/llm/`, `tests/integration/pipeline/`

## Implementation steps

### 1. Fix zero-metrics truthiness at the domain layer

In `domain/results.py`:

- Add `PipelineMetrics.__bool__()` so a zeroed metrics object is falsy.
- Keep `print_cost_summary()` simple; let it rely on the domain object truthiness.

### 2. Remove the redundant force-mode DB lookup

In `pipeline/_execution.py`:

- Fetch cache state once.
- Use the single fetch for skip logic and output-target reservation decisions.
- Do not hit SQLite twice in the same video execution path when `force=True`.

### 3. Rename the conflicting transcript export attribute

In `CorePipeline` and all references:

- Rename the instance attribute `export_transcript` to `export_transcript_format`.
- Keep the user-facing CLI flag unchanged.
- Keep the helper function name `export_transcript()` unchanged.

### 4. Fix provider error handling and `max_tokens`

In `llm/provider.py`:

- Re-raise an incoming `LLMGenerationError` unchanged.
- Only wrap non-domain exceptions.
- Change `if max_tokens:` to `if max_tokens is not None:`.

### 5. Fix artifact directory creation and chapter-mode transcript placement

In `_artifacts.py` and `_execution.py`:

- Ensure the destination directory exists before writing transcript or quiz files.
- In chapter mode, export transcript into the chapter output directory, not the parent output root.
- Make sure `generate_and_write_quiz()` also writes into an existing directory.

### 6. Remove dead generation code

In `generation.py`:

- Remove `generate_chapter_based_notes()` once the concurrent path is wired and covered.
- Delete any tests that only target dead behavior and replace them with tests covering the live concurrent path.

### 7. Wire the existing concurrent chapter implementation

Use `generate_chapter_notes_concurrent()` from `generation.py` in `_execution.py`.

Required behavior:

- Respect `config.max_concurrent_chapters`.
- Emit chapter events using the same event contract already used by the sequential path.
- Write final files in stable chapter order.
- Preserve skip behavior when a chapter output file already exists and `force` is not enabled.

Implementation pattern:

- split transcript into chapter transcripts
- call `generate_chapter_notes_concurrent(...)`
- gather results in memory
- write chapter files in deterministic original order

### 8. Keep cache persistence and metrics aggregation intact

After the above changes:

- `PipelineMetrics` must still aggregate prompt/completion/total tokens, cost, transcript seconds, and generation seconds.
- persistence to storage must still happen once per video run.

## Tests to add or update

### Unit tests

- `PipelineMetrics.__bool__()` truth table.
- `print_cost_summary()` produces no output for all-zero metrics.
- `LLMProvider.generate()` re-raises `LLMGenerationError` without double-wrapping.
- `max_tokens=1` and `max_tokens=0` are forwarded correctly when intended.
- transcript/quiz writers create destination directories before writing.

### Integration tests

- chapter mode exports transcript to the chapter directory.
- chapter mode still writes chapters in stable order.
- `max_concurrent_chapters=2` never exceeds two concurrent generation calls.
- force mode only queries cached video once per processed video.

## Exit criteria

- Chapter generation is concurrent and bounded.
- Transcript and quiz writers never fail because the directory is missing.
- Chapter-mode transcript export lands in the correct folder.
- `LLMGenerationError` is not double-wrapped.
- `max_tokens` is not silently ignored.
- Zero-metrics runs no longer render a bogus cost summary.

## References

- LiteLLM completion API: https://docs.litellm.ai/docs/completion
- Pydantic v2 models: https://docs.pydantic.dev/latest/concepts/models/
- SQLAlchemy ORM quick start: https://docs.sqlalchemy.org/en/20/orm/quickstart.html
- Python `asyncio` synchronization primitives: https://docs.python.org/3/library/asyncio-sync.html
