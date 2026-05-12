"""YouTube adapters and extractors."""

from notewise.domain.youtube import ParsedURL, VideoMetadata, VideoTranscript

from .metadata import get_video_metadata
from .parser import parse_youtube_url
from .playlist import extract_playlist_videos
from .transcript import fetch_transcript


__all__ = [
    "ParsedURL",
    "VideoMetadata",
    "VideoTranscript",
    "extract_playlist_videos",
    "fetch_transcript",
    "get_video_metadata",
    "parse_youtube_url",
]
