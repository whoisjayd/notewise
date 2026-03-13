# PROJECT KNOWLEDGE BASE

**Updated:** 2026-03-13
**Branch:** main

## OVERVIEW

`yt-study` is a Python CLI that converts YouTube videos, playlists, and URL batches into Markdown study notes using LLMs.

Core stack:

- Python 3.10+
- Typer CLI
- Rich TUI
- LiteLLM
- youtube-transcript-api
- pytubefix
- hatchling
- uv

Primary output styles:

- single Markdown file per video
- chapter-based Markdown output for long videos with chapters

## REPOSITORY STRUCTURE

```text
yt-study/
├── .github/                    # CI, release, issue templates, PR template
├── scripts/
│   └── hooks/                  # Local Git hook scripts
├── src/yt_study/
│   ├── __init__.py             # Package version
│   ├── cli.py                  # Typer app, logging, dashboard bridge
│   ├── setup_wizard.py         # Interactive config writer
│   ├── core/
│   │   ├── config.py           # Runtime config dataclass + env sync
│   │   ├── pipeline.py         # CorePipeline, PipelineEvent, EventType
│   │   ├── llm/
│   │   │   ├── generator.py    # Chunking + generation orchestration
│   │   │   └── providers.py    # LiteLLM wrapper
│   │   ├── prompts/
│   │   │   ├── study_notes.py  # Standard generation prompts
│   │   │   └── chapter_notes.py# Chapter generation prompts
│   │   └── youtube/
│   │       ├── parser.py       # URL parsing
│   │       ├── metadata.py     # Title, duration, chapters, playlist info
│   │       ├── transcript.py   # Transcript fetch + fallback logic
│   │       └── playlist.py     # Playlist expansion with retries
│   └── ui/
│       └── dashboard.py        # Rich live dashboard state/rendering
├── tests/                      # Pytest suite
├── wiki/                       # Git submodule for project wiki
├── Makefile                    # Cross-platform dev workflow
├── pyproject.toml              # Packaging, tooling, pytest, mypy, ruff
├── .pre-commit-config.yaml     # Hook configuration
├── README.md                   # User-facing overview
├── CONTRIBUTING.md             # Contributor workflow
└── AGENTS.md                   # This file
```

## IMPORTANT FILES TO KNOW

| Area | File | Why it matters |
| --- | --- | --- |
| CLI | `src/yt_study/cli.py` | Defines commands, logging, batch handling, dashboard bridge |
| Setup | `src/yt_study/setup_wizard.py` | Writes `~/.yt-study/config.env` |
| Config | `src/yt_study/core/config.py` | Actual supported runtime keys and provider mapping |
| Pipeline | `src/yt_study/core/pipeline.py` | Main orchestration logic and event model |
| LLM | `src/yt_study/core/llm/generator.py` | Chunking strategy and note generation |
| Provider | `src/yt_study/core/llm/providers.py` | LiteLLM async completion wrapper |
| YouTube | `src/yt_study/core/youtube/transcript.py` | Transcript fallback and retry logic |
| YouTube | `src/yt_study/core/youtube/metadata.py` | Duration/title/chapters/playlist info |
| YouTube | `src/yt_study/core/youtube/playlist.py` | Playlist ID expansion |
| UI | `src/yt_study/ui/dashboard.py` | Rich dashboard rendering |
| Tests | `tests/test_pipeline/test_core_pipeline.py` | Best reference for expected pipeline behavior |
| Workflow | `Makefile` | Canonical local commands |
| Hooks | `.pre-commit-config.yaml` | Actual enforced local checks |
| CI | `.github/workflows/ci-main.yml` | Main validation and matrix jobs |

## CLI SURFACE

Commands:

```bash
yt-study setup
yt-study setup --force
yt-study process "URL_OR_FILE"
yt-study config-path
yt-study version
```

`process` options:

```bash
--model / -m
--output / -o
--language / -l
--temperature / -t
--max-tokens / -k
```

Accepted input shapes for `process`:

- single YouTube video URL
- playlist URL
- text file with one URL per line

Batch-file behavior:

- blank lines ignored
- lines beginning with `#` ignored
- each remaining line processed sequentially as its own input

## CURRENT CONFIG MODEL

Runtime config file:

```text
~/.yt-study/config.env
```

Load order:

1. `~/.yt-study/config.env`
2. environment variables override file values
3. supported provider keys synced back into `os.environ`

