---
name: notewise
description: Source-truth guide for helping users install, configure, operate, troubleshoot, and develop NoteWise, the YouTube-to-notes CLI using LiteLLM providers.
license: MIT
compatibility: Python 3.11+. Works on Linux, macOS, Windows, and Docker.
metadata:
  author: whoisjayd
  version: "3.0"
---

# NoteWise Agent Skill

Use this when answering questions about NoteWise `1.6.0`.

Canonical public docs base: `https://notewise.click/docs`.

## Routes

| Intent                      | Route                              |
| --------------------------- | ---------------------------------- |
| Overview                    | `/docs`                            |
| Install                     | `/docs/start/install`              |
| Quickstart                  | `/docs/start/quickstart`           |
| Process videos              | `/docs/use/process`                |
| Playlists and batches       | `/docs/use/playlists-batches`      |
| Private videos and Docker   | `/docs/use/private-docker`         |
| Configuration               | `/docs/config/configuration`       |
| Models and providers        | `/docs/config/providers`           |
| OAuth login                 | `/docs/config/oauth`               |
| CLI commands                | `/docs/operate/commands`           |
| Cache, logs, history, stats | `/docs/operate/cache-logs-history` |
| Troubleshooting             | `/docs/operate/troubleshooting`    |
| Pipeline and output         | `/docs/understand/pipeline-output` |
| Storage, events, errors     | `/docs/understand/storage-events`  |
| Website and docs            | `/docs/understand/website-docs`    |
| Development                 | `/docs/understand/development`     |

## Defaults

- Version: `1.6.0`
- Python: `>=3.11`
- Default model: `gemini/gemini-2.5-flash`
- Default output: `./output`
- Output formats: `md`, `html`, `pdf`, `docx`; default `md`
- Temperature: `0.7`
- Max concurrent videos: `5`
- YouTube RPM: `10`
- Chunk size / overlap: `4000` / `200`
- Max concurrent chapters: `3`

## Commands

Commands: `process`, `setup`, `config`, `config-path`, `version`, `update`, `stats`, `history`, `info`, `doctor`, `edit-config`, `auth login`, `inference`, `cache`, `logs`.

`process` flags: `--model/-m`, `--base-url`, `--api-key`, `--output/-o`, `--format`, `--language/-l`, `--target-language`, `--temperature/-t`, `--max-tokens/-k`, `--throttle`, `--force/-F`, `--no-ui`, `--verbose/-v`, `--quiz`, `--export-transcript`, `--timestamps`, `--chapter-directory-output`, `--cookie-file/--cookies`.

`inference` manages saved OpenAI-compatible endpoints: `list`, `add <name> --base-url <url> --api-key <key> --model <model-id>`, `update`, and `delete`. It discovers and verifies models before saving; command-line API keys can remain in shell history. Names cannot use LiteLLM provider prefixes, remote endpoints require HTTPS, and a changed `--base-url` requires `--api-key`.

## Config

Config database: `~/.notewise/config.db`. `NOTEWISE_HOME` changes the state root. Practical precedence: CLI flags, then environment variables, then config database, then defaults. Exception: `OUTPUT_DIR` from the config database is respected unless `--output/-o` is passed.

Common keys: `DEFAULT_MODEL`, `CUSTOM_LLM_ENDPOINTS`, `OUTPUT_DIR`, `MAX_CONCURRENT_VIDEOS`, `YOUTUBE_REQUESTS_PER_MINUTE`, `TEMPERATURE`, `MAX_TOKENS`, `YOUTUBE_COOKIE_FILE`, provider API/auth keys. Custom models use `<name>/<model-id>` and `CUSTOM_LLM_ENDPOINTS` contains their API keys, so it must remain masked. Do not present `chunk_size`, `chunk_overlap`, or `max_concurrent_chapters` as normal config-file keys.

## OAuth

- `notewise auth login chatgpt`, model `chatgpt/gpt-5.6-luna`
- `notewise auth login github_copilot`, model `github_copilot/gpt-5-mini`
- `notewise auth login codex` is a ChatGPT alias
- Token dirs default under `<state>/oauth/...` unless `CHATGPT_TOKEN_DIR` or `GITHUB_COPILOT_TOKEN_DIR` is set

## Triage

Setup/provider: run `notewise doctor`, `notewise config`, `notewise logs --tail 100`, then check provider credentials and model string.

YouTube access: run `notewise info "URL"`, check captions/transcripts, use `--language`, and use `--cookie-file` for restricted videos.

Output/cache/logs: check `OUTPUT_DIR`, `--output`, cache skip behavior, `--force`, `--chapter-directory-output`, and `notewise cache show VIDEO_ID`.

## Security

Never request or expose API keys, OAuth tokens, cookies, raw prompts, provider payloads, or full unredacted logs.
