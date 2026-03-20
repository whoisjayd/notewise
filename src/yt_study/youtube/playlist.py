"""Playlist video extraction using the native extractor."""

import asyncio

import structlog

from yt_study._constants import PLAYLIST_MAX_RETRIES
from yt_study.errors import (
    ExtractionError,
    PlaylistError,
    VideoUnavailableError,
    raise_if_video_unavailable,
)
from yt_study.youtube._constants import YOUTUBE_PLAYLIST_URL
from yt_study.youtube.parser import extract_video_id

from .extractor.async_client import AsyncYouTubeExtractorClient
from .extractor.client import YouTubeExtractorConfig


logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


# PlaylistError is imported from yt_study.errors


async def extract_playlist_videos(
    playlist_id: str,
    cookie_file: str | None = None,
) -> list[str]:
    """
    Extract all video IDs from a YouTube playlist with retry logic.

    This function handles blocking network calls by offloading
    them to a separate thread, ensuring the asyncio event loop remains responsive.

    Args:
        playlist_id: YouTube playlist ID.

    Returns:
        List of video IDs.

    Raises:
        PlaylistError: If playlist cannot be accessed after retries.
    """
    max_retries = PLAYLIST_MAX_RETRIES
    last_error = None

    for attempt in range(max_retries):
        try:
            # Wrap blocking native extraction logic in a thread
            video_ids = await _extract_async(
                playlist_id,
                attempt,
                cookie_file,
            )

            if not video_ids:
                # Should have been raised in _extract_async if empty, but double check
                raise PlaylistError(
                    f"No videos found in playlist (Attempt {attempt + 1}/{max_retries})"
                )

            logger.info(f"Found {len(video_ids)} videos in playlist")
            return video_ids

        except VideoUnavailableError:
            raise
        except Exception as e:
            raise_if_video_unavailable(str(e))
            last_error = e

            logger.warning(f"Playlist extraction attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                wait_time = 2**attempt  # Exponential backoff
                logger.warning(f"Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)

    logger.error(
        f"Failed to extract playlist videos after {max_retries} attempts: {last_error}"
    )
    raise PlaylistError(f"Could not access playlist {playlist_id}: {str(last_error)}")


async def _extract_async(
    playlist_id: str,
    attempt: int,
    cookie_file: str | None,
) -> list[str]:
    """Async helper to extract playlist videos with the async extractor."""
    playlist_url = YOUTUBE_PLAYLIST_URL.format(playlist_id=playlist_id)
    client = AsyncYouTubeExtractorClient(
        YouTubeExtractorConfig(cookie_file=cookie_file)
    )

    try:
        payload = await client.playlist(playlist_url)
    except VideoUnavailableError:
        raise
    except ExtractionError as error:
        raise_if_video_unavailable(
            str(error)
        )  # raises VideoUnavailableError if access restricted
        raise PlaylistError(
            f"Could not access playlist {playlist_id}: {error}"
        ) from error

    playlist_meta = payload.get("playlist") or {}
    title = playlist_meta.get("title")
    if attempt == 0 and title:
        logger.info(f"Found playlist: {title}")

    video_ids = []

    entries = payload.get("entries") or []
    for entry in entries:
        url = entry.get("url") or ""
        video_id = entry.get("id") or extract_video_id(url)
        if video_id:
            video_ids.append(video_id)

    if not video_ids:
        raise PlaylistError("No videos found in playlist")

    return video_ids