Supported runtime keys today:

- `DEFAULT_MODEL`
- `OUTPUT_DIR`
- `MAX_CONCURRENT_VIDEOS`
- `TEMPERATURE`
- `MAX_TOKENS`
- `GEMINI_API_KEY`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GROQ_API_KEY`
- `XAI_API_KEY`
- `MISTRAL_API_KEY`
- `COHERE_API_KEY`
- `DEEPSEEK_API_KEY`
- `YOUTUBE_REQUESTS_PER_MINUTE`

Important distinction:

- `default_languages`, `chunk_size`, `chunk_overlap`, and `chapter_generation_min_duration` exist as code defaults in `Config`
- they are not currently first-class `config.env` keys loaded by `Config._load_from_user_config()`

Provider mapping implemented in `Config.get_api_key_name_for_model()`:

| Model family | Required env key |
| --- | --- |
| `gemini`, `vertex` | `GEMINI_API_KEY` |
| `gpt`, `openai` | `OPENAI_API_KEY` |
| `claude`, `anthropic` | `ANTHROPIC_API_KEY` |
| `groq` | `GROQ_API_KEY` |
| `grok`, `xai` | `XAI_API_KEY` |
| `mistral` | `MISTRAL_API_KEY` |
| `cohere`, `command` | `COHERE_API_KEY` |
| `deepseek` | `DEEPSEEK_API_KEY` |

## ARCHITECTURE RULES

### 1. `core/` stays UI-free

Do not import Rich, `Console`, or dashboard components into `src/yt_study/core/`.

### 2. Blocking YouTube calls stay off the event loop

Use `asyncio.to_thread(...)` for `pytubefix` and `youtube-transcript-api` work.

### 3. Progress moves through `PipelineEvent`

The pipeline emits events and the CLI converts them into UI updates.

### 4. Chapter output is orchestrated in `CorePipeline`

Do not wire persisted chapter output through `generate_chapter_based_notes()` for the main pipeline path.

### 5. Config provider support is a 3-part contract

If you add a provider key, update all of:

- `Config.ALLOWED_KEYS`
- `Config.get_api_key_name_for_model()`
- `Config._sync_env_vars()`

## PIPELINE EVENT MODEL

Event enum: `src/yt_study/core/pipeline.py`

- `PIPELINE_START`
- `METADATA_START`
- `METADATA_FETCHED`
- `TRANSCRIPT_FETCHING`
- `TRANSCRIPT_FETCHED`
- `GENERATION_START`
- `CHUNK_GENERATING`
- `CHAPTER_GENERATING`
- `GENERATION_COMPLETE`
- `VIDEO_SUCCESS`
- `VIDEO_FAILED`
- `PIPELINE_COMPLETE`

Single-video event flow:

```text
PIPELINE_START
  -> METADATA_START
  -> METADATA_FETCHED
  -> TRANSCRIPT_FETCHING
  -> TRANSCRIPT_FETCHED
  -> GENERATION_START or CHAPTER_GENERATING x N
  -> GENERATION_COMPLETE
  -> VIDEO_SUCCESS
PIPELINE_COMPLETE
```

Failure path:

```text
... -> VIDEO_FAILED -> PIPELINE_COMPLETE
```

Pipeline-level events use an empty `video_id` sentinel.

## GENERATION LOGIC

### Standard path

`StudyMaterialGenerator.generate_study_notes()`:

1. count tokens
2. chunk transcript when needed
3. generate per-chunk notes
4. combine chunk notes into one final document

Single-chunk fast path:

- uses `get_single_pass_prompt(...)`
- skips the combine call

### Chapter path

Activated when:

- video duration is greater than `config.chapter_generation_min_duration` (`3600`)
- chapters are available

Output path:

```text
{output_dir}/{safe_video_title}/{i:02d}_{safe_chapter}.md
```

### Chunking algorithm

Priority order:

1. sentence boundaries
2. newline boundaries
3. space boundaries
4. hard split by character limit

Defaults:

- `chunk_size = 4000`
- `chunk_overlap = 200`

Token counting:

- `litellm.token_counter(...)`
- fallback to `len(text) // 4`

## YOUTUBE RETRIEVAL RULES

### URL parser

Supported:

- watch URLs
- `youtu.be`
- `embed`
- `shorts`
- playlist URLs
- watch URLs containing `list=...`

### Transcript priority

`fetch_transcript()` tries:

