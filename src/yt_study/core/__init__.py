"""Core pipeline module - zero UI dependencies.

This module provides the core pipeline functionality that can be used
by any frontend (CLI, web API, GUI, etc.) without any UI dependencies.

Usage:
    >>> from yt_study.core import CorePipeline, EventType
    >>>
    >>> pipeline = CorePipeline(model="gemini/gemini-2.5-flash")
    >>>
    >>> def on_progress(event):
    ...     if event.event_type == EventType.VIDEO_SUCCESS:
    ...         print(f"Done: {event.title}")
    >>>
    >>> result = await pipeline.run(["VIDEO_ID"], on_event=on_progress)
"""

from .pipeline import (
    CorePipeline,
    EventType,
    PipelineEvent,
    PipelineResult,
    run_pipeline,
    sanitize_filename,
)


__all__ = [
    "CorePipeline",
    "EventType",
    "PipelineEvent",
    "PipelineResult",
    "run_pipeline",
    "sanitize_filename",
]
