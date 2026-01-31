"""Playlist video extraction using pytubefix."""

import asyncio
import logging

from pytubefix import Playlist
from rich.console import Console


console = Console()
logger = logging.getLogger(__name__)


class PlaylistError(Exception):
    """Exception raised for playlist-related errors."""

    pass


async def extract_playlist_videos(playlist_id: str) -> list[str]:
    """
    Extract all video IDs from a YouTube playlist with retry logic.

    This function handles the blocking network calls of pytubefix by offloading
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
            # Wrap blocking pytubefix logic in a thread
            video_ids = await asyncio.to_thread(_extract_sync, playlist_id, attempt)

            if not video_ids:
                # Should have been raised in _extract_sync if empty, but double check
                raise ValueError(
                    f"No videos found in playlist (Attempt {attempt + 1}/{max_retries})"
                )

            logger.info(f"Found {len(video_ids)} videos in playlist")
            return video_ids

        except Exception as e:
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


def _extract_sync(playlist_id: str, attempt: int) -> list[str]:
    """Blocking helper to extract videos using pytubefix."""
    playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
    playlist = Playlist(playlist_url)

    # Access playlist title to trigger loading
    try:
        title = playlist.title
        if attempt == 0:
            logger.info(f"Found playlist: {title}")
    except Exception:
        # Title fetch might fail but video extraction might still work
        logger.warning(f"Could not fetch playlist title on attempt {attempt + 1}")

    video_ids = []

    # Extract video IDs from URLs (waits for internal generator)
    # This loop triggers network requests
    for url in playlist.video_urls:
        if "v=" in url:
            try:
                # Robust ID extraction
                video_id = url.split("v=")[1].split("&")[0]
                video_ids.append(video_id)
            except IndexError:
                continue

    if not video_ids:
        raise ValueError("No videos found in playlist")

    return video_ids
