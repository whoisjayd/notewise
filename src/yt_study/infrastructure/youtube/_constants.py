"""YouTube-specific constants used across the infrastructure layer."""

from __future__ import annotations


# ── URL templates ─────────────────────────────────────────────────────────────
YOUTUBE_WATCH_URL = "https://www.youtube.com/watch?v={video_id}"
YOUTUBE_PLAYLIST_URL = "https://www.youtube.com/playlist?list={playlist_id}"
YOUTUBE_CHANNEL_URL = "https://www.youtube.com/channel/{channel_id}"

# ── Innertube API ─────────────────────────────────────────────────────────────
INNERTUBE_BASE_URL = "https://www.youtube.com/youtubei/v1"
INNERTUBE_CLIENT_NAME = "WEB"
INNERTUBE_CLIENT_VERSION = "2.20250626.01.00"

# ── Request defaults ──────────────────────────────────────────────────────────
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_ACCEPT_LANGUAGE = "en-US,en;q=0.9"
REQUEST_TIMEOUT_SECONDS = 30

# ── Transcript formats ────────────────────────────────────────────────────────
TRANSCRIPT_FORMAT_PRIORITY = ("json3", "srv3", "srv2", "srv1", "ttml", "vtt", "srt")

# ── Pagination ────────────────────────────────────────────────────────────────
MAX_PLAYLIST_PAGES = 250

# ── Android fallback client ───────────────────────────────────────────────────
ANDROID_CLIENT_NAME = "ANDROID"
ANDROID_CLIENT_VERSION = "20.10.38"
ANDROID_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/65.0.3325.181 "
    "Mobile Safari/537.36"
)
