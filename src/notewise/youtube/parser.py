"""YouTube URL parser for video and playlist detection."""

import re
from urllib.parse import ParseResult, parse_qs, urlparse

from notewise.domain.youtube import ParsedURL
from notewise.errors import ValidationError


_VIDEO_ID_PATTERN = re.compile(r"^[0-9A-Za-z_-]{11}$")
_BARE_ID_PATTERN = re.compile(r"^[0-9A-Za-z_-]+$")
_PLAYLIST_ID_PREFIXES = (
    "PL",
    "UU",
    "LL",
    "FL",
    "RD",
    "UL",
    "WL",
    "OLAK5uy_",
)


def extract_video_id(url: str) -> str | None:
    """
    Extract video ID from various YouTube URL formats.

    Supports:
    - Standard: https://www.youtube.com/watch?v=VIDEO_ID
    - Short: https://youtu.be/VIDEO_ID
    - Embed: https://www.youtube.com/embed/VIDEO_ID
    - V-path: https://www.youtube.com/v/VIDEO_ID
    - Shorts: https://www.youtube.com/shorts/VIDEO_ID
    - Live: https://www.youtube.com/live/VIDEO_ID or https://youtu.be/live/VIDEO_ID

    Args:
        url: The YouTube URL string.

    Returns:
        The 11-character video ID if found, else None.
    """
    parsed = _parse_supported_youtube_url(url)
    if parsed is None:
        return None

    host = _normalized_hostname(parsed)
    if host == "youtu.be":
        segments = [part for part in parsed.path.split("/") if part]
        if segments and segments[0] == "live":
            segments = segments[1:]
        candidate = segments[0] if segments else ""
        return candidate if _is_video_id(candidate) else None

    path_parts = [part for part in parsed.path.split("/") if part]
    if not path_parts:
        return None

    if path_parts[0] == "watch":
        query_params = parse_qs(parsed.query)
        query_candidate = _first_query_value(query_params, "v")
        return query_candidate if _is_video_id(query_candidate) else None

    if path_parts[0] in {"embed", "v", "shorts", "live"} and len(path_parts) >= 2:
        candidate = path_parts[1]
        return candidate if _is_video_id(candidate) else None

    return None


def extract_playlist_id(url: str) -> str | None:
    """
    Extract playlist ID from YouTube playlist URL.

    Supports:
    - https://www.youtube.com/playlist?list=PLAYLIST_ID
    - https://www.youtube.com/watch?v=VIDEO_ID&list=PLAYLIST_ID

    Args:
        url: The YouTube URL string.

    Returns:
        The playlist ID if found, else None.
    """
    parsed = _parse_supported_youtube_url(url)
    if parsed is None:
        return None

    query_params = parse_qs(parsed.query)
    return _first_query_value(query_params, "list")


def parse_youtube_url(url: str) -> ParsedURL:
    """
    Parse a YouTube URL and determine if it's a video or playlist.

    Prioritizes playlist ID if 'list' parameter is present,
    but also extracts video ID if available (e.g. watching a playlist).

    Args:
        url: YouTube URL (video or playlist)

    Returns:
        ParsedURL object with url_type and relevant IDs

    Raises:
        ValidationError: If URL is not a valid YouTube URL (neither video nor
            playlist)
    """
    if not url or not isinstance(url, str):
        raise ValidationError("URL must be a non-empty string")

    bare_input = _parse_bare_youtube_id(url)
    if bare_input is not None:
        return bare_input

    # Check for playlist first
    playlist_id = extract_playlist_id(url)
    if playlist_id:
        # It's a playlist URL
        video_id = extract_video_id(url)  # Might have both
        return ParsedURL(
            url_type="playlist", playlist_id=playlist_id, video_id=video_id
        )

    # Check for video
    video_id = extract_video_id(url)
    if video_id:
        return ParsedURL(url_type="video", video_id=video_id)

    raise ValidationError(f"Invalid YouTube URL: {url}")


def _parse_bare_youtube_id(value: str) -> ParsedURL | None:
    """Interpret a bare YouTube video or playlist id without requiring a URL."""
    candidate = value.strip()
    if not candidate or candidate != value or not _BARE_ID_PATTERN.fullmatch(candidate):
        return None
    if _is_video_id(candidate):
        return ParsedURL(url_type="video", video_id=candidate)
    if _looks_like_playlist_id(candidate):
        return ParsedURL(url_type="playlist", playlist_id=candidate)
    return None


def _parse_supported_youtube_url(url: str) -> ParseResult | None:
    """Parse a URL only when it targets a supported YouTube host."""
    parsed = urlparse(url)
    host = _normalized_hostname(parsed)
    if host is None:
        return None
    if host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com"):
        return parsed
    return None


def _normalized_hostname(parsed: ParseResult) -> str | None:
    """Return a lower-cased hostname without a leading www. prefix."""
    hostname = parsed.hostname
    if not hostname:
        return None
    normalized = hostname.lower()
    return normalized.removeprefix("www.")


def _is_video_id(candidate: str | None) -> bool:
    """Return True when a candidate string looks like a YouTube video ID."""
    return bool(candidate and _VIDEO_ID_PATTERN.fullmatch(candidate))


def _looks_like_playlist_id(candidate: str) -> bool:
    """Return True when a bare string looks like a YouTube playlist id."""
    return len(candidate) >= 12 and candidate.startswith(_PLAYLIST_ID_PREFIXES)


def _first_query_value(
    query_params: dict[str, list[str]],
    key: str,
) -> str | None:
    """Return the first parsed query value for a key, if present."""
    values = query_params.get(key)
    if not values:
        return None
    return values[0]
