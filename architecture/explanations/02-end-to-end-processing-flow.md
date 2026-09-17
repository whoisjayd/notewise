# End-to-End Processing Flow

## What this shows

A sequence diagram tracing the causal path of a single `notewise process <URL>` invocation, from the user's command through cache lookup, metadata and transcript retrieval, generation (including internal chunking and provider calls), artifact rendering, and final persistence. It captures the temporal ordering of a request — what must happen before what — rather than the static structure of the system.

## Key design decisions

The cache check happens before any network or AI work is done, and it checks not just "have we seen this video" but "does every artifact the user is asking for this time already exist" — so a rerun that adds a new output format or a quiz still does the right amount of work instead of either redoing everything or wrongly skipping. Metadata and transcript retrieval are sequenced before generation begins, since chapter markers (discovered in metadata) determine which generation path the transcript takes. Generation is shown as a loop over chunks or chapters precisely because it isn't always a single call — the diagram intentionally shows that internal iteration rather than collapsing it into one opaque step, since it's central to how the system handles arbitrarily long transcripts. Rendering and persistence happen only after generation fully completes, and persistence captures not just the output but token usage, cost, and timing — so cache and history data stay accurate even though they're written after the artifact.

## Tradeoffs

Fetching transcript and metadata strictly before generation begins means the two cannot overlap, which is simpler and safer (chapter-aware generation depends on chapters being known up front) but costs some wall-clock time compared to a more speculative pipeline. Persisting to the cache only after a video fully succeeds means a run that fails partway through can't count on file-level caching alone — this is why chapter-level resume state exists as a separate mechanism (see the reliability and caching view). Checking cache completeness per-artifact rather than per-video adds a small amount of lookup complexity in exchange for correctness when a user's requested outputs change between runs.
