# Plan 04 — YouTube extractor, transcript selection, metadata propagation, and transport retry

## Goal

Harden the YouTube-facing layer so it stops silently falling back to wrong data, stops misclassifying public playlists as private, reuses clients efficiently, and retries only where retry is actually safe.

## Governance references

- Global constraints: `master-prompt.md`
- Source-verified bug baseline: `plan-reference.md`
- Sequencing and dependencies: `plan-index.md`

## Source coverage

- V3 bug scope: `BUG-20`, `BUG-21`, `BUG-22`, `BUG-23`, `BUG-31`, `BUG-36`
- Source task coverage: `TASK-12` / YouTube extractor HTTP retry
- Older backlog carry-forward: missing transcript-track tests and optional limiter follow-on evaluation
- Related coverage-gap rows: `youtube/metadata.py`, `youtube/extractor/_playlist.py`, `youtube/extractor/_parsers.py`, `youtube/extractor/_transport.py`
- `plan-reference.md` anchors: `BUG-20` (line 422), `BUG-21` (line 433), `BUG-22` (line 448), `BUG-23` (line 459), `BUG-31` (line 578), `BUG-36` (line 706)
- `plan-reference.md` task anchor: `TASK-12` (line 1413), with dependency note (line 1416) and commit mapping (line 1541)

## Verified current-state findings from the codebase

- `_pick_language()` in `youtube/extractor/_parsers.py` still silently falls back to the alphabetically first language.
- `_extract_playlist()` in `youtube/extractor/_playlist.py` still sets playlist availability via `"private" in title.lower()`.
- `youtube/transcript.py` still constructs new extractor clients inside retry flow.
- `youtube/metadata.py` still swallows `ExtractionError` and returns fallback metadata.
- `youtube/metadata.py` still contains legacy `get_video_chapters()`, `get_video_title()`, and `get_video_duration()` helpers.
- `youtube/extractor/async_client.py` is the canonical async client boundary for extractor usage, while `youtube/extractor/client.py` may still carry legacy cleanup items.

## Constraints that must not be violated

1. All blocking YouTube I/O must stay inside `asyncio.to_thread`-protected extractor boundaries.
2. Availability and extractor failures must continue to use the project exception hierarchy in `yt_study.errors`.
3. Do not turn parse failures into retriable transport failures.
4. Preserve the public behavior of playlist and video parsing helpers unless the change is explicitly fixing a bug.

## Files to modify

- `src/yt_study/youtube/extractor/_parsers.py`
- `src/yt_study/youtube/extractor/_playlist.py`
- `src/yt_study/youtube/extractor/_transport.py`
- `src/yt_study/youtube/extractor/async_client.py`
- `src/yt_study/youtube/transcript.py`
- `src/yt_study/youtube/metadata.py`
- `src/yt_study/youtube/extractor/client.py`
- `src/yt_study/_constants.py`
- tests under `tests/unit/youtube/` and `tests/integration/pipeline/`

## Implementation steps

### 1. Make wrong-language fallback visible

In `_pick_language()`:

- keep the fallback behavior only if the product still wants a best-effort transcript
- before returning the fallback language, log a structured warning with requested languages, available languages, and the selected fallback

If there is a strong case to make this hard-fail instead, do not do it in this plan. Keep to the confirmed backlog fix: warning before fallback.

### 2. Replace the naive playlist privacy heuristic

In `_playlist.py`:

- stop inferring privacy from the playlist title string
- use real availability data from the page structure, matching the repo’s existing availability-checking approach
- ensure public playlists titled with the word `private` are still processed normally

### 3. Reuse one extractor client across transcript retries

In `transcript.py`:

- construct the async extractor client once per transcript fetch attempt group
- pass it into the inner fetch logic instead of recreating it inside the retry loop
- preserve current cookie-file behavior

### 4. Surface metadata failures instead of fabricating empty metadata

In `youtube/metadata.py`:

- re-raise `ExtractionError` for non-availability failures after the availability check helpers run
- allow the normal pipeline exception path to report the error to the user
- only use fallback title/duration/chapters when that behavior is explicitly justified by the code path, not for extractor failures

### 5. Add transport-layer retry/backoff

In `_transport.py` and `_constants.py`:

- add a bounded retry helper
- retry only on transient network and server failures: timeout, connection reset, remote disconnect, HTTP 429, 500, 502, 503, 504
- do not retry 401, 403, 404, availability failures, or parsing failures
- use exponential backoff with jitter
- make retry counts and backoff base configurable via constants

### 6. Remove dead extractor/metadata code

- delete unused metadata helper functions once all call sites use `get_video_metadata()`
- remove the unused import/suppressor in `youtube/extractor/client.py`
- update tests accordingly

### 7. Optional follow-on evaluation

After fixing the test-side limiter cleanup in Plan 05, briefly evaluate whether `_GLOBAL_YOUTUBE_LIMITERS` also needs a `WeakKeyDictionary` production hardening change. Only implement that if the code inspection shows a real production benefit and no compatibility risk.

## Tests to add or update

### Unit tests

- `_pick_language()` logs a warning when forced to fall back.
- playlist titled `Private vs Public Cloud APIs` is not treated as a private playlist.
- transcript fetch with transient failures reuses one client instance.
- transport succeeds after transient 503 failures and stops retrying on 404.
- metadata extraction propagates `ExtractionError` instead of returning empty fallback metadata.

### Integration tests

- pipeline surfaces extractor metadata failure to the user.
- transcript-unavailable or wrong-language cases still produce deterministic user-facing behavior.

## Exit criteria

- Public playlists are no longer rejected because of their title text.
- Wrong-language fallback becomes visible in logs.
- Metadata extraction failures no longer degrade silently into fake metadata.
- Transport retry exists and only retries safe transient failures.
- Dead metadata helper functions and unused extractor imports are removed.

## References

- httpx async support: https://www.python-httpx.org/async/
- httpx timeouts: https://www.python-httpx.org/advanced/timeouts/
- Python `asyncio.to_thread`: https://docs.python.org/3/library/asyncio-task.html#asyncio.to_thread
- YouTube Data API overview: https://developers.google.com/youtube/v3/getting-started
