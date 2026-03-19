"""Video metadata extraction using the native extractor."""

import structlog

from yt_study.domain.youtube import VideoChapter, VideoMetadata
from yt_study.errors import (
    ExtractionError,
    VideoUnavailableError,
    raise_if_video_unavailable,
)
from yt_study.infrastructure.youtube._constants import (
    YOUTUBE_PLAYLIST_URL,
    YOUTUBE_WATCH_URL,
)
from yt_study.infrastructure.youtube.availability import (
    raise_for_playlist_availability as _check_playlist_availability,
)
from yt_study.infrastructure.youtube.availability import (
    raise_for_video_availability as _check_video_availability,
)
from yt_study.infrastructure.youtube.extractor import (
    AsyncYouTubeExtractorClient,
    YouTubeExtractorConfig,
)


logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


async def get_video_metadata(
    video_id: str,
    cookie_file: str | None = None,
) -> VideoMetadata:
    """Fetch title, duration, and chapters in a single extractor client call.

    Replaces three separate get_video_title / get_video_duration / get_video_chapters
    calls with one page scrape, reducing network round-trips by 2/3 per video.

    Note: This function performs blocking network I/O.
    """
    try:
        client = _client(cookie_file)
        url = _video_url(video_id)
        # Re-use async interface for a single page scrape
        video_data = await client.video_metadata_full(url)

        data_fields = {
            "duration": video_data.get("duration"),
            "title": video_data.get("title"),
            "availability": video_data.get("availability"),
        }
        _check_video_availability(data_fields)

        title = str(video_data.get("title") or video_id)
        duration = int(video_data.get("duration") or 0)

        raw_chapters = video_data.get("chapters") or []
        chapters: list[VideoChapter] = []
        for i, ch in enumerate(raw_chapters, start=1):
            start_time = ch.get("start_time") or 0
            end_time = ch.get("end_time")
            ch_title = ch.get("title") or f"Chapter {i}"
            chapters.append(
                VideoChapter(
                    title=str(ch_title),
                    start_seconds=int(start_time),
                    end_seconds=int(end_time) if end_time is not None else None,
                )
            )

        return VideoMetadata(
            video_id=video_id,
            title=title,
            duration=duration,
            chapters=chapters,
        )
    except VideoUnavailableError:
        raise
    except ExtractionError as e:
        raise_if_video_unavailable(str(e), video_id=video_id)
        logger.debug("extractor.chapters_failed", video_id=video_id, error=str(e))
        return VideoMetadata(video_id=video_id, title=video_id, duration=0, chapters=[])
    except Exception as e:
        raise_if_video_unavailable(str(e), video_id=video_id)
        logger.warning("metadata.fetch_failed", video_id=video_id, error=str(e))
        return VideoMetadata(video_id=video_id, title=video_id, duration=0, chapters=[])


def _client(
    cookie_file: str | None = None,
) -> AsyncYouTubeExtractorClient:
    """Build a short-lived extractor client instance."""
    return AsyncYouTubeExtractorClient(
        YouTubeExtractorConfig(
            cookie_file=cookie_file,
        )
    )


def _video_url(video_id: str) -> str:
    return YOUTUBE_WATCH_URL.format(video_id=video_id)


def _playlist_url(playlist_id: str) -> str:
    return YOUTUBE_PLAYLIST_URL.format(playlist_id=playlist_id)


async def get_video_chapters(
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
        result = await _client(cookie_file).chapters(_video_url(video_id))
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
    except VideoUnavailableError:
        raise
    except ExtractionError as e:
        raise_if_video_unavailable(str(e))
        logger.debug(f"Could not fetch chapters for {video_id}: {e}")
    except Exception as e:
        raise_if_video_unavailable(str(e))
        logger.debug(f"Could not fetch chapters for {video_id}: {e}")

    return []


async def get_video_title(
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
        result = await _client(cookie_file).metadata(_video_url(video_id))
        data = result.get("data") or {}
        _check_video_availability(data)
        title = result.get("title") or data.get("title")
        if title:
            return str(title)
    except VideoUnavailableError:
        raise
    except ExtractionError as e:
        raise_if_video_unavailable(str(e))
        logger.warning(f"Could not fetch title for {video_id}: {e}")
    except Exception as e:
        raise_if_video_unavailable(str(e))
        logger.warning(f"Could not fetch title for {video_id}: {e}")

    # Fallback to video ID
    return video_id


async def get_video_duration(
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
        result = await _client(cookie_file).metadata(_video_url(video_id))
        data = result.get("data") or {}
        _check_video_availability(data)
        duration = data.get("duration")
        return int(duration) if duration is not None else 0
    except VideoUnavailableError:
        raise
    except ExtractionError as e:
        raise_if_video_unavailable(str(e))
        logger.warning(f"Could not fetch duration for {video_id}: {e}")
    except Exception as e:
        raise_if_video_unavailable(str(e))
        logger.warning(f"Could not fetch duration for {video_id}: {e}")
    return 0


async def get_playlist_info(
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
        result = await _client(cookie_file).metadata(_playlist_url(playlist_id))
        data = result.get("data") or {}
        _check_playlist_availability(data)
        title = result.get("title") or data.get("title") or f"playlist_{playlist_id}"
        count = data.get("playlist_count")
        return str(title), int(count) if count is not None else 0
    except VideoUnavailableError:
        raise
    except Exception as e:
        raise_if_video_unavailable(str(e))
        logger.warning(f"Could not fetch playlist info: {e}")
    return f"playlist_{playlist_id}", 0
