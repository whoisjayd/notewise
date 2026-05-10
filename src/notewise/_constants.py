"""Top-level application-wide constants for NoteWise."""

from __future__ import annotations

from typing import Any


# ── Cache ─────────────────────────────────────────────────────────────────────
CACHE_DB_FILENAME = ".notewise_cache.db"
STATE_DIR_NAME = ".notewise"
LOGS_DIR_NAME = "logs"
CONFIG_FILENAME = "config.env"
SESSION_LOG_PREFIX = "notewise"
CHECKSUM_FILENAME = "SHA256SUMS.txt"
OUTPUT_METADATA_FILENAME = ".notewise-output.json"
OUTPUT_METADATA_VIDEO_ID_KEY = "video_id"
MASKED_SECRET_MIN_VISIBLE_LENGTH = 8
MASKED_SECRET_PREFIX_LENGTH = 6
MASKED_SECRET_SUFFIX_LENGTH = 4
SANITIZED_FILENAME_FALLBACK = "untitled"
INVALID_FILENAME_CHARS_PATTERN = r'[<>:"/\\|?*\x00-\x1f\x7f]'
RESERVED_WINDOWS_FILENAME_PATTERN = r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)"
WHITESPACE_PATTERN = r"\s+"
BOOL_SETTING_TRUTHY_VALUES = frozenset({"1", "true", "yes", "on"})
BOOL_SETTING_FALSY_VALUES = frozenset({"0", "false", "no", "off"})
PYDANTIC_RESPONSE_USAGE_WARNING_PATTERN = (
    r"(?s)^Pydantic serializer warnings:.*ResponseAPIUsage"
)
GITHUB_REPOSITORY_OWNER = "whoisjayd"
GITHUB_REPOSITORY_NAME = "notewise"
LATEST_RELEASE_API_URL = (
    f"https://api.github.com/repos/{GITHUB_REPOSITORY_OWNER}/"
    f"{GITHUB_REPOSITORY_NAME}/releases/latest"
)
RELEASES_PAGE_URL = (
    f"https://github.com/{GITHUB_REPOSITORY_OWNER}/{GITHUB_REPOSITORY_NAME}/releases"
)
UPDATER_USER_AGENT = "NoteWise-Updater"
UPDATE_HTTP_TIMEOUT_SECONDS = 30
UPDATE_INSTALL_SOURCE_BINARY = "Standalone Binary"
UPDATE_INSTALL_SOURCE_PYTHON = "Python Package"
UPDATE_COMMAND_UV = "uv tool upgrade notewise"
UPDATE_COMMAND_PIPX = "pipx upgrade notewise"
UPDATE_COMMAND_PIP = "python -m pip install --upgrade notewise"
UPDATE_INSTALLER_UNIX_URL = "https://notewise.click/install"
UPDATE_INSTALLER_WINDOWS_URL = "https://notewise.click/install"
UPDATE_COMMAND_BINARY_UNIX = f"curl -fsSL {UPDATE_INSTALLER_UNIX_URL} | sh"
UPDATE_COMMAND_BINARY_WINDOWS = f"irm {UPDATE_INSTALLER_WINDOWS_URL} | iex"
UPDATE_METADATA_PARSE_ERROR = "Could not parse latest release metadata."
LEGACY_CONFIG_KEYS = frozenset(
    {
        "YOUTUBE_USE_OAUTH",
        "YOUTUBE_SAVE_OAUTH_TOKEN",
        "YOUTUBE_OAUTH_TOKEN_FILE",
        "YOUTUBE_AUTO_REFRESH_OAUTH_TOKEN",
    }
)


def _build_provider_api_key_env_vars(
    api_key_providers: dict[str, tuple[str, ...]],
) -> dict[str, tuple[str, ...]]:
    """Build provider->accepted API-key env vars from env-var groups."""
    provider_env_vars: dict[str, list[str]] = {}
    for env_var, providers in api_key_providers.items():
        for provider in providers:
            provider_env_vars.setdefault(provider, []).append(env_var)
    return {
        provider: tuple(env_vars) for provider, env_vars in provider_env_vars.items()
    }


