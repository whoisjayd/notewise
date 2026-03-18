"""Video metadata extraction using the native extractor."""

import logging
from dataclasses import dataclass

from .extractor.client import ExtractorClient, ExtractorConfig, ExtractorError


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


def _client(
    cookie_file: str | None = None,
) -> ExtractorClient:
    """Build a short-lived extractor client instance."""
    return ExtractorClient(
        ExtractorConfig(
            cookie_file=cookie_file,
        )
    )


def _video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _playlist_url(playlist_id: str) -> str:
    return f"https://www.youtube.com/playlist?list={playlist_id}"


def get_video_chapters(
    video_id: str,
    cookie_file: str | None = None,
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
        result = _client(cookie_file).chapters(_video_url(video_id))
        chapter_data = result.get("chapters") or []
        chapters: list[VideoChapter] = []
        for i, chapter in enumerate(chapter_data, start=1):
            start_time = chapter.get("start_time") or 0
            end_time = chapter.get("end_time")
            title = chapter.get("title") or f"Chapter {i}"
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
    except ExtractorError as e:
        _raise_if_public_access_required(str(e))
        logger.debug(f"Could not fetch chapters for {video_id}: {e}")
    except Exception as e:
        _raise_if_public_access_required(str(e))
        logger.debug(f"Could not fetch chapters for {video_id}: {e}")

    return []


def get_video_title(
    video_id: str,
    cookie_file: str | None = None,
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
        result = _client(cookie_file).metadata(_video_url(video_id))
        data = result.get("data") or {}
        _raise_if_video_data_requires_public_access(data)
        title = result.get("title") or data.get("title")
        if title:
            return str(title)
    except PublicAccessRequiredError:
        raise
    except ExtractorError as e:
        _raise_if_public_access_required(str(e))
        logger.warning(f"Could not fetch title for {video_id}: {e}")
    except Exception as e:
        _raise_if_public_access_required(str(e))
        logger.warning(f"Could not fetch title for {video_id}: {e}")

    # Fallback to video ID
    return video_id


def get_video_duration(
    video_id: str,
    cookie_file: str | None = None,
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
        result = _client(cookie_file).metadata(_video_url(video_id))
        data = result.get("data") or {}
        _raise_if_video_data_requires_public_access(data)
        duration = data.get("duration")
        return int(duration) if duration is not None else 0
    except PublicAccessRequiredError:
        raise
    except ExtractorError as e:
        _raise_if_public_access_required(str(e))
        logger.warning(f"Could not fetch duration for {video_id}: {e}")
    except Exception as e:
        _raise_if_public_access_required(str(e))
        logger.warning(f"Could not fetch duration for {video_id}: {e}")
    return 0


def get_playlist_info(
    playlist_id: str,
    cookie_file: str | None = None,
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
        result = _client(cookie_file).metadata(_playlist_url(playlist_id))
        data = result.get("data") or {}
        _raise_if_playlist_data_requires_public_access(data)
        title = result.get("title") or data.get("title") or f"playlist_{playlist_id}"
        count = data.get("playlist_count")
        return str(title), int(count) if count is not None else 0
    except PublicAccessRequiredError:
        raise
    except Exception as e:
        _raise_if_public_access_required(str(e))
        logger.warning(f"Could not fetch playlist info: {e}")
    return f"playlist_{playlist_id}", 0


def _raise_if_video_data_requires_public_access(data: dict[str, object]) -> None:
    availability = str(data.get("availability") or "").lower()
    if availability == "private":
        raise PublicAccessRequiredError(
            "Private YouTube videos are not supported. "
            "Make the video unlisted or public to process it."
        )
    if availability in {"login_required", "unavailable"}:
        raise PublicAccessRequiredError(
            "Sign-in-only YouTube videos are not supported. "
            "Use a public or unlisted video to process it."
        )
    if availability == "age_restricted":
        raise PublicAccessRequiredError(
            "Age-restricted YouTube videos are not supported. "
            "Use a public or unlisted video without sign-in requirements to process it."
        )


def _raise_if_playlist_data_requires_public_access(data: dict[str, object]) -> None:
    availability = str(data.get("availability") or "").lower()
    if availability == "private":
        raise PublicAccessRequiredError(
            "Private YouTube playlists are not supported. "
            "Make the playlist unlisted or public to process it."
        )


def _raise_if_public_access_required(error_text: str) -> None:
    """Raise a user-facing access error when the text indicates restricted access."""
    normalized_text = error_text.lower()

    if (
        "private video" in normalized_text
        or "this is a private video" in normalized_text
    ):
        raise PublicAccessRequiredError(
            "Private YouTube videos are not supported. "
            "Make the video unlisted or public to process it."
        )
    if "members-only video" in normalized_text or "members only" in normalized_text:
        raise PublicAccessRequiredError(
            "Members-only YouTube videos are not supported. "
            "Use a public or unlisted video to process it."
        )
    if "age restricted" in normalized_text or "without logging in" in normalized_text:
        raise PublicAccessRequiredError(
            "Age-restricted YouTube videos are not supported. "
            "Use a public or unlisted video without sign-in requirements to process it."
        )
    if (
        "requires login to view" in normalized_text
        or "please sign in" in normalized_text
        or "sign in to confirm your age" in normalized_text
    ):
        raise PublicAccessRequiredError(
            "Sign-in-only YouTube videos are not supported. "
            "Use a public or unlisted video to process it."
        )
