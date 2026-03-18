# Architecture

This document describes the internal structure of `yt-study` for contributors who want to understand how the pieces fit together.

## High-level overview

`yt-study` is a CLI application that accepts a YouTube URL (single video, playlist, or batch file), fetches transcript data from YouTube, and generates Markdown study notes (and optionally a quiz) through a large-language model.

The code is split into three main layers:

| Layer | Package           | Role                                                                     |
| ----- | ----------------- | ------------------------------------------------------------------------ |
| CLI   | `yt_study/cli.py` | Parses flags, owns Rich dashboard / headless printing, launches pipeline |
| Core  | `yt_study/core/`  | All business logic — YouTube retrieval, LLM generation, orchestration    |
| UI    | `yt_study/ui/`    | Rich live-dashboard rendering helpers                                    |

`core/` is UI-free by design; it never imports Rich or anything from `ui/`.

---

## Data-flow diagram

```mermaid
flowchart TD
    A([User runs yt-study with URL]) --> B[cli.py parses flags]
    B --> C{Input type?}

    C -->|single video| D[parser.py extracts video_id]
    C -->|playlist| E[playlist.py expands video IDs]
    C -->|batch file| F[cli.py expands batch entries into shared video jobs]

    D --> G[CorePipeline.run]
    E --> G
    F --> G

    subgraph Pipeline["core/pipeline.py"]
        G --> H[metadata.py fetches title, duration, and chapters]
        H --> I{Output exists?}

        I -->|yes and not force| J([VIDEO_SKIPPED])
        I -->|no or force| K[transcript.py fetches transcript]

        K --> L{Use chapters?}
        L -->|yes| M[generator creates chapter-based notes]
        L -->|no| N[generator creates standard notes]

        M --> O[write .md file or files]
        N --> O

        O --> P{Quiz enabled?}
        P -->|yes| Q[generator.generate_quiz writes _quiz.md]
        P -->|no| R([VIDEO_SUCCESS])

        Q --> R
    end

    G --> S([PIPELINE_COMPLETE])
    S --> T[cli.py prints success summary or clean failure panel]
```

---

## Class relationships

```mermaid
classDiagram
    direction TB

    class CorePipeline {
        +model
        +output_dir
        +force
        +quiz
        +generator
        +provider
        +run(video_ids, on_event) PipelineResult
        -_process_single_video(video_id, on_event) bool
        -_check_api_key() bool
        -_emit_event(on_event) Callable
    }

    class StudyMaterialGenerator {
        +provider
        +temperature
        +max_tokens
        +generate_study_notes(transcript, video_title, on_chunk) str
        +generate_single_chapter_notes(chapter_title, chapter_text) str
        +generate_chapter_based_notes(chapter_transcripts, video_title) str
        +generate_quiz(transcript) str
        -_chunk_transcript(text) List~String~
        -_count_tokens(text) int
    }

    class LLMProvider {
        +model
        +generate(system_prompt, user_prompt, temperature, max_tokens) str
    }

    class PipelineEvent {
        +event_type
        +video_id
        +title
        +chapter_number
        +total_chapters
        +chunk_number
        +total_chunks
        +error
        +output_path
    }

    class PipelineDashboard {
        +update(event)
        +RenderableType render()
    }

    CorePipeline --> StudyMaterialGenerator : owns
    CorePipeline --> LLMProvider : owns
    CorePipeline --> PipelineEvent : emits
    StudyMaterialGenerator --> LLMProvider : delegates to
    PipelineDashboard ..> PipelineEvent : consumes
```

---

## Async concurrency model

`CorePipeline.run()` processes multiple video IDs concurrently using `asyncio.gather`
guarded by a shared semaphore (`config.max_concurrent_videos`). Each video slot
corresponds to one worker in the Rich dashboard.

Concurrency depends on the entry shape:

- direct playlist processing passes playlist video IDs into one concurrent pipeline run
- batch-file processing expands playlist entries into per-video jobs inside one shared batch worker pool
- failed or private batch entries are collected and reported after the batch finishes instead of stopping remaining work

```mermaid
sequenceDiagram
    participant CLI
    participant Pipeline as CorePipeline
    participant W1 as Worker 1
    participant W2 as Worker 2
    participant LLM

    CLI->>Pipeline: run(["id1", "id2"])
    activate Pipeline

    Pipeline->>W1: _process_single_video("id1")
    activate W1

    Pipeline->>W2: _process_single_video("id2")
    activate W2

    W1-->>Pipeline: METADATA_FETCHED(id1)
    W2-->>Pipeline: METADATA_FETCHED(id2)

    W1->>LLM: generate(prompt)
    LLM-->>W1: notes

    W2->>LLM: generate(prompt)
    LLM-->>W2: notes

    W1-->>Pipeline: VIDEO_SUCCESS(id1)
    deactivate W1

    W2-->>Pipeline: VIDEO_SUCCESS(id2)
    deactivate W2

    Pipeline-->>CLI: PipelineResult
    deactivate Pipeline
```

---

## Module map

```text
src/yt_study/
├── __init__.py             — package version
├── cli.py                  — Typer app, flag parsing, dashboard bridge
├── setup_wizard.py         — interactive config writer
├── core/
│   ├── config.py           — runtime Config dataclass, env loading
│   ├── pipeline.py         — CorePipeline, PipelineEvent, EventType, sanitize_filename
│   ├── llm/
│   │   ├── generator.py    — StudyMaterialGenerator (chunking + generation)
│   │   └── providers.py    — LiteLLM async wrapper (LLMProvider)
│   ├── prompts/
│   │   ├── study_notes.py  — standard note-generation prompts
│   │   ├── chapter_notes.py— chapter note-generation prompts
│   │   └── quiz.py         — multiple-choice quiz prompts
│   └── youtube/
│       ├── parser.py       — URL parsing (video, playlist, shorts, embed)
│       ├── metadata.py     — title, duration, chapters, playlist info
│       ├── transcript.py   — transcript fetch with language fallback & retry
│       └── playlist.py     — playlist ID → video ID expansion with retry
└── ui/
    └── dashboard.py        — Rich live-dashboard state and rendering
```

---

## Key design rules

1. **`core/` is UI-free.** No Rich imports inside `src/yt_study/core/`.
2. **Blocking I/O off the event loop.** Native YouTube extractor calls are wrapped in `asyncio.to_thread(...)`.
3. **Progress via events.** `CorePipeline` emits `PipelineEvent` objects through a callback; the CLI converts them into dashboard updates, headless progress lines, and final summaries.
4. **User-facing failures stay in the CLI.** The terminal shows simplified, non-technical failures while detailed tracebacks stay in the current session log.
5. **Config is a 3-part contract.** Adding a provider key requires updating `Config.ALLOWED_KEYS`, `Config.get_api_key_name_for_model()`, and `Config._sync_env_vars()`.
