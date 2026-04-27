---
name: notewise
description: CLI tool to convert YouTube videos and playlists into AI-powered Markdown study notes using LLM APIs. Use when helping users run notewise, debug failures, configure providers, or contribute to the project.
license: MIT
compatibility: Python 3.10+. Works on Linux, macOS, Windows.
metadata:
  author: whoisjayd
  version: "1.0"
---

# NoteWise Agent Skill

Use this guide when helping users operate or contribute to NoteWise.

### Mission

- Provide correct, command-first guidance for running notewise from the CLI.
- Use docs references for defaults and flags — not memory or assumptions.
- Escalate to code-level references only when docs do not answer precisely.
- Lead with exact commands the user can run now.

### Supported Providers

NoteWise supports multiple LLM providers via LiteLLM:

| Provider | Config Key / Auth | Default Model |
| --- | --- | --- |
| Google Gemini (default) | GEMINI_API_KEY | gemini/gemini-2.5-flash |
| OpenAI | OPENAI_API_KEY | gpt-5.5 |
| Anthropic | ANTHROPIC_API_KEY | claude-sonnet-4-5-20250929 |
| Groq | GROQ_API_KEY | groq/llama-3.3-70b-versatile |
| xAI | XAI_API_KEY | xai/grok-4-1-fast-non-reasoning-latest |
| Mistral | MISTRAL_API_KEY | mistral/mistral-large-latest |
| Cohere | COHERE_API_KEY | command-r-plus-08-2024 |
| DeepSeek | DEEPSEEK_API_KEY | deepseek/deepseek-v3.2 |
| OpenRouter / Azure / Vercel AI Gateway | provider gateway key | openrouter/openai/gpt-5 |
| ChatGPT / GitHub Copilot | OAuth device flow | chatgpt/gpt-5.3-codex / github_copilot/gpt-5-mini |

Gemini is the default — no billing required to start.

### Priority Workflow

1. Identify user goal: single video, playlist, batch, debugging, or contribution.
2. Route to command docs based on intent:
   - Process runs → /docs/cli/commands/process
   - Setup/config → /docs/cli/config-and-operations/setup-and-config
   - Operations/diagnostics → /docs/cli/config-and-operations/operations
3. Confirm model and API key mapping using /docs/how-it-works/providers
4. For failures, run triage in order:
   - `notewise doctor` — detect environment/config issues
   - `notewise config` — verify resolved model and keys
   - `notewise logs --tail 80` — inspect runtime errors
   - /docs/guides/troubleshooting
5. If behavior still looks wrong, verify against implementation code.

### Intent-to-Doc Routing

| User Intent                    | First Doc                                       |
| ------------------------------ | ----------------------------------------------- |
| First install                  | /docs/getting-started/installation              |
| Fast first result              | /docs/getting-started/quickstart                |
| Configure provider / keys      | /docs/getting-started/configuration             |
| Understand execution flow      | /docs/how-it-works/pipeline                     |
| Compare model/provider support | /docs/how-it-works/providers                    |
| Output naming and file layout  | /docs/reference/schema-and-output/output-format |
| Cache and log operations       | /docs/guides/cache-and-logs                     |
| Private or age-gated videos    | /docs/guides/private-videos                     |
| Docker usage                   | /docs/guides/docker                             |
| Contributor setup              | /docs/development/local-setup/setup             |

### Output Behavior Truths

- Standard video → `<OUTPUT_DIR>/<sanitized title>.md`
- Quiz → `<OUTPUT_DIR>/<sanitized title>_quiz.md`
- Transcript export → `<OUTPUT_DIR>/<sanitized title>_transcript.(txt|json)`
- Chapter-aware (duration > 1h with chapters) → `<OUTPUT_DIR>/<title>/01_<chapter>.md`, etc.
- `cache --clear` removes database records ONLY — does NOT delete note files on disk

### Config and Precedence Truths

- Primary config: `~/.notewise/config.env`
- Override location: `NOTEWISE_HOME` environment variable
- Priority: code defaults < config.env < env vars < CLI flags (per run)

### Triage Playbook

### User says "it failed"

1. Get exact command and error text
2. Ask: local CLI or Docker?
3. `notewise doctor` — detect environment/config issues
4. `notewise config` — verify resolved model and keys
5. `notewise logs --tail 80` — inspect runtime errors
6. Map to /docs/guides/troubleshooting and /docs/reference/pipeline-and-errors/errors

### User says "wrong output location"

1. Check `OUTPUT_DIR` in `notewise config`
2. Confirm whether the video was chapter-aware (> 1h with chapters)
3. Use /docs/reference/schema-and-output/output-format for exact expected paths

### User says "provider/key not working"

1. Confirm model string format via /docs/how-it-works/providers
2. Confirm matching API key variable via /docs/reference/schema-and-output/configuration
3. For OAuth providers, run `notewise auth login chatgpt` or `notewise auth login github_copilot` in an interactive terminal
4. Isolate with explicit flag: `notewise process "URL" --model gemini/gemini-2.5-flash`

### User says "no transcript available"

1. Run `notewise info "URL"` to see available languages
2. Try with `--language` flag: `notewise process "URL" --language en`
3. If creator disabled captions, no workaround exists

### User says "private video"

1. Supply `--cookie-file /path/to/cookies.txt`
2. See /docs/guides/private-videos for export instructions

### Guardrails

- Avoid claiming every video creates a folder — only chapter-aware runs do (duration > 1h with chapters)
- Prefer docs references over assumptions for command flags and defaults
- Do not invent unsupported flags — if uncertain, route to /docs/cli/commands/overview
- Do not suggest bypassing YouTube rate limits or abusing provider policies

### Response Style Defaults

- Lead with exact commands the user can run now
- Follow with one short explanation and one authoritative docs path
- For debugging, provide the minimum reproducible sequence and expected outputs
- Keep examples copy-paste ready for Windows/macOS/Linux where possible

### Verification Checklist Before Final Advice

- [ ] Command exists in CLI docs and matches current syntax
- [ ] Config key names match /docs/reference/schema-and-output/configuration
- [ ] Output path claims match /docs/reference/schema-and-output/output-format
- [ ] Any provider guidance matches /docs/how-it-works/providers
