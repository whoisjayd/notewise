"""Core pipeline module - zero UI dependencies.

This module provides the core pipeline functionality that can be used
by any frontend (CLI, web API, GUI, etc.) without UI dependencies.

Usage:
    >>> from yt_study.core import CorePipeline, EventType
    >>>
    >>> pipeline = CorePipeline(model="gemini-1.5-flash")
    >>>
    >>> def on_progress(event):
    ...     if event.event_type == EventType.VIDEO_SUCCESS:
    ...         print(f"Done: {event.title}")
    >>>
    >>> result = await pipeline.run(["VIDEO_ID"], on_event=on_progress)
"""

# Keep backward compatibility with old PipelineOrchestrator
from .orchestrator import PipelineOrchestrator
from .pipeline import (
    CorePipeline,
    EventType,
    PipelineEvent,
    PipelineResult,
    run_pipeline,
    sanitize_filename,
)


__all__ = [
    # New core API
    "CorePipeline",
    "EventType",
    "PipelineEvent",
    "PipelineResult",
    "run_pipeline",
    "sanitize_filename",
    # Legacy (deprecated, for backward compatibility)
    "PipelineOrchestrator",
]