PROVIDER_API_KEY_ENV_VAR_PROVIDERS: dict[str, tuple[str, ...]] = {
    "AI21_API_KEY": ("ai21",),
    "ANTHROPIC_API_KEY": ("anthropic",),
    "AZURE_API_KEY": ("azure", "azure_ai", "azure_text"),
    "AZURE_OPENAI_API_KEY": ("azure", "azure_text"),
    "CEREBRAS_API_KEY": ("cerebras",),
    "CLOUDFLARE_API_KEY": ("cloudflare",),
    "COHERE_API_KEY": ("cohere", "cohere_chat"),
    "DASHSCOPE_API_KEY": ("dashscope",),
    "DATABRICKS_API_KEY": ("databricks",),
    "DEEPINFRA_API_KEY": ("deepinfra",),
    "DEEPSEEK_API_KEY": ("deepseek",),
    "FIREWORKS_AI_API_KEY": ("fireworks_ai", "fireworks_ai-embedding-models"),
    "GEMINI_API_KEY": ("gemini", "vertex", "vertex_ai"),
    "GROQ_API_KEY": ("groq",),
    "HUGGINGFACE_API_KEY": ("huggingface",),
    "JINA_API_KEY": ("jina_ai",),
    "MISTRAL_API_KEY": ("mistral",),
    "NOVITA_API_KEY": ("novita",),
    "NVIDIA_NIM_API_KEY": ("nvidia_nim",),
    "OPENAI_API_KEY": ("openai",),
    "OPENROUTER_API_KEY": ("openrouter",),
    "PERPLEXITYAI_API_KEY": ("perplexity",),
    "REPLICATE_API_KEY": ("replicate",),
    "SAMBANOVA_API_KEY": ("sambanova",),
    "TOGETHERAI_API_KEY": ("together", "together_ai"),
    "VERCEL_AI_GATEWAY_API_KEY": ("vercel_ai_gateway",),
    "VOYAGE_API_KEY": ("voyage",),
    "WATSONX_API_KEY": ("watsonx",),
    "XAI_API_KEY": ("xai",),
}
PROVIDER_API_KEY_ENV_VARS = _build_provider_api_key_env_vars(
    PROVIDER_API_KEY_ENV_VAR_PROVIDERS
)
PROVIDER_SECRET_ENV_KEYS = frozenset(PROVIDER_API_KEY_ENV_VAR_PROVIDERS) | frozenset(
    {
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
    }
)
OAUTH_DEVICE_PROVIDER_PREFIXES = frozenset({"chatgpt", "github_copilot"})
OAUTH_LOGIN_CODEX_ALIAS = "codex"
OAUTH_LOGIN_ALLOWED_PROVIDERS = (
    "chatgpt",
    "github_copilot",
    OAUTH_LOGIN_CODEX_ALIAS,
)
OAUTH_LOGIN_DIRECT_PROVIDERS = ("chatgpt", "github_copilot")
OAUTH_PROVIDER_CONFIGS: dict[str, dict[str, str]] = {
    "chatgpt": {
        "label": "ChatGPT Subscription",
        "safe_model": "chatgpt/gpt-5.2",
        "token_dir_env": "CHATGPT_TOKEN_DIR",
        "token_dir_name": "chatgpt",
    },
    "github_copilot": {
        "label": "GitHub Copilot",
        "safe_model": "github_copilot/gpt-5-mini",
        "token_dir_env": "GITHUB_COPILOT_TOKEN_DIR",
        "token_dir_name": "github_copilot",
    },
}
AUTH_TYPE_API_KEY = "api_key"
AUTH_TYPE_OAUTH_DEVICE = "oauth_device"
PROVIDER_CONFIG: dict[str, dict[str, Any]] = {
    "gemini": {
        "name": "Google Gemini",
        "auth_type": AUTH_TYPE_API_KEY,
        "env_var": "GEMINI_API_KEY",
        "api_url": "https://aistudio.google.com/app/apikey",
        "keywords": ["gemini", "vertex"],
        "litellm_providers": ["gemini"],
    },
    "openai": {
        "name": "OpenAI (ChatGPT)",
        "auth_type": AUTH_TYPE_API_KEY,
        "env_var": "OPENAI_API_KEY",
        "api_url": "https://platform.openai.com/api-keys",
        "keywords": ["gpt", "openai", "o1", "o3", "o4"],
        "litellm_providers": ["openai"],
    },
    "anthropic": {
        "name": "Anthropic (Claude)",
        "auth_type": AUTH_TYPE_API_KEY,
        "env_var": "ANTHROPIC_API_KEY",
        "api_url": "https://console.anthropic.com/settings/keys",
        "keywords": ["claude", "anthropic"],
        "litellm_providers": ["anthropic"],
    },
    "groq": {
        "name": "Groq",
        "auth_type": AUTH_TYPE_API_KEY,
        "env_var": "GROQ_API_KEY",
        "api_url": "https://console.groq.com/keys",
        "keywords": ["groq"],
        "litellm_providers": ["groq"],
    },
    "xai": {
        "name": "xAI (Grok)",
        "auth_type": AUTH_TYPE_API_KEY,
        "env_var": "XAI_API_KEY",
        "api_url": "https://console.x.ai/",
        "keywords": ["grok", "xai"],
        "litellm_providers": ["xai"],
    },
    "mistral": {
        "name": "Mistral AI",
        "auth_type": AUTH_TYPE_API_KEY,
        "env_var": "MISTRAL_API_KEY",
        "api_url": "https://console.mistral.ai/api-keys/",
        "keywords": ["mistral"],
        "litellm_providers": ["mistral"],
    },
    "cohere": {
        "name": "Cohere",
        "auth_type": AUTH_TYPE_API_KEY,
        "env_var": "COHERE_API_KEY",
        "api_url": "https://dashboard.cohere.com/api-keys",
        "keywords": ["cohere", "command"],
        "litellm_providers": ["cohere_chat", "cohere"],
    },
    "deepseek": {
        "name": "DeepSeek",
        "auth_type": AUTH_TYPE_API_KEY,
        "env_var": "DEEPSEEK_API_KEY",
        "api_url": "https://platform.deepseek.com/api_keys",
        "keywords": ["deepseek"],
        "litellm_providers": ["deepseek"],
    },
    "openrouter": {
        "name": "OpenRouter",
        "auth_type": AUTH_TYPE_API_KEY,
        "env_var": "OPENROUTER_API_KEY",
        "api_url": "https://openrouter.ai/settings/keys",
        "keywords": ["openrouter"],
        "litellm_providers": ["openrouter"],
    },
    "together_ai": {
        "name": "Together AI",
        "auth_type": AUTH_TYPE_API_KEY,
        "env_var": "TOGETHERAI_API_KEY",
        "api_url": "https://api.together.ai/settings/api-keys",
        "keywords": ["together"],
        "litellm_providers": ["together_ai"],
    },
    "fireworks_ai": {
        "name": "Fireworks AI",
        "auth_type": AUTH_TYPE_API_KEY,
        "env_var": "FIREWORKS_AI_API_KEY",
        "api_url": "https://fireworks.ai/account/api-keys",
        "keywords": ["fireworks"],
        "litellm_providers": ["fireworks_ai"],
    },
    "perplexity": {
        "name": "Perplexity",
        "auth_type": AUTH_TYPE_API_KEY,
        "env_var": "PERPLEXITYAI_API_KEY",
        "api_url": "https://www.perplexity.ai/settings/api",
        "keywords": ["perplexity", "sonar"],
        "litellm_providers": ["perplexity"],
    },
    "github_copilot": {
        "name": "GitHub Copilot",
        "auth_type": AUTH_TYPE_OAUTH_DEVICE,
        "api_url": "https://docs.github.com/en/copilot",
        "keywords": ["github_copilot", "copilot", "codex"],
        "litellm_providers": ["github_copilot"],
    },
    "chatgpt": {
        "name": "ChatGPT Subscription",
        "auth_type": AUTH_TYPE_OAUTH_DEVICE,
        "api_url": "https://chatgpt.com/",
        "keywords": ["chatgpt", "codex"],
        "litellm_providers": ["chatgpt"],
    },
}
OAUTH_LOGIN_PROVIDER_LABELS = {
    provider: config["label"] for provider, config in OAUTH_PROVIDER_CONFIGS.items()
}
OAUTH_LOGIN_SAFE_MODELS = {
    provider: config["safe_model"]
    for provider, config in OAUTH_PROVIDER_CONFIGS.items()
}
OAUTH_TOKEN_DIR_PARENT = "oauth"
OAUTH_TOKEN_DIR_ENV_VARS = {
    provider: config["token_dir_env"]
    for provider, config in OAUTH_PROVIDER_CONFIGS.items()
}
OAUTH_TOKEN_DIR_NAMES = {
    provider: config["token_dir_name"]
    for provider, config in OAUTH_PROVIDER_CONFIGS.items()
}
OAUTH_LOGIN_TEST_PROMPT = "Reply with OK."
OAUTH_LOGIN_TEST_INSTRUCTIONS = "You are validating OAuth login for notewise."
OAUTH_LOGIN_TEST_MAX_OUTPUT_TOKENS = 4
OAUTH_LOGIN_SUCCESS_MESSAGE = (
    "OAuth login succeeded for {provider_label} using {model}."
)
OAUTH_LOGIN_FAILURE_MESSAGE = "OAuth login failed for {provider_label}: {error}"
OAUTH_LOGIN_STORAGE_GUIDANCE = (
    "No API key was written to notewise config. OAuth tokens are stored under "
    "the notewise state directory by default: {storage_paths}. Override with "
    "CHATGPT_TOKEN_DIR or GITHUB_COPILOT_TOKEN_DIR if needed."
)
OAUTH_LOGIN_TRIGGER_MESSAGE = (
    "LiteLLM may print a device code or browser URL. Complete that prompt to "
    "finish provider authentication."
)
OAUTH_LOGIN_PROVIDER_PROMPT = "Select OAuth provider"
OAUTH_LOGIN_UNSUPPORTED_PROVIDER_MESSAGE = (
    "Unsupported provider. Choose one of: {allowed}."
)
OAUTH_UNSUPPORTED_PROVIDER_ERROR = "Unsupported OAuth provider: {provider}."
OAUTH_SETUP_RUN_PROMPT = "Run OAuth login now?"
OAUTH_FALLBACK_MESSAGE = (
    "OAuth login failed or was cancelled. "
    "Run `notewise auth login` for your provider and try again."
)
UNSUPPORTED_MODEL_MESSAGE = (
    "Model {model} is not currently supported for {provider_label}. "
    "Run `notewise setup --force` to choose a supported model. "
    "Supported models include: {supported_models}."
)
UNSUPPORTED_MODEL_LIST_LIMIT = 8
AMBIENT_CREDENTIAL_PROVIDER_PREFIXES = frozenset(
    {"amazon_nova", "bedrock", "bedrock_converse", "sagemaker"}
)
PROVIDER_AUTH_ENV_KEYS = frozenset(
    {
        "AWS_ACCESS_KEY_ID",
        "AWS_PROFILE",
        "AWS_REGION_NAME",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "ANTHROPIC_API_BASE",
        "AZURE_API_BASE",
        "AZURE_API_VERSION",
        "AZURE_OPENAI_ENDPOINT",
        "CHATGPT_API_BASE",
        "CHATGPT_AUTH_FILE",
        "CHATGPT_ORIGINATOR",
        "CHATGPT_TOKEN_DIR",
        "CHATGPT_USER_AGENT",
        "CHATGPT_USER_AGENT_SUFFIX",
        "CLOUDFLARE_ACCOUNT_ID",
        "DATABRICKS_API_BASE",
        "GITHUB_COPILOT_ACCESS_TOKEN_FILE",
        "GITHUB_COPILOT_ACCESS_TOKEN_URL",
        "GITHUB_COPILOT_API_BASE",
        "GITHUB_COPILOT_API_KEY_FILE",
        "GITHUB_COPILOT_API_KEY_URL",
        "GITHUB_COPILOT_DEVICE_CODE_URL",
        "GITHUB_COPILOT_TOKEN_DIR",
        "HUGGINGFACE_API_BASE",
        "OPENAI_API_BASE",
        "OPENAI_BASE_URL",
        "OPENAI_CHATGPT_API_BASE",
        "VERTEX_PROJECT",
        "VERTEXAI_PROJECT",
        "VERTEX_LOCATION",
        "VERTEXAI_LOCATION",
    }
)
PROVIDER_REQUIRED_ENV_VARS = {
    "cloudflare": ("CLOUDFLARE_ACCOUNT_ID",),
    "databricks": ("DATABRICKS_API_BASE",),
}
RESPONSES_API_PROVIDER_PREFIXES = frozenset({"chatgpt", "github_copilot"})
RESPONSES_API_ALL_MODEL_PROVIDER_PREFIXES = frozenset({"chatgpt"})
RESPONSES_API_MODEL_MARKERS = ("codex",)
GPT5_MODEL_MARKER = "gpt-5"
GPT5_REQUIRED_TEMPERATURE = 1.0
LITELLM_TEXT_MODEL_EXCLUDED_MARKERS = (
    "audio",
    "computer-use",
    "container",
    "embedding",
    "firellava",
    "flux",
    "glm-4p5v",
    "guard",
    "image",
    "internvl3",
    "llava",
    "moderation",
    "pixtral",
    "realtime",
    "research",
    "robotics",
    "rolm-ocr",
    "search",
    "safeguard",
    "speech",
    "transcribe",
    "tts",
    "ui-tars",
    "vision",
    "-vl",
    "vl-",
    "vl_",
    "whisper",
)
LITELLM_PROVIDER_TEXT_MODEL_EXCLUDED_MARKERS = {
    "chatgpt": ("gpt-5.1-codex",),
}
STRIP_SAFE_PROVIDER_ALIASES = frozenset(
    {
        "gemini",
        "openai",
        "anthropic",
        "groq",
        "xai",
        "mistral",
        "cohere",
        "deepseek",
        "fireworks_ai",
        "chatgpt",
        "github_copilot",
        "vertex_ai",
    }
)
THIRD_PARTY_DIAGNOSTIC_LOGGERS = (
    "LiteLLM",
    "litellm",
    "openai",
    "openai._base_client",
    "httpx",
    "httpcore",
)

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_MODEL = "gemini/gemini-2.5-flash"
DEFAULT_OUTPUT_DIR = "./output"
DEFAULT_LANGUAGES = ["en"]
DEFAULT_TARGET_LANGUAGE = "English"
DEFAULT_RENDERED_HTML_LANG = "en"
DEFAULT_TEMPERATURE = 0.7
MIN_TEMPERATURE = 0.0
MAX_TEMPERATURE = 1.0
DEFAULT_MAX_CONCURRENT_VIDEOS = 5
DEFAULT_YOUTUBE_REQUESTS_PER_MINUTE = 10
DEFAULT_THROTTLE_SECONDS = 0.0
MIN_THROTTLE_SECONDS = 0.0
DEFAULT_CHUNK_SIZE = 4000  # tokens
DEFAULT_CHUNK_OVERLAP = 200  # tokens
DEFAULT_MAX_CONCURRENT_CHAPTERS = 3
DEFAULT_STITCH_SECTION_BOUNDARY_COUNT = 2
DEFAULT_STITCH_CHAR_BOUNDARY = 6000
TOKEN_ESTIMATE_CHARS_PER_TOKEN = 4
MIN_ESTIMATED_TOKENS = 1
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600

