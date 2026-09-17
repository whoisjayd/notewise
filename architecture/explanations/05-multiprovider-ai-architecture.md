# Multi-Provider AI Architecture

## What this shows

How the system stays provider-agnostic despite supporting many different AI backends. It shows a single unified generation interface sitting between the rest of the application and two categories of providers — built-in hosted/OAuth providers and user-defined custom OpenAI-compatible endpoints — plus the credential resolution and cost estimation logic that has to work uniformly across both categories.

## Key design decisions

Every generation call, regardless of provider, passes through one unified interface built on a third-party multi-provider abstraction library, so the rest of the system never branches on "which provider is this." Credential resolution follows a fixed precedence (an explicitly supplied key, then saved configuration, then environment variables) applied identically whether the model is a well-known hosted provider or a custom endpoint. Custom OpenAI-compatible endpoints get their own onboarding path — model discovery, then a live verification call, then optional pricing discovery — all run once at setup time and the result (including any endpoint-advertised pricing) is saved as a named profile, rather than repeating discovery on every generation call. Cost estimation is layered: it first tries the provider abstraction's own catalog pricing, and only falls back to saved custom-endpoint pricing when the model is unmapped — treating cost as "best-effort estimate," not a promise of billing accuracy.

## Tradeoffs

Routing everything through one abstraction layer means the system inherits that layer's provider coverage and quirks rather than hand-tuning each integration, which is a large simplification but occasionally means provider-specific behavior needs workarounds elsewhere (for example, special handling for certain reasoning-style models). Verifying custom endpoints live at setup time (rather than trusting whatever the user types) adds friction to onboarding a new endpoint but avoids silently saving a broken configuration. Falling back to zero-cost estimates for genuinely unmapped models is an honest "we don't know" rather than a guess, but it does mean displayed cost can understate real spend for obscure or newly launched gateways until pricing is discoverable.
