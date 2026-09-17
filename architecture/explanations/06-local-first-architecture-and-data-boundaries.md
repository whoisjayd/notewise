# Local-First Architecture and Data Boundaries

## What this shows

This diagram draws the trust boundary around the user's machine and shows exactly two things crossing it: a read-only content request to YouTube, and a generation request to whichever AI provider the user configured. Everything else — cache, configuration, credentials, session logs, and every generated document — stays local, and there is no telemetry or cloud backend of any kind.

## Key design decisions

All persistent state lives in local files the user already controls: a cache database, a configuration database, OAuth/subscription tokens, session logs, and the output documents themselves. Nothing is synced or reported anywhere by default. The only two network dependencies are structural, not incidental — the system cannot fetch a transcript without talking to YouTube, and it cannot generate notes without talking to an AI provider, so those two boundary crossings are drawn explicitly rather than treated as an implementation detail. No third network dependency exists: there's no analytics endpoint, no license-check service, no update-telemetry channel.

## Tradeoffs

Local-first means the user owns backup, sync, and multi-machine access themselves — there's no cloud fallback if a local database is lost, which is a deliberate privacy/ownership tradeoff rather than an oversight. Sending transcript text to an AI provider is unavoidable for generation to happen at all, so "local-first" here means "everything that doesn't have to leave, doesn't" rather than "fully offline" — the system still needs network access for its two core dependencies. Keeping credentials in a local file instead of a managed secrets service is simpler to operate but puts the burden of protecting that file on the user's own machine security.

## How to talk through this diagram

**Spoken walkthrough:** "Draw a boundary around the user's machine: the cache, the configuration and credentials, session logs, and every generated document all live inside it, and none of it is synced anywhere by default. Only two things cross that boundary — a read-only request to YouTube to get the transcript, and a generation request to whichever AI provider the user chose. There's no telemetry, no analytics, no cloud backend at all."

**Likely follow-ups:**
- *"Isn't local-first the same as offline?"* — No — the system still needs network access for its two structural dependencies, fetching from YouTube and generating with an AI provider. Local-first means state ownership and everything that doesn't need to leave the machine stays on it, not that the tool works with no network at all.
- *"What's the actual privacy exposure here?"* — Transcript text and generation prompts are sent to whichever AI provider the user explicitly configured — that's the one real exposure, and it's opt-in by design since the user chooses and can change the provider. Nothing else — cache contents, credentials, history — ever leaves the machine.
