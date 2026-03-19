"""Pure domain objects for yt-study — no infrastructure dependencies."""

from .events import EventType, PipelineEvent
from .results import PipelineMetrics, PipelineResult
from .youtube import (
    ParsedURL,
    TranscriptSegment,
    VideoChapter,
    VideoMetadata,
    VideoTranscript,
)


__all__ = [
    "EventType",
    "PipelineEvent",
    "PipelineMetrics",
    "PipelineResult",
    "VideoChapter",
    "TranscriptSegment",
    "VideoTranscript",
    "VideoMetadata",
    "ParsedURL",
]
