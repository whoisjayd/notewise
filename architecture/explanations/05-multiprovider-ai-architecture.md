# Multi-Provider AI Architecture

## What this shows

This diagram shows why NoteWise isn't locked to one AI vendor: every generation call goes through one unified interface, credentials resolve through a consistent precedence regardless of provider, and cost is estimated for every provider — including ones NoteWise has never seen before — through a layered fallback instead of a hardcoded price list.

## Key design decisions

The application layer depends on one stable generation interface, not on any single provider's API shape — the model is a configuration value, not an architectural dependency. Credentials resolve in a fixed order (an explicit key for this call, then saved configuration, then environment variables), so the same code path works whether a user is using a hosted provider, an OAuth-authenticated subscription, or a self-hosted OpenAI-compatible endpoint. Custom endpoints go through discovery and live verification before they're trusted — the system asks the endpoint what models it has and confirms one actually works before saving it. Cost estimation is layered: known providers use their published cost catalog, but for a custom or unlisted endpoint, NoteWise discovers pricing directly from the endpoint itself (when it advertises it) and falls back to that instead of silently reporting zero cost.

## Tradeoffs

Routing everything through one unified interface costs some provider-specific nuance (a feature only one vendor supports is harder to expose cleanly) in exchange for one consistent retry, cost, and credential story across every provider. Live-verifying a custom endpoint before saving it adds a network round-trip to setup, but it catches a broken configuration immediately instead of failing silently on the first real request. Falling back to endpoint-advertised pricing instead of a hardcoded price list means cost accuracy depends on the endpoint actually advertising it — when it doesn't, the system honestly reports zero rather than guessing.

## How to talk through this diagram

**Spoken walkthrough:** "The application never talks to a specific vendor's API directly — everything goes through one generation interface, and the model string in configuration decides which provider actually handles the call. Credentials resolve the same way for every provider: explicit key, then saved config, then environment. For custom or self-hosted endpoints, the system discovers what models are available, verifies one live, and estimates cost from whatever pricing the endpoint itself advertises — falling back to zero only when there's truly nothing to go on."

**Likely follow-ups:**
- *"How do you avoid double-maintaining cost data for every provider?"* — Well-known providers already carry cost data through the underlying multi-provider library NoteWise is built on; the endpoint-pricing-discovery path only exists as a fallback for the providers that library doesn't already know about, so there's no manual price list to maintain for the common case.
- *"What happens if a saved custom endpoint's model catalog changes after it's been added?"* — The same discovery-and-verification path runs again on update, so a stale or now-invalid model is caught the next time the endpoint's configuration is touched rather than failing silently mid-run.
