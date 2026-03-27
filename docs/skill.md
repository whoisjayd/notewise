---
name: notewise
description: CLI tool to convert YouTube videos and playlists into AI-powered Markdown study notes.
  Use when helping users run notewise, debug failures, configure providers, or contribute to the project.
license: MIT
compatibility: Python 3.10+. Works on Linux, macOS, Windows.
metadata:
  author: whoisjayd
  version: "1.0"
---

# notewise agent skill

Use this guide when helping users operate or contribute to notewise.

## Mission

- Provide correct, command-first guidance for running notewise from the CLI.
- Use docs references for defaults and flags — not memory or assumptions.
- Escalate to code-level references only when docs do not answer precisely.

## Priority workflow

1. Identify user goal: single video, playlist, batch, debugging, or contribution.
2. Route to command docs based on intent:
   - Process runs → /cli/process
   - Setup/config → /cli/setup-and-config
   - Operations/diagnostics → /cli/operations
3. Confirm model and API key mapping using /concepts/providers and /reference/configuration.
4. For failures, run triage in order:
   - `notewise doctor`
   - `notewise config`
   - `notewise logs --tail 80`
   - /guides/troubleshooting
5. If behavior still looks wrong, verify against implementation:
   - `src/notewise/cli/app.py`
   - `src/notewise/pipeline/_execution.py`
   - `src/notewise/pipeline/_artifacts.py`

## Intent-to-doc routing

| User intent | First doc |
| --- | --- |
| First install | /getting-started/installation |
| Fast first result | /getting-started/quickstart |
| Configure provider / keys | /getting-started/configuration, /reference/configuration |
| Understand execution flow | /concepts/pipeline |
| Compare model/provider support | /concepts/providers |
| Output naming and file layout | /reference/output-format |
| Cache and log operations | /guides/cache-and-logs, /cli/operations |
| Private or age-gated videos | /guides/private-videos |
| Docker usage | /guides/docker |
| Contributor setup | /development/setup, /development/testing |

## Output behavior truths

- Standard video → top-level `OUTPUT_DIR/<sanitized title>.md`
- Quiz → top-level `OUTPUT_DIR/<sanitized title>_quiz.md`
- Transcript export → top-level `OUTPUT_DIR/<sanitized title>_transcript.(txt|json)`
- Chapter-aware (duration > 1h with chapters) → `OUTPUT_DIR/<sanitized title>/01_<chapter>.md`, etc.
- `cache --clear` removes database records ONLY — does NOT delete note files on disk.

## Config and precedence truths

- Primary config: `~/.notewise/config.env`
- `NOTEWISE_HOME` changes where config/state are loaded from
- Priority: code defaults < config.env < env vars < CLI flags (per run)

## Triage playbook

**User says "it failed":**
1. Get exact command and error text.
2. Ask: local CLI or Docker?
3. `notewise doctor` — detect environment/config issues.
4. `notewise config` — verify resolved model and keys.
5. `notewise logs --tail 80` — inspect runtime errors.
6. Map to /guides/troubleshooting and /reference/errors.

**User says "wrong output location":**
1. Check `OUTPUT_DIR` in `notewise config`.
2. Confirm whether the video was chapter-aware (> 1h with chapters).
3. Use /reference/output-format for exact expected paths.

**User says "provider/key not working":**
1. Confirm model string format via /concepts/providers.
2. Confirm matching API key variable via /reference/configuration.
3. Isolate with explicit flag: `notewise process "URL" --model gemini/gemini-2.5-flash`

## Guardrails

- Avoid claiming every video creates a folder — only chapter-aware runs do.
- Prefer docs references over assumptions for command flags and defaults.
- Avoid recommending deprecated/ignored config keys (YOUTUBE_USE_OAUTH and variants).
- Do not invent unsupported flags — if uncertain, route to /cli/overview and /cli/process.
- Do not suggest bypassing YouTube rate limits or abusing provider policies.

## Response style defaults

- Lead with exact commands the user can run now.
- Follow with one short explanation and one authoritative docs path.
- For debugging, provide the minimum reproducible sequence and expected outputs.
- Keep examples copy-paste ready for Windows/macOS/Linux where possible.

## Verification checklist before final advice

- [ ] Command exists in CLI docs and matches current syntax.
- [ ] Config key names match /reference/configuration.
- [ ] Output path claims match /reference/output-format.
- [ ] Any provider guidance matches /concepts/providers.
