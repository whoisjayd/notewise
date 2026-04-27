"""Top-level application-wide constants for NoteWise."""

from __future__ import annotations


# ── Cache ─────────────────────────────────────────────────────────────────────
CACHE_DB_FILENAME = ".notewise_cache.db"
STATE_DIR_NAME = ".notewise"
LOGS_DIR_NAME = "logs"
CONFIG_FILENAME = "config.env"
SESSION_LOG_PREFIX = "notewise"
CHECKSUM_FILENAME = "SHA256SUMS.txt"
OUTPUT_METADATA_FILENAME = ".notewise-output.json"
OUTPUT_METADATA_VIDEO_ID_KEY = "video_id"
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
UPDATE_COMMAND_UV = "uv tool upgrade notewise"
UPDATE_COMMAND_PIPX = "pipx upgrade notewise"
UPDATE_COMMAND_PIP = "pip install --upgrade notewise"
UPDATE_INSTALLER_UNIX_URL = (
    f"https://github.com/{GITHUB_REPOSITORY_OWNER}/{GITHUB_REPOSITORY_NAME}/"
    "releases/latest/download/install.sh"
)
UPDATE_INSTALLER_WINDOWS_URL = (
    f"https://github.com/{GITHUB_REPOSITORY_OWNER}/{GITHUB_REPOSITORY_NAME}/"
    "releases/latest/download/install.ps1"
)
UPDATE_COMMAND_BINARY_UNIX = f"curl -fsSL {UPDATE_INSTALLER_UNIX_URL} | sh"
UPDATE_COMMAND_BINARY_WINDOWS = f"irm {UPDATE_INSTALLER_WINDOWS_URL} | iex"
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
        "safe_model": "chatgpt/gpt-5.3-codex",
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
OAUTH_LOGIN_CODEX_PROMPT = "Use Codex through which provider?"
OAUTH_LOGIN_UNSUPPORTED_PROVIDER_MESSAGE = (
    "Unsupported provider. Choose one of: {allowed}."
)
OAUTH_SETUP_RUN_PROMPT = "Run OAuth login now?"
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
    "guard",
    "image",
    "moderation",
    "realtime",
    "research",
    "robotics",
    "search",
    "safeguard",
    "speech",
    "transcribe",
    "tts",
    "ui-tars",
    "vision",
    "vl-",
    "vl_",
    "whisper",
)
LITELLM_PROVIDER_TEXT_MODEL_EXCLUDED_MARKERS = {
    "chatgpt": ("gpt-5.1-codex",),
}

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_MODEL = "gemini/gemini-2.5-flash"
DEFAULT_OUTPUT_DIR = "./output"
DEFAULT_LANGUAGES = ["en"]
DEFAULT_TARGET_LANGUAGE = "English"
DEFAULT_RENDERED_HTML_LANG = "en"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_CONCURRENT_VIDEOS = 5
DEFAULT_YOUTUBE_REQUESTS_PER_MINUTE = 10
DEFAULT_THROTTLE_SECONDS = 0.0
DEFAULT_CHUNK_SIZE = 4000  # tokens
DEFAULT_CHUNK_OVERLAP = 200  # tokens
DEFAULT_CHAPTER_MIN_DURATION = 3600  # seconds (1 hour)
DEFAULT_MAX_CONCURRENT_CHAPTERS = 3
DEFAULT_USE_COMBINE_CHUNK = False
DEFAULT_STITCH_SECTION_BOUNDARY_COUNT = 2
DEFAULT_STITCH_CHAR_BOUNDARY = 6000

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
