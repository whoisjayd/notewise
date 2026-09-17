# System Architecture

## What this shows

This is the top-level map of NoteWise: a local application that turns a YouTube video, playlist, or batch of URLs into study materials. A user's input flows through one orchestrator, which is the only component that talks to both the YouTube side (fetching) and the AI side (generating). Everything the system needs to remember lives in two local stores — a cache and a configuration store — and everything it produces is written back to the user's machine. The goal of this diagram is "what are the moving parts and who talks to whom," not implementation detail.

## Key design decisions

The orchestrator is the hub: it owns the sequencing (check cache, then fetch, then generate, then render) and is the single point where concurrency and configuration are applied. Storage is deliberately split into two stores with different lifecycles — a cache holding prunable work (videos, transcripts, run history) and a configuration store holding durable settings and credentials — so clearing the cache can never touch a user's setup. Every outbound generation call passes through one model gateway regardless of which AI provider is configured, which is what makes the system provider-agnostic (see the multi-provider diagram). The only two things that leave the machine are a read request to YouTube and a generation request to whichever provider the user configured.

## Tradeoffs

Concentrating orchestration in one component makes the system easy to reason about end-to-end, but that component carries real complexity — caching, fetching, chunking, and rendering decisions all pass through it. The two-store split costs a small amount of operational surface (two local databases instead of one) in exchange for a strong safety guarantee. Routing every AI call through one gateway trades a small amount of per-provider nuance for consistent retry, cost, and credential handling everywhere generation happens.

## How to talk through this diagram

**Spoken walkthrough:** "A user gives NoteWise a video, playlist, or batch of URLs. One orchestrator owns the whole request: it checks the local cache first, fetches from YouTube only if needed, sends the transcript through a model gateway to whichever AI provider is configured, and writes the result back to disk. Configuration and credentials live in a separate local store from the cache, and nothing leaves the machine except the YouTube fetch and the one generation call."

**Likely follow-ups:**
- *"Why split the cache from the configuration store instead of one database?"* — Different lifecycles and different risk profiles: the cache is safe to wipe or prune at any time, but credentials and settings must never be touched by a cache-maintenance operation. Separating them makes that safety guarantee structural instead of something you have to remember to enforce in code.
- *"What would you change if this had to run as a hosted service instead of a local CLI?"* — The orchestrator's concurrency model and local SQLite stores would need to move to something shared across instances (a real database and a queue instead of in-process semaphores), and the "local-first" trust boundary in this diagram would need a new one drawn around the service itself.
