"""Video metadata extraction using pytubefix."""

import logging
from dataclasses import dataclass
from typing import Optional

from pytubefix import YouTube
from rich.console import Console

console = Console()
logger = logging.getLogger(__name__)


@dataclass
class VideoChapter:
    """A video chapter with title and time range."""
    
    title: str
    start_seconds: int
    end_seconds: Optional[int] = None


def get_video_chapters(video_id: str) -> list[VideoChapter]:
    """
    Get chapters from a YouTube video.
    
    Args:
        video_id: YouTube video ID
        
    Returns:
        List of VideoChapter objects, empty if no chapters
    """
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        yt = YouTube(url)
        
        # Access chapters if available
        if hasattr(yt, 'chapters') and yt.chapters:
            chapters = []
            chapter_data = yt.chapters
            
            for i, chapter in enumerate(chapter_data):
                # Handle pytubefix chapter object structure
                # Sometimes it's a dict, sometimes an object
                if isinstance(chapter, dict):
                    start_time = chapter.get('start_seconds', 0)
                    title = chapter.get('title', f'Chapter {i+1}')
                else:
                    start_time = getattr(chapter, 'start_seconds', 0)
                    title = getattr(chapter, 'title', f'Chapter {i+1}')
                
                # Calculate end time (start of next chapter or None for last)
                end_time = None
                if i < len(chapter_data) - 1:
                    next_chapter = chapter_data[i + 1]
                    if isinstance(next_chapter, dict):
                        end_time = next_chapter.get('start_seconds')
                    else:
                        end_time = getattr(next_chapter, 'start_seconds', None)
                
                chapters.append(VideoChapter(
                    title=title,
                    start_seconds=start_time,
                    end_seconds=end_time
                ))
            
            return chapters
            
    except Exception as e:
        logger.debug(f"Could not fetch chapters for {video_id}: {e}")
    
    return []


def get_video_title(video_id: str) -> str:
    """
    Get the title of a YouTube video.
    
    Args:
        video_id: YouTube video ID
        
    Returns:
        Video title, or video ID if title cannot be fetched
    """
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        yt = YouTube(url)
        title = yt.title
        
        if title:
            return title
        
    except Exception as e:
        logger.warning(f"Could not fetch title for {video_id}: {e}")
    
    # Fallback to video ID
    return video_id


def get_video_duration(video_id: str) -> int:
    """
    Get video duration in seconds.
    
    Args:
        video_id: YouTube video ID
        
    Returns:
        Duration in seconds, 0 if cannot be fetched
    """
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        yt = YouTube(url)
        return yt.length
    except Exception as e:
        logger.warning(f"Could not fetch duration for {video_id}: {e}")
        return 0


def get_playlist_info(playlist_id: str) -> tuple[str, int]:
    """
    Get playlist title and video count.
    
    Args:
        playlist_id: YouTube playlist ID
        
    Returns:
        Tuple of (title, video_count)
    """
    try:
        from pytubefix import Playlist
        url = f"https://www.youtube.com/playlist?list={playlist_id}"
        playlist = Playlist(url)
        
        title = playlist.title if hasattr(playlist, 'title') else f"playlist_{playlist_id}"
        return title, len(list(playlist.video_urls))
        
    except Exception as e:
        logger.warning(f"Could not fetch playlist info: {e}")
        return f"playlist_{playlist_id}", 0
