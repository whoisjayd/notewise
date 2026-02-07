"""Video metadata extraction using pytubefix."""

import logging
from dataclasses import dataclass
from typing import Any

from pytubefix import Playlist, YouTube
from rich.console import Console


console = Console()
logger = logging.getLogger(__name__)


@dataclass
class VideoChapter:
    """
    A video chapter with title and time range.

    Attributes:
        title: Chapter title.
        start_seconds: Start time in seconds.
        end_seconds: End time in seconds (None for the last chapter).
    """

    title: str
    start_seconds: int
    end_seconds: int | None = None


def get_video_chapters(video_id: str) -> list[VideoChapter]:
    """
    Get chapters from a YouTube video.

    Note: This function performs blocking network I/O.

    Args:
        video_id: YouTube video ID.

    Returns:
        List of VideoChapter objects, empty if no chapters found.
    """
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        yt = YouTube(url)

        # Access chapters if available
        # pytubefix properties trigger network calls
        if hasattr(yt, "chapters") and yt.chapters:
            chapters: list[VideoChapter] = []
            chapter_data = yt.chapters

            for i, chapter in enumerate(chapter_data):
                # Handle pytubefix chapter object structure (dict or object)
                start_time = _get_attr_or_item(chapter, "start_seconds", 0)
                title = _get_attr_or_item(chapter, "title", f"Chapter {i + 1}")

                # Calculate end time (start of next chapter or None for last)
                end_time = None
                if i < len(chapter_data) - 1:
                    next_chapter = chapter_data[i + 1]
                    end_time = _get_attr_or_item(next_chapter, "start_seconds", None)

                chapters.append(
                    VideoChapter(
                        title=str(title),
                        start_seconds=int(start_time),
                        end_seconds=int(end_time) if end_time is not None else None,
                    )
                )

            return chapters

    except Exception as e:
        logger.debug(f"Could not fetch chapters for {video_id}: {e}")

    return []


def get_video_title(video_id: str) -> str:
    """
    Get the title of a YouTube video.

    Note: This function performs blocking network I/O.

    Args:
        video_id: YouTube video ID.

    Returns:
        Video title, or video ID if title cannot be fetched.
    """
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        yt = YouTube(url)
        title = yt.title

        if title:
            return str(title)

    except Exception as e:
        logger.warning(f"Could not fetch title for {video_id}: {e}")

    # Fallback to video ID
    return video_id


def get_video_duration(video_id: str) -> int:
    """
    Get video duration in seconds.

    Note: This function performs blocking network I/O.

    Args:
        video_id: YouTube video ID.

    Returns:
        Duration in seconds, 0 if cannot be fetched.
    """
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        yt = YouTube(url)
        return int(yt.length)
    except Exception as e:
        logger.warning(f"Could not fetch duration for {video_id}: {e}")
        return 0


def get_playlist_info(playlist_id: str) -> tuple[str, int]:
    """
    Get playlist title and video count.

    Note: This function performs blocking network I/O.

    Args:
        playlist_id: YouTube playlist ID.

    Returns:
        Tuple of (title, video_count).
    """
    try:
        url = f"https://www.youtube.com/playlist?list={playlist_id}"
        playlist = Playlist(url)

        # Pytube's title might fail if playlist is private/invalid
        title = getattr(playlist, "title", f"playlist_{playlist_id}")

        # Getting length requires fetching the page
        # list(playlist.video_urls) is robust but slow for huge playlists
        # For metadata, it's acceptable.
        count = len(list(playlist.video_urls))

        return str(title), count

    except Exception as e:
        logger.warning(f"Could not fetch playlist info: {e}")
        return f"playlist_{playlist_id}", 0


def _get_attr_or_item(obj: Any, key: str, default: Any = None) -> Any:
    """Helper to get value from object attribute or dict key."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
