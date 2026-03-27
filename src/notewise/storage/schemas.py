"""Pydantic v2 schemas for persistence data crossing module boundaries.

These schemas are returned by DatabaseRepository methods. Business logic and
pipeline code work with these, never with ORM entities directly.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VideoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    duration: int
    cached_at: datetime | None = None


class TranscriptSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    video_id: str
    content: str
    language: str


class RunStatsSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    video_id: str
    tokens_used: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    model: str
    transcript_seconds: float = 0.0
    generation_seconds: float = 0.0
    timestamp: datetime


class ExportRecordSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    video_id: str
    format: str
    output_path: str
    timestamp: datetime


class RecentVideoSchema(BaseModel):
    id: str
    title: str
    duration: int
    cached_at: datetime | None = None
    last_run_at: datetime
    model: str
    cost_usd: float = 0.0
    tokens_used: int = 0


class ModelStatsSchema(BaseModel):
    model: str
    videos_processed: int
    run_count: int
    total_tokens_used: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cost_usd: float = 0.0
    total_transcript_seconds: float = 0.0
    total_generation_seconds: float = 0.0


class StatsSummarySchema(BaseModel):
    total_videos_processed: int = 0
    total_runs: int = 0
    total_tokens_used: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cost_usd: float = 0.0
    total_transcript_seconds: float = 0.0
    total_generation_seconds: float = 0.0
    models: list[ModelStatsSchema] = []


class CacheSummarySchema(BaseModel):
    total_videos: int = 0
    total_transcripts: int = 0
    total_runs: int = 0
    total_exports: int = 0
    oldest_cached_at: datetime | None = None
    newest_cached_at: datetime | None = None
