# Reliability and Caching Architecture

## What this shows

The layers of failure handling that keep a long-running, multi-network-call pipeline from losing work: caching to avoid redoing completed videos, retry/backoff for transient network and provider failures, partial-failure isolation for chapter-based generation, a resume cache that survives across process runs, and graceful degradation for output rendering. The diagram follows one request through each layer in the order it would actually encounter them.

## Key design decisions

Caching is the first line of defense against wasted work: a request is checked against the local cache before any network or AI call happens at all, and a full skip only happens when every artifact the current invocation asks for is already present — not just "this video was processed before." Network calls to YouTube use bounded retry with exponential backoff and jitter, treating only genuinely transient failures (timeouts, connection resets, specific server error codes) as retryable. The most distinctive decision is partial-failure isolation in chapter generation: chapters run concurrently, and if one fails (a stuck model, a transient provider error) the chapters that already finished are not thrown away — they're written to a resume cache keyed by video, so the next run picks up only the failed chapters instead of regenerating (and re-paying for) everything. Output rendering treats PDF as the one format allowed to fail softly: if PDF rendering breaks on content it can't handle, the pipeline writes Markdown instead of failing the whole video, since Markdown is the one format guaranteed to represent any content.

## Tradeoffs

The resume cache for chapters is deliberately deterministic (keyed by video, not a random temp directory) so it survives an interrupted or crashed run — but that means leftover partial state is a designed persistent artifact, not an implementation accident, and it's only cleaned up once a video is fully completed. Checking full artifact completeness on every cache lookup is more expensive than a single boolean "seen before" flag, but it's what makes the cache trustworthy when a user changes requested formats between runs. Falling back to Markdown on PDF failure silently changes the user's requested output format for that one video — a deliberate choice to preserve the run's other successes rather than fail the whole batch over one renderer's limitation.