# ── Dashboard UI ───────────────────────────────────────────────────────────────
DASHBOARD_RECENT_ACTIVITY_LIMIT = 5
DASHBOARD_ACTIVITY_TITLE_LIMIT = 60
DASHBOARD_WORKER_TITLE_LIMIT = 42
DASHBOARD_WORKER_DETAIL_LIMIT = 44
DASHBOARD_CONFIG_VALUE_LIMIT = 52
DASHBOARD_SKIPPED_SUFFIX = " (skipped)"
DASHBOARD_PROGRESS_BAR_WIDTH = 40
DASHBOARD_ACTIVE_PHASE = "Active"
DASHBOARD_IDLE_STATUS = "Idle"
DASHBOARD_IDLE_MARKUP = "[dim]Idle[/dim]"
BATCH_SOURCE_UNEXPECTED_ERROR_TITLE = "Could not resolve batch source"
BATCH_SOURCE_UNEXPECTED_ERROR_MESSAGE = (
    "notewise hit an unexpected internal error while resolving this source. "
    "Check the current log for details."
)
DASHBOARD_UNKNOWN_VALUE = "—"
DASHBOARD_HEADER_SOURCE_LABEL = "📑 Source:"
DASHBOARD_HEADER_OUTPUT_LABEL = "📁 Output:"
DASHBOARD_HEADER_MODEL_ICON = "🤖"
DASHBOARD_HEADER_LIVE_LABEL = "Rich live dashboard"
DASHBOARD_PROGRESS_LABEL_MARKUP = "[bold blue]Total Progress"
DASHBOARD_PROGRESS_PERCENT_MARKUP = "[bold green]{task.percentage:>3.0f}%"
DASHBOARD_PROGRESS_TOTAL_MARKUP = "[bold white]{task.completed}/{task.total}"
DASHBOARD_PROGRESS_SEPARATOR = "•"
CLI_COST_DECIMAL_PLACES = 6
CLI_SECONDS_DECIMAL_PLACES = 2
DASHBOARD_WORKER_LABEL_TEMPLATE = "{prefix} Worker {number}"
DASHBOARD_WORKER_VIDEO_PREFIX = "W"
DASHBOARD_WORKER_TABLE_HEADERS = ("ID", "Phase", "Video", "Detail", "Elapsed")
DASHBOARD_SUMMARY_COMPLETED_LABEL = "Completed"
DASHBOARD_SUMMARY_SKIPPED_LABEL = "Skipped"
DASHBOARD_SUMMARY_FAILED_LABEL = "Failed"
DASHBOARD_SUMMARY_RUNNING_LABEL = "Running"
DASHBOARD_SUMMARY_QUEUED_LABEL = "Queued"
DASHBOARD_RECENT_EMPTY_MARKUP = "[dim italic]No videos completed yet...[/]"
DASHBOARD_SECTION_RUN_STATUS = "Run Status"
DASHBOARD_SECTION_FLAGS_CONFIG = "Flags & Config"
DASHBOARD_SECTION_WORKERS = "Workers"
DASHBOARD_SECTION_ACTIVE_TASKS = "Active Tasks"
DASHBOARD_SECTION_CHAPTER_TASKS = "Chapter Tasks"
DASHBOARD_SECTION_RECENT_ACTIVITY = "Recent Activity"
DASHBOARD_SECTION_RUN_STATUS_HEADING = f"📊 {DASHBOARD_SECTION_RUN_STATUS}"
DASHBOARD_SECTION_FLAGS_CONFIG_HEADING = f"⚙️ {DASHBOARD_SECTION_FLAGS_CONFIG}"
DASHBOARD_SECTION_WORKERS_HEADING = f"👷 {DASHBOARD_SECTION_WORKERS}"
DASHBOARD_SECTION_ACTIVE_TASKS_HEADING = f"⚡ {DASHBOARD_SECTION_ACTIVE_TASKS}"
DASHBOARD_SECTION_CHAPTER_TASKS_HEADING = f"🧩 {DASHBOARD_SECTION_CHAPTER_TASKS}"
DASHBOARD_SECTION_RECENT_ACTIVITY_HEADING = f"✅ {DASHBOARD_SECTION_RECENT_ACTIVITY}"
DASHBOARD_PANEL_TITLE_MARKUP = (
    "[bold cyan]🎓 YouTube Study Material Pipeline[/bold cyan]"
)

