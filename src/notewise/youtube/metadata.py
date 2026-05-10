"""Video and playlist metadata extraction using the native extractor."""

from __future__ import annotations

import structlog

from notewise.domain.youtube import VideoChapter, VideoMetadata
from notewise.errors import (
    ExtractionError,
    PlaylistError,
    VideoUnavailableError,
    raise_if_video_unavailable,
)
from notewise.utils import coerce_int as _coerce_int
from notewise.youtube._availability import (
    raise_for_playlist_availability as _check_playlist_availability,
)
from notewise.youtube._availability import (
    raise_for_video_availability as _check_video_availability,
)
from notewise.youtube._constants import YOUTUBE_PLAYLIST_URL, YOUTUBE_WATCH_URL

from .extractor.async_client import AsyncYouTubeExtractorClient
from .extractor.client import YouTubeExtractorConfig


logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


async def get_video_metadata(
    video_id: str,
    cookie_file: str | None = None,
) -> VideoMetadata:
    """Fetch title, duration, and chapters for one video in a single call."""
    video_data = await get_video_details(video_id, cookie_file)
    title = str(video_data.get("title") or video_id)
    duration = _coerce_int(video_data.get("duration"))
    chapters = _map_video_chapters(_coerce_raw_chapters(video_data.get("chapters")))

    return VideoMetadata(
        video_id=video_id,
        title=title,
        duration=duration,
        chapters=chapters,
    )


async def get_video_details(
    video_id: str,
    cookie_file: str | None = None,
) -> dict[str, object]:
    """Fetch the full extractor payload for a single video."""
    try:
        client = _client(cookie_file)
        video_data = await client.video_metadata_full(_video_url(video_id))

        data_fields = {
            "duration": video_data.get("duration"),
            "title": video_data.get("title"),
            "availability": video_data.get("availability"),
        }
        _check_video_availability(data_fields)
        return video_data
    except VideoUnavailableError:
        raise
    except ExtractionError as error:
        raise_if_video_unavailable(str(error), video_id=video_id)
        logger.warning(
            "metadata.video_extraction_failed",
            video_id=video_id,
            error=str(error),
        )
        raise
    except Exception as error:
        raise_if_video_unavailable(str(error), video_id=video_id)
        logger.warning(
            "metadata.video_fetch_failed",
            video_id=video_id,
            error=str(error),
        )
        raise ExtractionError(
            f"Failed to fetch metadata for {video_id}: {error}",
            video_id=video_id,
        ) from error


def _map_video_chapters(raw_chapters: list[dict[str, object]]) -> list[VideoChapter]:
    """Normalize raw extractor chapter objects into domain models."""
    chapters: list[VideoChapter] = []
    for index, chapter in enumerate(raw_chapters, start=1):
        start_time = chapter.get("start_time") or 0
        end_time = chapter.get("end_time")
        title = chapter.get("title") or f"Chapter {index}"
        chapters.append(
            VideoChapter(
                title=str(title),
                start_seconds=_coerce_int(start_time),
                end_seconds=_coerce_int(end_time) if end_time is not None else None,
            )
        )
    return chapters


def _coerce_raw_chapters(value: object | None) -> list[dict[str, object]]:
    """Return only dict-like chapter payloads from the raw extractor value."""
    if not isinstance(value, list):
        return []

    chapters: list[dict[str, object]] = []
    for chapter in value:
        if not isinstance(chapter, dict):
            continue
        normalized: dict[str, object] = {}
        for key, item in chapter.items():
            if isinstance(key, str):
                normalized[key] = item
        chapters.append(normalized)
    return chapters


def _client(cookie_file: str | None = None) -> AsyncYouTubeExtractorClient:
    """Build a short-lived extractor client instance."""
    return AsyncYouTubeExtractorClient(YouTubeExtractorConfig(cookie_file=cookie_file))


def _video_url(video_id: str) -> str:
    return YOUTUBE_WATCH_URL.format(video_id=video_id)


def _playlist_url(playlist_id: str) -> str:
    return YOUTUBE_PLAYLIST_URL.format(playlist_id=playlist_id)


async def get_source_metadata(
    target: str,
    cookie_file: str | None = None,
) -> dict[str, object]:
    """Return the raw extractor metadata payload for a video or playlist target."""
    return await _client(cookie_file).metadata(target)


async def get_playlist_info(
    playlist_id: str,
    cookie_file: str | None = None,
) -> tuple[str, int]:
    """Get playlist title and video count."""
    try:
        result = await _client(cookie_file).metadata(_playlist_url(playlist_id))
        data = result.get("data") or {}
        _check_playlist_availability(data)
        title = result.get("title") or data.get("title") or f"playlist_{playlist_id}"
        count = data.get("playlist_count")
        return str(title), _coerce_int(count)
    except VideoUnavailableError:
        raise
    except ExtractionError as error:
        raise_if_video_unavailable(str(error))
        logger.warning("metadata.playlist_fetch_failed", error=str(error))
        raise PlaylistError(
            f"Could not access playlist {playlist_id}: {error}"
        ) from error
    except Exception as error:
        raise_if_video_unavailable(str(error))
        logger.warning("metadata.playlist_fetch_failed", error=str(error))
        raise PlaylistError(
            f"Could not access playlist {playlist_id}: {error}"
        ) from error
