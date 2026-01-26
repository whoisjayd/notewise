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
    Extract all video IDs from a YouTube playlist.
    
    Args:
        playlist_id: YouTube playlist ID
        
    Returns:
        List of video IDs
        
    Raises:
        PlaylistError: If playlist cannot be accessed
    """
    try:
        playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
        playlist = Playlist(playlist_url)
        
        # Access playlist title to trigger loading
        try:
            title = playlist.title
            console.print(f"[cyan]Found playlist:[/cyan] {title}")
        except Exception:
            title = "Unknown Playlist"
            console.print(f"[yellow]Warning: Could not fetch playlist title[/yellow]")
        
        video_ids = []
        
        # Extract video IDs from URLs
        for url in playlist.video_urls:
            # Extract ID from URL
            if "v=" in url:
                video_id = url.split("v=")[1].split("&")[0]
                video_ids.append(video_id)
        
        if not video_ids:
            raise PlaylistError(f"No videos found in playlist: {playlist_id}")
        
        console.print(f"[green]Found {len(video_ids)} videos in playlist[/green]")
        return video_ids
        
    except Exception as e:
        logger.error(f"Failed to extract playlist videos: {e}")
        raise PlaylistError(f"Could not access playlist {playlist_id}: {str(e)}")
