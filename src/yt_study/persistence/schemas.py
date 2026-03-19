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
