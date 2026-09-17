# Reliability and Caching Architecture

## What this shows

This diagram traces one request through every point where NoteWise can avoid repeated work or fail gracefully instead of hard-failing: the cache-first short circuit, retry-with-backoff on transient network failures, per-chapter partial-failure handling with resume, output-path collision protection, and format-rendering fallback. It's the "what happens when something goes wrong, or when you run this twice" diagram.

## Key design decisions

A request is checked against the local cache before any network or generation cost is paid — a full cache hit skips fetching and generation entirely. Network failures are classified: transient failures (timeouts, temporary errors) retry with backoff, while permanent failures (video unavailable, access blocked) are reported immediately instead of being retried into a long, pointless loop. Chapter-based generation treats partial success as a first-class outcome — if some chapters fail, the ones that succeeded are persisted immediately rather than discarded, so a rerun resumes from where it left off instead of re-paying for completed work. Output paths are reserved before writing, which prevents two videos with colliding output names from silently overwriting each other. Format rendering has its own fallback: if a requested format (PDF, DOCX, HTML) fails to render, the run still succeeds with the Markdown source instead of failing the whole video over a rendering-library edge case.

## Tradeoffs

Classifying failures as transient-vs-permanent requires maintaining that classification as new failure modes are discovered, but a naive "retry everything" policy wastes real time retrying failures that will never succeed, and a naive "retry nothing" policy sacrifices resilience against normal network flakiness. Persisting partial chapter results costs a small amount of extra I/O per chapter instead of one write at the end, in exchange for never losing already-generated (and already-paid-for) work when one chapter fails. Falling back to Markdown on a rendering failure means a user might get a different format than they asked for — a deliberate choice to keep the canonical source safe rather than fail the entire run over one renderer.

## How to talk through this diagram

**Spoken walkthrough:** "Every request checks the cache first, so reruns are free when nothing changed. If a fetch fails transiently — a timeout, a temporary error — it retries with backoff; if it's a permanent failure like an unavailable video, it fails fast instead of retrying forever. On the generation side, chapters are treated independently: if one fails, the others are still persisted, so a rerun resumes instead of starting over. And if a specific output format fails to render, the run still succeeds with Markdown instead of failing the whole video."

**Likely follow-ups:**
- *"How do you distinguish a transient failure from a permanent one?"* — By classifying the failure type at the point it's raised — network-level errors like timeouts and connection resets are treated as transient and retried, while explicit unavailability or access-restriction signals from the source are treated as permanent and surfaced immediately.
- *"What stops two concurrent runs from writing to the same output path?"* — Output paths are reserved in memory before any file is written, so a second video that would resolve to the same target path gets a distinguishing suffix instead of silently colliding with the first.
