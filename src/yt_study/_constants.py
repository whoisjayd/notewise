"""Top-level application-wide constants for yt-study."""

from __future__ import annotations


# ── Cache ─────────────────────────────────────────────────────────────────────
CACHE_DB_FILENAME = ".yt_study_cache.db"
STATE_DIR_NAME = ".yt-study"
LOGS_DIR_NAME = "logs"
CONFIG_FILENAME = "config.env"
SESSION_LOG_PREFIX = "yt-study"
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

# ── Output ────────────────────────────────────────────────────────────────────
MAX_FILENAME_LENGTH = 100
