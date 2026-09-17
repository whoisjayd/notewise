# System Architecture

## What this shows

This diagram is the top-level map of notewise: a command-line application that turns YouTube videos into local study materials. It groups the system into five component boundaries — the user surface, processing orchestration, external data sources, local storage, and generated artifacts — and shows how requests and data move between them. Nothing below the component level appears here; the goal is to answer "what are the moving parts and who talks to whom," not "how is each part implemented."

## Key design decisions

The command-line interface is a thin front door: it parses commands, drives interactive wizards, and hands work to the processing orchestrator rather than doing any of the YouTube fetching, generation, or storage itself. The orchestrator is the hub of the system — it is the only component that talks to both the YouTube extraction layer and the AI provider abstraction, and it owns the sequencing between them (fetch first, generate second). The live dashboard is fed by a progress-event stream out of the orchestrator rather than polling state, keeping the terminal UI decoupled from pipeline internals. Storage is deliberately split into two databases with different lifecycles: one holding prunable cached work (videos, transcripts, run history) and one holding durable user configuration (settings, credentials, saved endpoints) — so clearing a cache can never destroy a user's setup. The AI provider abstraction is the single seam through which every outbound generation request passes, regardless of which provider is configured.

## Tradeoffs

Concentrating orchestration in one component makes the system easy to reason about end-to-end, but it also means that component carries real complexity — chunking decisions, chapter handling, caching, and artifact writing all pass through it. The two-database split adds a small amount of operational surface (two files instead of one) in exchange for a strong safety guarantee: cache maintenance commands are structurally incapable of touching credentials or settings. Routing all AI calls through a single abstraction layer trades a small amount of per-provider nuance for consistent retry, cost, and credential handling everywhere generation happens.
