"""Playlist video extraction using pytubefix."""

import logging
from typing import List

from pytubefix import Playlist
from rich.console import Console

console = Console()
logger = logging.getLogger(__name__)


class PlaylistError(Exception):
    """Exception raised for playlist-related errors."""
    pass


async def extract_playlist_videos(playlist_id: str) -> List[str]:
    """
    Extract all video IDs from a YouTube playlist with retry logic.
    """
    import asyncio
    
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
            playlist = Playlist(playlist_url)
            
            # Access playlist title to trigger loading
            try:
                title = playlist.title
                if attempt == 0:
                     logger.info(f"Found playlist: {title}")
            except Exception:
                title = "Unknown Playlist"
                logger.warning(f"Could not fetch playlist title on attempt {attempt+1}")
            
            video_ids = []
            
            # Extract video IDs from URLs (waits for internal generator)
            for url in playlist.video_urls:
                if "v=" in url:
                    video_id = url.split("v=")[1].split("&")[0]
                    video_ids.append(video_id)
            
            if not video_ids:
                # If pytubefix found no videos, it might be a transient page load error
                # unless checking logic confirms it's empty.
                # We raise to trigger retry.
                raise ValueError(f"No videos found in playlist (Attempt {attempt+1}/{max_retries})")
            
            logger.info(f"Found {len(video_ids)} videos in playlist")
            return video_ids
            
        except Exception as e:
            last_error = e
            logger.warning(f"Playlist extraction attempt {attempt+1} failed: {e}")
            if attempt < max_retries - 1:
                logger.warning(f"Failed to extract playlist videos, retrying ({attempt+1}/{max_retries})...")
                await asyncio.sleep(2) # Wait before retry
    
    logger.error(f"Failed to extract playlist videos after {max_retries} attempts: {last_error}")
    raise PlaylistError(f"Could not access playlist {playlist_id}: {str(last_error)}")
