# Release Notes - v0.1.9

## Summary
This release significantly improves the robustness, scalability, and feature set of `yt-study`. Key highlights include synthetic chapter generation for unchaptered videos, robust rate limiting to prevent YouTube IP blocks, and a redesigned concurrent processing pipeline with a live dashboard.

## Resolved Issues
- **#39: Handling Oversized Chapters**: Implemented recursive chunking within chapters to handle extremely long video segments without exceeding LLM context limits.
- **#38: Playlist Checkpointing**: Added logic to skip already processed videos in a playlist, allowing for seamless resumption after interruption.
- **#33: Rate Limiting**: Integrated `aiolimiter` to respect YouTube's request limits and prevent IP blocking during concurrent metadata fetching.
- **#26: Filename Sanitization**: Switched to `pathvalidate` for robust, cross-platform filename generation, resolving issues with reserved characters and Windows-specific constraints.
- **#8: Export Raw Transcript**: Added a new `--export-transcript` (or `--raw`) flag to save the raw YouTube transcript alongside the study notes.
- **#9: Timestamp Links**: All generated study notes now include clickable `[MM:SS]` links that jump directly to the relevant moment in the YouTube video.

## New Features
- **Synthetic Chapters**: Automatically generates a logical table of contents for videos that lack native YouTube chapters, ensuring structured notes for all content.
- **Diagnostics & Feedback**: New `bug-report` command to collect anonymized system info and simplify issue reporting.
- **Telemetry & Privacy**:
  - Optional usage analytics via PostHog to guide development.
  - Robust PII scrubbing ensures sensitive data (usernames, paths) never leaves your machine.
  - Easy opt-out with `yt-study config telemetry --off`.
- **Per-chunk Saving**: Intermediate LLM responses are now saved in a `chunks/` subdirectory, providing transparency into the generation process and a fallback if the final merge fails.
- **Advanced CLI Flags**:
  - `--no-chapters`: Skip using native YouTube chapters.
  - `--no-synthetic`: Disable synthetic chapter generation.
  - `--chunk-size`: Customize the token limit for transcript segments.
  - `--chunk-overlap`: Adjust the context overlap between segments.
  - `--export-transcript`: Save the raw transcript.
- **Improved Dashboard**: A new Rich-powered live UI shows the status of parallel workers, overall progress, and metadata fetching in real-time.

## Robustness & Architecture
- **Concurrent Processing**: Redesigned the pipeline with an `asyncio.Queue` based worker pool for more reliable parallel execution.
- **Property-Based Testing**: Added `hypothesis` tests to verify core logic against a wide range of edge cases and malformed inputs.
- **Encoding Fixes**: Unified character encoding across the codebase and documentation, eliminating legacy mojibake artifacts.
- **Cleanup**: Removed the `wiki` submodule; all documentation is now centrally managed in the `docs/` directory.
- **Error Handling**: Improved detection and reporting of YouTube IP blocks with actionable recommendations.
- **Retry Logic**: Added exponential backoff for network-related failures in playlist and transcript extraction.
- **Thread Offloading**: Network-heavy blocking calls are now properly offloaded to threads using `asyncio.to_thread` to keep the UI responsive.

---
