"""YouTube URL parser for video and playlist detection."""

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, urlparse


@dataclass
class ParsedURL:
    """Parsed YouTube URL information."""
    
    url_type: str  # 'video' or 'playlist'
    video_id: Optional[str] = None
    playlist_id: Optional[str] = None
    

def extract_video_id(url: str) -> Optional[str]:
    """
    Extract video ID from various YouTube URL formats.
    
    Supports:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/embed/VIDEO_ID
    - https://www.youtube.com/v/VIDEO_ID
    """
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'youtu\.be\/([0-9A-Za-z_-]{11})',
        r'embed\/([0-9A-Za-z_-]{11})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None


def extract_playlist_id(url: str) -> Optional[str]:
    """
    Extract playlist ID from YouTube playlist URL.
    
    Supports:
    - https://www.youtube.com/playlist?list=PLAYLIST_ID
    - https://www.youtube.com/watch?v=VIDEO_ID&list=PLAYLIST_ ID
    """
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    
    if 'list' in query_params:
        return query_params['list'][0]
    
    return None


def parse_youtube_url(url: str) -> ParsedURL:
    """
    Parse a YouTube URL and determine if it's a video or playlist.
    
    Args:
        url: YouTube URL (video or playlist)
        
    Returns:
        ParsedURL object with url_type and relevant IDs
        
    Raises:
        ValueError: If URL is not a valid YouTube URL
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL must be a non-empty string")
    
    # Check for playlist
    playlist_id = extract_playlist_id(url)
    if playlist_id:
        # It's a playlist URL
        video_id = extract_video_id(url)  # Might have both
        return ParsedURL(
            url_type='playlist',
            playlist_id=playlist_id,
            video_id=video_id  # Optional, for playlist starting point
        )
    
    # Check for video
    video_id = extract_video_id(url)
    if video_id:
        return ParsedURL(
            url_type='video',
            video_id=video_id
        )
    
    raise ValueError(f"Invalid YouTube URL: {url}")
