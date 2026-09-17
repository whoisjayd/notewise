# notewise Architecture

This folder documents notewise's architecture at a conceptual, implementation-independent level: what the major components are, how data and requests flow through them, and why the system is shaped the way it is. It is written for a technical but non-implementation audience — there are no function names, class names, file paths, or code-level identifiers anywhere in these documents.

## How to read this folder

Each numbered topic is split into two separate files by design:

- `diagrams/NN-topic.mmd` — a pure [Mermaid](https://mermaid.js.org/) diagram (flowchart or sequence diagram, whichever fits the topic) with no prose.
- `explanations/NN-topic.md` — the prose explanation for that same diagram, following a consistent structure: **What this shows**, **Key design decisions**, and **Tradeoffs**.

Open the `.mmd` file in any Mermaid-compatible viewer (many Markdown editors, GitHub, or the [Mermaid Live Editor](https://mermaid.live)) alongside its paired explanation.

## Diagram index

| # | Topic | Diagram | Explanation |
| - | ----- | ------- | ----------- |
| 01 | System architecture — the major components (CLI, pipeline, provider layer, storage, YouTube extraction, UI/dashboard) and how they relate | [diagrams/01-system-architecture.mmd](diagrams/01-system-architecture.mmd) | [explanations/01-system-architecture.md](explanations/01-system-architecture.md) |
| 02 | End-to-end processing flow — the temporal/causal path of a single `process` request, from cache check through persistence | [diagrams/02-end-to-end-processing-flow.mmd](diagrams/02-end-to-end-processing-flow.mmd) | [explanations/02-end-to-end-processing-flow.md](explanations/02-end-to-end-processing-flow.md) |
| 03 | AI generation architecture — how transcript text becomes notes: chunking, chapter-aware vs. single-pass generation, stitching, and quiz generation | [diagrams/03-ai-generation-architecture.mmd](diagrams/03-ai-generation-architecture.mmd) | [explanations/03-ai-generation-architecture.md](explanations/03-ai-generation-architecture.md) |
| 04 | Reliability and caching architecture — retries/backoff, cache-driven work avoidance, partial-failure isolation, and graceful degradation | [diagrams/04-reliability-and-caching-architecture.mmd](diagrams/04-reliability-and-caching-architecture.mmd) | [explanations/04-reliability-and-caching-architecture.md](explanations/04-reliability-and-caching-architecture.md) |
| 05 | Multi-provider AI architecture — provider-agnostic generation, built-in vs. custom endpoints, credential resolution, and cost estimation | [diagrams/05-multiprovider-ai-architecture.mmd](diagrams/05-multiprovider-ai-architecture.mmd) | [explanations/05-multiprovider-ai-architecture.md](explanations/05-multiprovider-ai-architecture.md) |
| 06 | Local-first architecture and data boundaries — what stays on disk, what leaves the machine, the two local databases, and the absence of telemetry | [diagrams/06-local-first-architecture-and-data-boundaries.mmd](diagrams/06-local-first-architecture-and-data-boundaries.mmd) | [explanations/06-local-first-architecture-and-data-boundaries.md](explanations/06-local-first-architecture-and-data-boundaries.md) |
| 07 | CLI and configuration architecture — the command surface, layered configuration resolution, and interactive setup tooling | [diagrams/07-cli-and-configuration-architecture.mmd](diagrams/07-cli-and-configuration-architecture.mmd) | [explanations/07-cli-and-configuration-architecture.md](explanations/07-cli-and-configuration-architecture.md) |

## Scope note

Diagram 07 goes beyond the six required views because the command surface and its layered configuration-resolution model (flags > saved config > environment > defaults), plus the interactive setup/config/endpoint tooling, form a genuinely distinct architectural concern from both the processing pipeline (02–04) and the provider layer (05) — it is the system's control-plane, not its data-plane. No other additions were made beyond the requested six plus this one, to avoid padding.
