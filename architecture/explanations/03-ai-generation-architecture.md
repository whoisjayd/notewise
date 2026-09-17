# AI Generation Architecture

## What this shows

This is the deep-dive diagram for the hardest engineering problem in NoteWise: turning a transcript of arbitrary length into one coherent document without exceeding a model's context window. It traces the decision from "does this video have chapters" and "does the content fit in one call" through chunking, parallel generation, and stitching, down to a single final document — plus quiz generation as a separate concern that reuses the same strategy.

## Key design decisions

Chunking prefers natural boundaries — sentence breaks first, then line breaks, then word breaks, and only a hard character split as a last resort for pathological input — so chunk edges land on points that read naturally rather than mid-word. Adjacent chunks share a bounded overlap, which gives the model shared context across the boundary instead of two independently-generated fragments that don't know about each other. Chunks and chapters are generated in parallel with throttled request starts rather than strictly sequentially, trading a bit of request-pacing complexity for much shorter wall-clock time on long videos. Multi-chunk output isn't just concatenated: a dedicated stitching pass merges using the tail of one section and the head of the next, and normalizes duplicate or chunk-local headings so the result reads as one document, not several pasted together.

## Tradeoffs

Preferring natural boundaries over fixed-size splits means chunk sizes vary, which is the right tradeoff for output quality but makes token-budget accounting slightly less predictable. The overlap between chunks costs some redundant generation (the same span of transcript gets processed twice, once at the tail of one chunk and once at the head of the next) in exchange for narrative continuity across the seam. Running generation in parallel instead of sequentially means a single stuck or slow call doesn't block everything else, but it does mean the system needs the chapter-resume behavior shown in the reliability diagram to handle partial failure cleanly.

## How to talk through this diagram

**Spoken walkthrough:** "The interesting problem here wasn't calling an LLM — it was making generation reliable for a two-hour video that blows past any model's context window. If a video has chapters, each one generates concurrently and independently; otherwise the transcript is split into overlapping chunks along sentence and word boundaries. Every chunk generates in parallel against the model gateway, and a dedicated stitching pass — not simple concatenation — merges the results using shared context at each boundary."

**Likely follow-ups:**
- *"Why overlap chunks instead of just splitting them cleanly?"* — A clean split loses context right at the seam — the model generating the second chunk has no idea what the first chunk just said. The overlap gives both chunks a shared window of text, so the stitching pass has real context to merge on instead of two disconnected fragments.
- *"How do you keep costs bounded with this much parallelism?"* — Request starts are throttled rather than fired all at once, and every generation call goes through the same cost-accounting path (see the multi-provider diagram) regardless of how many run concurrently, so parallelism affects latency, not cost-visibility.
