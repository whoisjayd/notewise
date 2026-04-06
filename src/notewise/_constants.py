"""Top-level application-wide constants for NoteWise."""

from __future__ import annotations


# ── Cache ─────────────────────────────────────────────────────────────────────
CACHE_DB_FILENAME = ".notewise_cache.db"
STATE_DIR_NAME = ".notewise"
LOGS_DIR_NAME = "logs"
CONFIG_FILENAME = "config.env"
SESSION_LOG_PREFIX = "notewise"
CHECKSUM_FILENAME = "SHA256SUMS.txt"
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

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_MODEL = "gemini/gemini-2.5-flash"
DEFAULT_OUTPUT_DIR = "./output"
DEFAULT_LANGUAGES = ["en"]
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_CONCURRENT_VIDEOS = 5
DEFAULT_YOUTUBE_REQUESTS_PER_MINUTE = 10
DEFAULT_CHUNK_SIZE = 4000  # tokens
DEFAULT_CHUNK_OVERLAP = 200  # tokens
DEFAULT_CHAPTER_MIN_DURATION = 3600  # seconds (1 hour)
DEFAULT_MAX_CONCURRENT_CHAPTERS = 3

# ── Retry ─────────────────────────────────────────────────────────────────────
TRANSCRIPT_MAX_RETRIES = 3
PLAYLIST_MAX_RETRIES = 3
LLM_NUM_RETRIES = 3
HTTP_MAX_RETRIES = 3
HTTP_BACKOFF_BASE = 1.0

# ── Output ────────────────────────────────────────────────────────────────────
MAX_FILENAME_LENGTH = 100
LITELLM_MODELS_SNAPSHOT_FILENAME = "litellm_models_snapshot.json"
