"""Pipeline package for yt-study."""

from ._limiter import clear_youtube_limiters
from .core import CorePipeline, PipelineSharedState, dedupe_video_ids, run_pipeline
from .generation import StudyMaterialGenerator


Pipeline = CorePipeline


__all__ = [
    "Pipeline",
    "CorePipeline",
    "PipelineSharedState",
    "run_pipeline",
    "StudyMaterialGenerator",
    "clear_youtube_limiters",
    "dedupe_video_ids",
]
