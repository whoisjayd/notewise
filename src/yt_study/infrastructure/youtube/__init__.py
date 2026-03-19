"""YouTube infrastructure adapters."""

from yt_study.domain.youtube import ParsedURL, VideoMetadata, VideoTranscript
from yt_study.infrastructure.youtube.metadata import get_video_metadata
from yt_study.infrastructure.youtube.parser import parse_youtube_url
from yt_study.infrastructure.youtube.playlist import extract_playlist_videos
from yt_study.infrastructure.youtube.transcript import fetch_transcript


__all__ = [
    "VideoMetadata",
    "get_video_metadata",
    "VideoTranscript",
    "fetch_transcript",
    "extract_playlist_videos",
    "parse_youtube_url",
    "ParsedURL",
]