# ── Retry ─────────────────────────────────────────────────────────────────────
TRANSCRIPT_MAX_RETRIES = 3
PLAYLIST_MAX_RETRIES = 3
LLM_NUM_RETRIES = 3
LLM_ERROR_PAYLOAD_MARKERS = (
    "complete_input_dict",
    "input=[",
    "json_data",
    "messages",
    "request payload",
)
LLM_PAYLOAD_ERROR_SUMMARY = (
    "Provider request failed. The provider returned an error containing request "
    "payload details, so notewise suppressed it from logs."
)
HTTP_MAX_RETRIES = 3
HTTP_BACKOFF_BASE = 1.0

# ── Output ────────────────────────────────────────────────────────────────────
MAX_FILENAME_LENGTH = 100
LITELLM_MODELS_SNAPSHOT_FILENAME = "litellm_models_snapshot.json"
LITELLM_MODEL_METADATA_SOURCE_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)
LITELLM_MODEL_METADATA_FETCH_TIMEOUT_SECONDS = 30
LITELLM_MODEL_METADATA_FIELDS = (
    "litellm_provider",
    "mode",
    "max_input_tokens",
    "max_output_tokens",
    "max_tokens",
    "supported_endpoints",
    "supported_output_modalities",
    "supports_function_calling",
    "supports_parallel_function_calling",
    "supports_prompt_caching",
    "supports_reasoning",
    "supports_response_schema",
    "supports_system_messages",
)
DEFAULT_NOTES_OUTPUT_FORMAT = "md"
SUPPORTED_NOTES_OUTPUT_FORMATS = ("md", "html", "pdf", "docx")
OUTPUT_FORMAT_SEPARATOR = ","
NOTES_OUTPUT_EXTENSIONS = {
    "md": ".md",
    "html": ".html",
    "pdf": ".pdf",
    "docx": ".docx",
}
HTML_LANGUAGE_ALIASES = {
    "arabic": "ar",
    "bengali": "bn",
    "english": "en",
    "french": "fr",
    "german": "de",
    "gujarati": "gu",
    "hindi": "hi",
    "italian": "it",
    "japanese": "ja",
    "kannada": "kn",
    "korean": "ko",
    "malayalam": "ml",
    "marathi": "mr",
    "polish": "pl",
    "portuguese": "pt",
    "portuguese (brazil)": "pt-BR",
    "portuguese-brazil": "pt-BR",
    "pt-br": "pt-BR",
    "punjabi": "pa",
    "russian": "ru",
    "spanish": "es",
    "tamil": "ta",
    "telugu": "te",
    "turkish": "tr",
    "urdu": "ur",
}
PDF_UNSUPPORTED_UNICODE_ERROR = (
    "PDF output currently supports Latin-script text only. "
    "Use Markdown, HTML, or DOCX for {target_language} output."
)
MARKDOWN_RENDER_EXTENSIONS = ("extra", "sane_lists")
CHAPTER_BUNDLE_SEPARATOR = "\n\n---\n\n"
DOCX_BODY_FONT_NAME = "Aptos"
DOCX_HEADING_FONT_NAME = "Aptos Display"
DOCX_BODY_FONT_SIZE_PT = 11
DOCX_TITLE_FONT_SIZE_PT = 22
DOCX_HEADING_ONE_FONT_SIZE_PT = 16
DOCX_HEADING_TWO_FONT_SIZE_PT = 13
DOCX_HEADING_THREE_FONT_SIZE_PT = 11
DOCX_BODY_SPACE_AFTER_PT = 6
DOCX_HEADING_SPACE_BEFORE_PT = 10
DOCX_HEADING_SPACE_AFTER_PT = 4
DOCX_SECTION_MARGIN_INCHES = 0.75
DEFAULT_RENDERED_HTML_STYLES = """
body {
    background: #f3f0ea;
    color: #171717;
    font-family: "Georgia", "Times New Roman", serif;
    font-size: 16px;
    line-height: 1.55;
    margin: 0;
}

.document {
    background: #ffffff;
    box-shadow: 0 18px 40px rgba(15, 23, 42, 0.08);
    margin: 0 auto;
    max-width: 820px;
    padding: 32px 40px;
}

h1,
h2,
h3,
h4,
h5,
h6 {
    color: #111827;
    font-family: Arial, Helvetica, sans-serif;
    line-height: 1.2;
    margin-bottom: 0.35em;
}

h1 {
    border-bottom: 1px solid #e5e7eb;
    font-size: 2rem;
    margin-top: 0;
    padding-bottom: 0.3em;
}

h2 {
    font-size: 1.35rem;
    margin-top: 1.3em;
}

h3 {
    font-size: 1.05rem;
    margin-top: 1.1em;
}

p,
blockquote,
pre,
table {
    margin: 0.55em 0 0.85em;
}

ul,
ol {
    margin: 0.4em 0 0.85em 1.25em;
    padding-left: 0.4em;
}

li {
    margin: 0.2em 0;
}

p code,
li code,
td code,
blockquote code {
    background: #f4f1ea;
    border-radius: 4px;
    font-family: "Courier New", Courier, monospace;
    padding: 0.15em 0.35em;
}

pre {
    background: #171717;
    border-radius: 8px;
    color: #fafaf9;
    overflow-x: auto;
    padding: 14px 16px;
}

pre code {
    background: transparent;
    color: inherit;
    padding: 0;
}

blockquote {
    border-left: 3px solid #d6d3d1;
    color: #57534e;
    margin-left: 0;
    padding-left: 14px;
}

table {
    border-collapse: collapse;
    font-size: 0.95rem;
    width: 100%;
}

th,
td {
    border: 1px solid #d6d3d1;
    padding: 8px 10px;
    text-align: left;
}

th {
    background: #fafaf9;
}

hr {
    border: 0;
    border-top: 1px solid #e7e5e4;
    margin: 1.5em 0;
}
"""
