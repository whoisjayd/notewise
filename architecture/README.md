# NoteWise Architecture

This folder documents NoteWise's architecture at a conceptual, implementation-independent level: what the major components are, how data and requests flow through them, and why the system is shaped the way it is. It is written for a technical but non-implementation audience — there are no function names, class names, file paths, or code-level identifiers anywhere in these documents. It also doubles as interview/portfolio material: each diagram is self-contained (own title banner, own scope) and each explanation includes a suggested spoken walkthrough and likely follow-up questions.

## How to read this folder

Each numbered topic is split into two separate files by design:

- `diagrams/NN-topic.mmd` — a pure [Mermaid](https://mermaid.js.org/) diagram (flowchart or sequence diagram) with no prose. Every diagram opens with a title banner node so it reads standalone.
- `explanations/NN-topic.md` — the prose explanation for that same diagram, following a consistent structure: **What this shows**, **Key design decisions**, **Tradeoffs**, and **How to talk through this diagram** (a spoken walkthrough plus likely interviewer follow-ups with short model answers).

Open the `.mmd` file in any Mermaid-compatible viewer (many Markdown editors, GitHub, the [Mermaid Live Editor](https://mermaid.live)) or import it into [Excalidraw](https://excalidraw.com) (Menu → Insert → paste Mermaid, or the mermaid-to-excalidraw plugin) alongside its paired explanation.

### Diagram conventions

Every flowchart uses the same color system so the diagrams read as one coherent set:

| Color | Category |
| ----- | -------- |
| Amber | User / person |
| Blue | Local component or process |
| Green | Local data store |
| Red | External network / third-party system |
| Purple | Decision point |
| Gray (dashed) | Title banner |

Sequence diagrams (diagram 02) use Mermaid's native actor/participant distinction instead, since `classDef` styling only applies to flowcharts.

## Diagram index

| # | Topic | Diagram | Explanation |
| - | ----- | ------- | ----------- |
| 01 | System architecture — the major components and how they relate; the diagram to open first | [diagrams/01-system-architecture.mmd](diagrams/01-system-architecture.mmd) | [explanations/01-system-architecture.md](explanations/01-system-architecture.md) |
| 02 | End-to-end processing flow — the temporal path of a single `process` request, from cache check through persistence | [diagrams/02-end-to-end-processing-flow.mmd](diagrams/02-end-to-end-processing-flow.mmd) | [explanations/02-end-to-end-processing-flow.md](explanations/02-end-to-end-processing-flow.md) |
| 03 | AI generation architecture — chunking strategy, chapter-aware vs. single-pass generation, parallel generation, and stitching | [diagrams/03-ai-generation-architecture.mmd](diagrams/03-ai-generation-architecture.mmd) | [explanations/03-ai-generation-architecture.md](explanations/03-ai-generation-architecture.md) |
| 04 | Reliability and caching architecture — retries/backoff, cache-driven work avoidance, partial-failure resume, and graceful degradation | [diagrams/04-reliability-and-caching-architecture.mmd](diagrams/04-reliability-and-caching-architecture.mmd) | [explanations/04-reliability-and-caching-architecture.md](explanations/04-reliability-and-caching-architecture.md) |
| 05 | Multi-provider AI architecture — provider-agnostic generation, built-in vs. custom endpoints, credential resolution, and cost estimation | [diagrams/05-multiprovider-ai-architecture.mmd](diagrams/05-multiprovider-ai-architecture.mmd) | [explanations/05-multiprovider-ai-architecture.md](explanations/05-multiprovider-ai-architecture.md) |
| 06 | Local-first architecture and data boundaries — what stays on disk, what leaves the machine, and the absence of telemetry | [diagrams/06-local-first-architecture-and-data-boundaries.mmd](diagrams/06-local-first-architecture-and-data-boundaries.mmd) | [explanations/06-local-first-architecture-and-data-boundaries.md](explanations/06-local-first-architecture-and-data-boundaries.md) |

## Scope note

Concurrency (per-video and per-chapter bounded parallelism) is intentionally not a separate diagram — it's already shown where it matters: as part of the orchestrator in (01), as the parallel-generation step in (03), and as the partial-failure/resume path in (04). A dedicated 7th diagram would have mostly repeated those three rather than adding a distinct view, so it was cut in favor of keeping six diagrams that are each worth presenting on their own.

## Suggested presentation order for an interview

Don't open with all six. Start with **01 (System Architecture)** as the anchor, then switch diagrams based on what's asked:

- "How does the system work?" → **01**
- "Walk me through a request." → **02**
- "How did you handle arbitrarily long videos?" → **03**
- "What happens when something fails?" → **04**
- "Why aren't you locked to one AI vendor?" → **05**
- "What happens to my data?" → **06**
