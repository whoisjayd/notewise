"""Service layer — business logic orchestration for yt-study."""

from __future__ import annotations

from typing import Any


__all__ = [
    "Pipeline",
    "CorePipeline",
    "run_pipeline",
    "StudyMaterialGenerator",
    "clear_youtube_limiters",
]


def __getattr__(name: str) -> Any:
    """Load heavy service exports lazily to keep CLI import time low."""
    if name in {"Pipeline", "CorePipeline", "run_pipeline"}:
        from .pipeline import CorePipeline, run_pipeline

        if name == "run_pipeline":
            return run_pipeline
        return CorePipeline

    if name == "StudyMaterialGenerator":
        from .generation import StudyMaterialGenerator

        return StudyMaterialGenerator

    if name == "clear_youtube_limiters":
        from ._limiter import clear_youtube_limiters

        return clear_youtube_limiters

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
