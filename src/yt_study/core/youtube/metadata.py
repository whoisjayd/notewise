"""Video metadata extraction using pytubefix."""

import json
import logging
from dataclasses import dataclass
from typing import Any

from pytubefix import Playlist, YouTube
from pytubefix import exceptions as pytubefix_exceptions


logger = logging.getLogger(__name__)


class PublicAccessRequiredError(Exception):
    """Raised when a video requires sign-in-only access that yt-study cannot use."""

    pass


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


def get_video_chapters(
    video_id: str,
) -> list[VideoChapter]:
    """
    Get chapters from a YouTube video.

    Note: This function performs blocking network I/O.

    Args:
        video_id: YouTube video ID.

    Returns:
        List of VideoChapter objects, empty if no chapters found.
    """
    try:
        yt = _get_available_video(video_id)

        # Read the chapter property once because pytubefix properties can
        # trigger network calls on access.
        try:
            chapter_data = yt.chapters
        except AttributeError:
            chapter_data = None

        if chapter_data:
            chapters: list[VideoChapter] = []

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
    except PublicAccessRequiredError:
        raise
    except Exception as e:
        _raise_if_public_access_required(e)
        logger.debug(f"Could not fetch chapters for {video_id}: {e}")

    return []


def get_video_title(
    video_id: str,
) -> str:
    """
    Get the title of a YouTube video.

    Note: This function performs blocking network I/O.

    Args:
        video_id: YouTube video ID.

    Returns:
        Video title, or video ID if title cannot be fetched.
    """
    try:
        yt = _get_available_video(video_id)
        title = yt.title

        if title:
            return str(title)
    except PublicAccessRequiredError:
        raise
    except Exception as e:
        _raise_if_public_access_required(e)
        logger.warning(f"Could not fetch title for {video_id}: {e}")

    # Fallback to video ID
    return video_id


def get_video_duration(
    video_id: str,
) -> int:
    """
    Get video duration in seconds.

    Note: This function performs blocking network I/O.

    Args:
        video_id: YouTube video ID.

    Returns:
        Duration in seconds, 0 if cannot be fetched.
    """
    try:
        yt = _get_available_video(video_id)
        return int(yt.length)
    except PublicAccessRequiredError:
        raise
    except Exception as e:
        _raise_if_public_access_required(e)
        logger.warning(f"Could not fetch duration for {video_id}: {e}")
    return 0


def get_playlist_info(
    playlist_id: str,
) -> tuple[str, int]:
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
        try:
            title = playlist.title
        except Exception:
            title = f"playlist_{playlist_id}"

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


def _get_available_video(video_id: str) -> YouTube:
    """Build a pytubefix YouTube object and fail fast on restricted access."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    yt = YouTube(url)
    try:
        yt.check_availability()
    except Exception as error:
        _raise_if_playability_status_requires_public_access(yt, error)
        _raise_if_public_access_required(error)
        raise
    return yt


def _raise_if_public_access_required(error: Exception) -> None:
    """Convert private or sign-in-only pytubefix errors into user-facing failures."""
    if isinstance(error, pytubefix_exceptions.VideoPrivate):
        raise PublicAccessRequiredError(
            "Private YouTube videos are not supported. "
            "Make the video unlisted or public to process it."
        ) from error

    if isinstance(error, pytubefix_exceptions.MembersOnly):
        raise PublicAccessRequiredError(
            "Members-only YouTube videos are not supported. "
            "Use a public or unlisted video to process it."
        ) from error

    if isinstance(
        error,
        (
            pytubefix_exceptions.AgeRestrictedError,
            pytubefix_exceptions.AgeCheckRequiredError,
            pytubefix_exceptions.AgeCheckRequiredAccountError,
        ),
    ):
        raise PublicAccessRequiredError(
            "Age-restricted YouTube videos are not supported. "
            "Use a public or unlisted video without sign-in requirements to process it."
        ) from error

    _raise_from_public_access_text(str(error), error)


def _raise_if_playability_status_requires_public_access(
    yt: YouTube, error: Exception
) -> None:
    """Inspect pytubefix playability metadata for private/sign-in-only videos."""
    try:
        playability_status = (yt.vid_info or {}).get("playabilityStatus", {})
        status_text = json.dumps(playability_status)
    except Exception:
        return

    _raise_from_public_access_text(status_text, error)


def _raise_from_public_access_text(error_text: str, cause: Exception) -> None:
    """Raise a user-facing access error when the text indicates restricted access."""
    normalized_text = error_text.lower()

    if (
        "private video" in normalized_text
        or "this is a private video" in normalized_text
    ):
        raise PublicAccessRequiredError(
            "Private YouTube videos are not supported. "
            "Make the video unlisted or public to process it."
        ) from cause
    if "members-only video" in normalized_text or "members only" in normalized_text:
        raise PublicAccessRequiredError(
            "Members-only YouTube videos are not supported. "
            "Use a public or unlisted video to process it."
        ) from cause
    if "age restricted" in normalized_text or "without logging in" in normalized_text:
        raise PublicAccessRequiredError(
            "Age-restricted YouTube videos are not supported. "
            "Use a public or unlisted video without sign-in requirements to process it."
        ) from cause
    if (
        "requires login to view" in normalized_text
        or "please sign in" in normalized_text
        or "sign in to confirm your age" in normalized_text
    ):
        raise PublicAccessRequiredError(
            "Sign-in-only YouTube videos are not supported. "
            "Use a public or unlisted video to process it."
        ) from cause
