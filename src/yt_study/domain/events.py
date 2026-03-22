"""Pipeline event types and event data objects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class EventType(Enum):
    """Event types emitted by the pipeline."""

    METADATA_START = "metadata_start"
    METADATA_FETCHED = "metadata_fetched"
    TRANSCRIPT_FETCHING = "transcript_fetching"
    TRANSCRIPT_FETCHED = "transcript_fetched"
    GENERATION_START = "generation_start"
    CHUNK_GENERATING = "chunk_generating"
    GENERATION_COMBINING = "generation_combining"
    CHAPTER_GENERATING = "chapter_generating"
    CHAPTER_CHUNK_GENERATING = "chapter_chunk_generating"
    CHAPTER_COMBINING = "chapter_combining"
    CHAPTER_COMPLETE = "chapter_complete"
    QUIZ_GENERATING = "quiz_generating"
    QUIZ_CHUNK_GENERATING = "quiz_chunk_generating"
    QUIZ_COMBINING = "quiz_combining"
    QUIZ_COMPLETE = "quiz_complete"
    GENERATION_COMPLETE = "generation_complete"
    VIDEO_SUCCESS = "video_success"
    VIDEO_SKIPPED = "video_skipped"
    VIDEO_FAILED = "video_failed"
    PIPELINE_START = "pipeline_start"
    PIPELINE_COMPLETE = "pipeline_complete"


@dataclass
class PipelineEvent:
    """Event emitted during pipeline execution."""

    event_type: EventType
    video_id: str
    title: str | None = None
    chapter_number: int | None = None
    total_chapters: int | None = None
    chunk_number: int | None = None
    total_chunks: int | None = None
    error: str | None = None
    output_path: Path | None = None
