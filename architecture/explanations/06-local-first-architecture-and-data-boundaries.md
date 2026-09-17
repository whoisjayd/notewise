# Local-First Architecture and Data Boundaries

## What this shows

A trust-boundary view: everything inside the "user's machine" box stays on disk, and only two categories of outbound network calls ever leave it — requests to YouTube for video content, and requests to whichever single AI provider the user has configured, carrying transcript text for generation. There is no cloud backend, and no telemetry channel, drawn anywhere in this diagram because none exists.

## Key design decisions

All durable state lives under one local state directory, split by concern rather than combined: a cache database for prunable processing history (video metadata, transcripts, run stats, export records), a separate configuration database for durable settings and credentials (API keys, saved custom endpoint profiles), OAuth/subscription tokens stored in their own location, plain-text session logs, and the generated study documents themselves. Every one of these is a local file the user fully owns and can delete. The network boundary is narrow and named explicitly: the application talks to YouTube to read public video data, and it talks to exactly one AI provider — the one the user configured — to turn transcript text into notes. Nothing else initiates outbound traffic; there is no usage reporting, crash reporting, or update-check-with-tracking baked into the core pipeline.

## Tradeoffs

Keeping everything local means the user is responsible for their own backup, sync, and multi-machine story — there's no server-side source of truth to fall back on, which is the deliberate cost of not running a backend at all. Storing provider API keys and OAuth tokens on disk (rather than in a managed secrets service) is simpler and requires no additional infrastructure, but it puts the burden of file permissions and machine security on the local environment. Sending full transcript text to the configured AI provider is unavoidable given how generation works, but it does mean the privacy boundary of the whole system is only as strong as the user's choice of provider — the architecture makes that choice explicit and singular rather than fanning transcript data out to multiple services.
