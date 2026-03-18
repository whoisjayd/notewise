"""Playlist video extraction using the native extractor."""

import asyncio
import logging

from .extractor.client import ExtractorClient, ExtractorConfig, ExtractorError
from .metadata import PublicAccessRequiredError
from .parser import extract_video_id


logger = logging.getLogger(__name__)


class PlaylistError(Exception):
    """Exception raised for playlist-related errors."""

    pass


def _raise_if_public_access_required(error: Exception) -> None:
    """Convert private or sign-in-only playlist failures into user-facing errors."""
    error_text = str(error).lower()

    if "private playlist" in error_text or "this playlist is private" in error_text:
        raise PublicAccessRequiredError(
            "Private YouTube playlists are not supported. "
            "Make the playlist unlisted or public to process it."
        ) from error

    if (
        "requires login to view" in error_text
        or "please sign in" in error_text
        or "sign-in" in error_text
        or "sign in" in error_text
    ):
        raise PublicAccessRequiredError(
            "Sign-in-only YouTube playlists are not supported. "
            "Use a public or unlisted playlist to process it."
        ) from error


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
    max_retries = 3
    last_error = None

    for attempt in range(max_retries):
        try:
            # Wrap blocking native extraction logic in a thread
            video_ids = await asyncio.to_thread(
                _extract_sync,
                playlist_id,
                attempt,
                cookie_file,
            )

            if not video_ids:
                # Should have been raised in _extract_sync if empty, but double check
                raise ValueError(
                    f"No videos found in playlist (Attempt {attempt + 1}/{max_retries})"
                )

            logger.info(f"Found {len(video_ids)} videos in playlist")
            return video_ids

        except PublicAccessRequiredError:
            raise
        except Exception as e:
            _raise_if_public_access_required(e)
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


def _extract_sync(
    playlist_id: str,
    attempt: int,
    cookie_file: str | None,
) -> list[str]:
    """Blocking helper to extract playlist videos with the native extractor."""
    playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
    client = ExtractorClient(
        ExtractorConfig(
            cookie_file=cookie_file,
        )
    )

    try:
        payload = client.playlist(playlist_url)
    except ExtractorError as error:
        _raise_if_public_access_required(error)
        raise

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
        raise ValueError("No videos found in playlist")

    return video_ids
