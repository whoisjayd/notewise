# End-to-End Processing Flow

## What this shows

This is the temporal story behind "what happens when I run `notewise process URL`" — a sequence diagram tracing one request from the user through the orchestrator, the local cache, YouTube, the generator, the model gateway, and finally the filesystem. It exists to answer "in what order do things happen, and what happens when something is slow or fails," which the system architecture diagram (a static component map) can't show.

## Key design decisions

The cache check happens before any network call, so a rerun of an already-processed video costs nothing beyond a local lookup. Transcript fetching is rate-limited and retried with backoff on transient failures, because YouTube access is the least reliable dependency in the whole flow. Generation branches on whether the video has chapters: chaptered videos generate each chapter with bounded concurrency, while chapterless videos fall back to token-bounded chunking — either way, individual sections are generated in parallel and stitched into one document rather than generated strictly one-at-a-time. Output formats are written in parallel once the final document exists, since they're independent renderings of the same Markdown source. The run's cost, token usage, and timing are persisted after the artifacts are written, not before, so a failed run doesn't record statistics for work that never completed.

## Tradeoffs

Checking the cache first means a `--force` reprocess has to explicitly bypass this fast path — correctness here depends on that flag being respected everywhere. Retrying transcript fetches with backoff adds latency to the failure case in exchange for resilience against YouTube's transient errors, which are common enough to matter in practice. Parallelizing chunk/chapter generation trades some resource usage (multiple concurrent model calls) for significantly shorter wall-clock time on long videos.

## How to talk through this diagram

**Spoken walkthrough:** "Once the video is submitted, the orchestrator checks the cache first — if everything requested is already there, it skips straight to the user. Otherwise it fetches metadata and transcript from YouTube with rate limiting and retry, decides whether to generate per-chapter or per-chunk, runs those generations in parallel against the model gateway, stitches the results together, writes every requested format in parallel, and only then persists the run's cost and timing."

**Likely follow-ups:**
- *"What happens if generation fails halfway through a long video with many chapters?"* — Chapters that already succeeded are kept and persisted; only the failed ones need to be retried on a rerun, instead of discarding a partially-completed expensive job. See the reliability and caching diagram for that resume path.
- *"Why write the different output formats in parallel instead of sequentially?"* — They're independent, deterministic renderings of the same finished Markdown document, so there's no data dependency between them — parallelizing them shortens wall-clock time for multi-format requests at negligible extra cost.
