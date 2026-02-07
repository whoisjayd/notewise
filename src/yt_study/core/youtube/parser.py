"""YouTube URL parser for video and playlist detection."""

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse


@dataclass
class ParsedURL:
    """
    Parsed YouTube URL information.

    Attributes:
        url_type: Type of the URL ('video' or 'playlist').
        video_id: Extracted video ID (if present).
        playlist_id: Extracted playlist ID (if present).
    """

    url_type: str  # 'video' or 'playlist'
    video_id: str | None = None
    playlist_id: str | None = None


def extract_video_id(url: str) -> str | None:
    """
    Extract video ID from various YouTube URL formats.

    Supports:
    - Standard: https://www.youtube.com/watch?v=VIDEO_ID
    - Short: https://youtu.be/VIDEO_ID
    - Embed: https://www.youtube.com/embed/VIDEO_ID
    - V-path: https://www.youtube.com/v/VIDEO_ID
    - Shorts: https://www.youtube.com/shorts/VIDEO_ID

    Args:
        url: The YouTube URL string.

    Returns:
        The 11-character video ID if found, else None.
    """
    # Common patterns for YouTube Video IDs (11 chars, alphanumeric + _ -)
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
        r"youtu\.be\/([0-9A-Za-z_-]{11})",
        r"embed\/([0-9A-Za-z_-]{11})",
        r"shorts\/([0-9A-Za-z_-]{11})",
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

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
    try:
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)

        if "list" in query_params:
            return query_params["list"][0]
    except Exception:
        # Fail gracefully on malformed URLs
        pass

    return None


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
        ValueError: If URL is not a valid YouTube URL (neither video nor playlist)
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL must be a non-empty string")

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

    raise ValueError(f"Invalid YouTube URL: {url}")
