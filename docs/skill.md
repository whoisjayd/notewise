---
name: notewise
description: Source-truth guide for helping users install, configure, operate, troubleshoot, and develop NoteWise, the YouTube-to-notes CLI using LiteLLM providers.
license: MIT
compatibility: Python 3.10+. Works on Linux, macOS, Windows, and Docker.
metadata:
  author: whoisjayd
  version: "3.0"
---

# NoteWise Agent Skill

Use this when answering questions about NoteWise `1.3.1`.

## Routes

| Intent | Route |
| --- | --- |
| Overview | `/docs` |
| Install | `/docs/start/install` |
| Quickstart | `/docs/start/quickstart` |
| Process videos | `/docs/use/process` |
| Playlists and batches | `/docs/use/playlists-batches` |
| Private videos and Docker | `/docs/use/private-docker` |
| Configuration | `/docs/config/configuration` |
| Models and providers | `/docs/config/providers` |
| OAuth login | `/docs/config/oauth` |
| CLI commands | `/docs/operate/commands` |
| Cache, logs, history, stats | `/docs/operate/cache-logs-history` |
| Troubleshooting | `/docs/operate/troubleshooting` |
| Pipeline and output | `/docs/understand/pipeline-output` |
| Storage, events, errors | `/docs/understand/storage-events` |
| Development | `/docs/understand/development` |

## Defaults

- Version: `1.3.1`
- Python: `>=3.10`
- Default model: `gemini/gemini-2.5-flash`
- Default output: `./output`
- Output formats: `md`, `html`, `pdf`, `docx`; default `md`
- Temperature: `0.7`
- Max concurrent videos: `5`
- YouTube RPM: `10`
- Chunk size / overlap: `4000` / `200`
- Max concurrent chapters: `3`

## Commands

Commands: `process`, `setup`, `config`, `config-path`, `version`, `update`, `stats`, `history`, `info`, `doctor`, `edit-config`, `auth login`, `cache`, `logs`.

`process` flags: `--model/-m`, `--output/-o`, `--format`, `--language/-l`, `--target-language`, `--temperature/-t`, `--max-tokens/-k`, `--throttle`, `--force/-F`, `--no-ui`, `--verbose/-v`, `--quiz`, `--use-combine-chunk`, `--export-transcript`, `--timestamps`, `--chapter-directory-output`, `--cookie-file/--cookies`.

## Config

Config file: `~/.notewise/config.env`. `NOTEWISE_HOME` changes the state root. Practical precedence: CLI flags, environment variables, config file, defaults.

Common keys: `DEFAULT_MODEL`, `OUTPUT_DIR`, `MAX_CONCURRENT_VIDEOS`, `YOUTUBE_REQUESTS_PER_MINUTE`, `TEMPERATURE`, `MAX_TOKENS`, `YOUTUBE_COOKIE_FILE`, provider API/auth keys. Do not present `chunk_size`, `chunk_overlap`, or `max_concurrent_chapters` as normal config-file keys.

## OAuth

- `notewise auth login chatgpt`, model `chatgpt/gpt-5.2`
- `notewise auth login github_copilot`, model `github_copilot/gpt-5-mini`
- `notewise auth login codex` is a ChatGPT alias
- Token dirs default under `<state>/oauth/...` unless `CHATGPT_TOKEN_DIR` or `GITHUB_COPILOT_TOKEN_DIR` is set

## Triage

Setup/provider: run `notewise doctor`, `notewise config`, `notewise logs --tail 100`, then check provider credentials and model string.

YouTube access: run `notewise info "URL"`, check captions/transcripts, use `--language`, and use `--cookie-file` for restricted videos.

Output/cache/logs: check `OUTPUT_DIR`, `--output`, cache skip behavior, `--force`, `--chapter-directory-output`, and `notewise cache show VIDEO_ID`.

## Security

Never request or expose API keys, OAuth tokens, cookies, raw prompts, provider payloads, or full unredacted logs.