1. manual transcript in preferred languages
2. generated transcript in preferred languages
3. manual transcript in any language
4. any transcript, translated to English if possible

### Retry behavior

- transcript fetch retries transient failures up to 3 times
- playlist extraction retries up to 3 times
- backoff uses `2**attempt`

### IP block handling

`YouTubeIPBlockError` is surfaced when YouTube blocks requests. The pipeline records a failure and continues with other videos.

## OUTPUT RULES

Filename sanitization:

- strips `<>:"/\\|?*`
- collapses whitespace
- trims to 100 chars
- returns `untitled` for empty or dot-only names

Standard output:

```text
output/
  Video Title.md
```

Playlist output:

```text
output/
  Playlist Name/
    Video One.md
    Long Video/
      01_Intro.md
```

## LOGGING

Configured in `src/yt_study/cli.py`.

- LiteLLM logging suppressed early
- session logs go to `~/.yt-study/logs`
- fallback to `./logs` if the home directory is unavailable
- console only shows warning-level output and higher

## TEST MAP

| Test file | Focus |
| --- | --- |
| `tests/test_cli.py` | Typer command behavior, flags, config-path, setup |
| `tests/test_config.py` | env/file loading and validation |
| `tests/test_setup_wizard.py` | setup wizard prompts and save/load behavior |
| `tests/test_ui.py` | dashboard state and render output |
| `tests/test_llm/test_generator.py` | chunking and generation calls |
| `tests/test_llm/test_providers.py` | LiteLLM wrapper behavior |
| `tests/test_pipeline/test_core_pipeline.py` | event flow, output creation, chapter path |
| `tests/test_youtube/test_parser.py` | URL parsing |
| `tests/test_youtube/test_transcript.py` | transcript fallback and retry logic |
| `tests/test_youtube/test_metadata.py` | metadata extraction |
| `tests/test_youtube/test_playlist.py` | playlist extraction retries |

## DEVELOPMENT COMMANDS

Canonical commands come from `Makefile`.

Setup:

```bash
make sync
make install
make install-dev
make dev-setup
```

Quality:

```bash
make format
make format-check
make lint
make lint-check
make type-check
make deps-check
make security
make check
make verify
```

Testing:

```bash
make test
make test-fast
make test-cov
make test-watch
make test-failed
make test-verbose
```

Hooks:

```bash
make hooks-install
make hooks-run
make pre-commit
```

Build/release:

```bash
make build
make publish
make publish-test
```

## HOOKS AND CI

Pre-commit hooks include:

- repo hygiene checks
- Ruff format/lint
- Bandit
- conventional commit validation
- single-line commit enforcement
- mypy
- deptry
- pytest on pre-push

GitHub workflows:

- `ci-main.yml`: format, lint, mypy, coverage, cross-platform test matrix
- `pr-gate.yml`: PR checks
- `release.yml`: validate, build, publish to PyPI, create GitHub release

## WIKI AND DOCS WORKFLOW

The `wiki/` directory is a Git submodule.

Implications:

- docs updates can touch both parent-repo files and submodule content
- new wiki pages must be linked from `wiki/Home.md`
- README and wiki should stay aligned on commands, config keys, and output behavior

When behavior changes:

- update `README.md` for user-facing summary changes
- update `wiki/` for detailed reference pages
- update `CONTRIBUTING.md` for workflow changes
- update this file when the repo map or engineering rules change

## KNOWN GOTCHAS

- Do not document repo-root `.env` as the runtime config source.
- Do not claim unsupported provider env keys are wired unless `Config` actually supports them.
- `yt-study --help` or other Rich-heavy output can hit Unicode issues on legacy Windows consoles; prefer Windows Terminal or UTF-8 mode when documenting support paths.
- Avoid nested Rich progress bars; the current dashboard uses one overall bar plus worker status rows.

## QUICK DECISION GUIDE

If asked to change...

- CLI behavior: start with `src/yt_study/cli.py`
- setup/config flow: inspect `setup_wizard.py` and `core/config.py`
- note generation: inspect `core/llm/generator.py` and `core/prompts/`
- transcript issues: inspect `core/youtube/transcript.py`
- playlist expansion: inspect `core/youtube/playlist.py`
- dashboard rendering: inspect `ui/dashboard.py`
- contributor workflow/docs: inspect `Makefile`, `.pre-commit-config.yaml`, `.github/workflows/`, `CONTRIBUTING.md`, and `wiki/`
