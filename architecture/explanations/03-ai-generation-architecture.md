# AI Generation Architecture

## What this shows

How raw transcript text becomes finished study notes. The diagram branches on two structural questions: does the video have publisher-provided chapter markers, and does the transcript (or a chapter) fit inside a single generation call? Those two questions determine which of three generation paths a video takes — single-pass, chunked single-document, or chapter-aware — and the diagram also shows quiz generation as a parallel, independently-triggered concern that reuses the same chunking machinery.

## Key design decisions

Chunking exists purely as a workaround for context-window limits, not as a default behavior — the fast path is always "does this fit in one call," and chunking only activates when it doesn't. When chunking is needed, chunks are split on natural boundaries (sentences, then lines, then words as a last resort) with deliberate overlap, and the resulting per-chunk notes are reassembled through a boundary-stitching step rather than naive concatenation — this is what keeps a long video's notes from reading like disconnected fragments. Chapter-aware generation is a distinct path, not a variant of chunking: each chapter is generated concurrently (bounded by a parallelism limit) as its own unit, and only an individual chapter that's still too long falls back to the chunk-and-stitch mechanism internally. Quiz generation is drawn as a parallel concern because it is triggered independently of notes generation but shares the exact same chunk/combine pattern — an architectural choice that avoids maintaining two separate long-text-handling strategies.

## Tradeoffs

Concurrent chapter generation trades higher peak resource/API usage for much faster wall-clock time on chaptered videos, and it requires the reliability layer (see that view) to handle one chapter failing without discarding its siblings — a cost the single-pass and chunked paths don't have to pay. Boundary stitching adds an extra generation call per chunk junction, which costs a small amount of latency and token spend in exchange for a coherent final document instead of visible seams. Reusing the chunk/combine pattern for quizzes keeps the codebase's long-text strategy singular, at the cost of quizzes inheriting whatever chunking tradeoffs notes generation has, even though a quiz's structure is simpler.
