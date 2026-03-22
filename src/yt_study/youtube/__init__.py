"""YouTube adapters and extractors."""

from yt_study.domain.youtube import ParsedURL, VideoMetadata, VideoTranscript

from .metadata import get_video_metadata
from .parser import parse_youtube_url
from .playlist import extract_playlist_videos
from .transcript import fetch_transcript


__all__ = [
    "VideoMetadata",
    "get_video_metadata",
    "VideoTranscript",
    "fetch_transcript",
    "extract_playlist_videos",
    "parse_youtube_url",
    "ParsedURL",
]
