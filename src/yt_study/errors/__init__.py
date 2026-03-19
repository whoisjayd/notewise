"""Centralized exceptions and error utilities for yt-study."""

from .exceptions import (
    ConfigurationError,
    ExtractionError,
    IPBlockError,
    LLMError,
    LLMGenerationError,
    PersistenceError,
    PlaylistError,
    TranscriptUnavailableError,
    UserVisibleCliError,
    ValidationError,
    VideoUnavailableError,
    YouTubeError,
    YtStudyError,
    raise_if_video_unavailable,
)
from .formatting import format_user_error


__all__ = [
    "YtStudyError",
    "ConfigurationError",
    "ValidationError",
    "UserVisibleCliError",
    "YouTubeError",
    "VideoUnavailableError",
    "TranscriptUnavailableError",
    "IPBlockError",
    "PlaylistError",
    "ExtractionError",
    "LLMError",
    "LLMGenerationError",
    "PersistenceError",
    "raise_if_video_unavailable",
    "format_user_error",
]
