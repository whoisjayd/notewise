"""Thread-safe SQLite repository; singleton per database path."""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from .migrations import repair_runstats_schema
from .models import Base, ExportRecord, RunStatsRecord, TranscriptRecord, VideoRecord
from .schemas import ExportRecordSchema, RunStatsSchema, TranscriptSchema, VideoSchema


class DatabaseRepository:
    """Thread-safe SQLite repository; one instance per database file path."""

    _instances: ClassVar[dict[Path, DatabaseRepository]] = {}
    _instances_lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False},
            poolclass=NullPool,
        )
        self._write_lock = threading.Lock()
        Base.metadata.create_all(self._engine)
        with self._engine.begin() as conn:
            repair_runstats_schema(conn)

    # ── Singleton management ──────────────────────────────────────────────────

    @classmethod
    def get_instance(cls, db_path: Path) -> DatabaseRepository:
        """Return a singleton repository for the given database path."""
        resolved = db_path.expanduser().resolve()
        with cls._instances_lock:
            if resolved not in cls._instances:
                cls._instances[resolved] = cls(resolved)
            return cls._instances[resolved]

    @classmethod
    def close_instance(cls, db_path: Path) -> None:
        """Dispose and evict the singleton for the given path."""
        resolved = db_path.expanduser().resolve()
        with cls._instances_lock:
            instance = cls._instances.pop(resolved, None)
        if instance:
            instance.close()

    @classmethod
    def close_all_instances(cls) -> None:
        """Dispose and evict all singleton instances."""
        with cls._instances_lock:
            instances = list(cls._instances.values())
            cls._instances.clear()
        for inst in instances:
            inst.close()

    def close(self) -> None:
        """Close pooled DB resources for this repository."""
        self._engine.dispose()

    # ── Read operations ───────────────────────────────────────────────────────

    def has_video(self, video_id: str) -> bool:
        """Return True when cached metadata exists for the video."""
        with Session(self._engine) as session:
            return session.get(VideoRecord, video_id) is not None

    def get_video(self, video_id: str) -> VideoSchema | None:
        """Load cached video metadata if present."""
        with Session(self._engine) as session:
            record = session.get(VideoRecord, video_id)
            return VideoSchema.model_validate(record) if record else None

    async def aget_video(self, video_id: str) -> VideoSchema | None:
        """Async wrapper for get_video using the repository thread boundary."""
        return await asyncio.to_thread(self.get_video, video_id)

    def get_transcript(self, video_id: str) -> TranscriptSchema | None:
        """Load cached transcript row for a video."""
        with Session(self._engine) as session:
            record = session.execute(
                select(TranscriptRecord).where(TranscriptRecord.video_id == video_id)
            ).scalar_one_or_none()
            return TranscriptSchema.model_validate(record) if record else None

    def get_run_stats(self, video_id: str) -> list[RunStatsSchema]:
        """Load all run stats rows for a video."""
        with Session(self._engine) as session:
            records = (
                session.execute(
                    select(RunStatsRecord)
                    .where(RunStatsRecord.video_id == video_id)
                    .order_by(RunStatsRecord.timestamp, RunStatsRecord.id)
                )
                .scalars()
                .all()
            )
            return [RunStatsSchema.model_validate(r) for r in records]

    def get_export_records(self, video_id: str) -> list[ExportRecordSchema]:
        """Load all export records for a video."""
        with Session(self._engine) as session:
            records = (
                session.execute(
                    select(ExportRecord)
                    .where(ExportRecord.video_id == video_id)
                    .order_by(ExportRecord.timestamp, ExportRecord.id)
                )
                .scalars()
                .all()
            )
            return [ExportRecordSchema.model_validate(r) for r in records]

    # ── Write operations ──────────────────────────────────────────────────────

    def add_export_record(
        self,
        *,
        video_id: str,
        format: str,
        output_path: str,
    ) -> None:
        """Persist an export record for a video."""
        with self._write_lock, Session(self._engine) as session:
            session.add(
                ExportRecord(
                    video_id=video_id,
                    format=format,
                    output_path=output_path,
                    timestamp=datetime.now(timezone.utc),
                )
            )
            session.commit()

    def upsert_video_cache(
        self,
        *,
        video_id: str,
        title: str,
        duration: int,
        transcript_content: str,
        language: str,
        tokens_used: int,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0.0,
        model: str,
        transcript_seconds: float = 0.0,
        generation_seconds: float = 0.0,
    ) -> None:
        """Persist metadata, transcript, and run stats in one transaction."""
        with self._write_lock, Session(self._engine) as session:
            video = session.get(VideoRecord, video_id)
            if video is None:
                video = VideoRecord(id=video_id, title=title, duration=duration)
                session.add(video)
            else:
                video.title = title
                video.duration = duration

            transcript = session.execute(
                select(TranscriptRecord).where(TranscriptRecord.video_id == video_id)
            ).scalar_one_or_none()
            if transcript is None:
                session.add(
                    TranscriptRecord(
                        video_id=video_id,
                        content=transcript_content,
                        language=language,
                    )
                )
            else:
                transcript.content = transcript_content
                transcript.language = language

            session.add(
                RunStatsRecord(
                    video_id=video_id,
                    tokens_used=tokens_used,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=cost_usd,
                    model=model,
                    transcript_seconds=transcript_seconds,
                    generation_seconds=generation_seconds,
                    timestamp=datetime.now(timezone.utc),
                )
            )
            session.commit()

    async def aupsert_video_cache(
        self,
        *,
        video_id: str,
        title: str,
        duration: int,
        transcript_content: str,
        language: str,
        tokens_used: int,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0.0,
        model: str,
        transcript_seconds: float = 0.0,
        generation_seconds: float = 0.0,
    ) -> None:
        """Async wrapper for upsert_video_cache using the repository thread boundary."""
        await asyncio.to_thread(
            self.upsert_video_cache,
            video_id=video_id,
            title=title,
            duration=duration,
            transcript_content=transcript_content,
            language=language,
            tokens_used=tokens_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            model=model,
            transcript_seconds=transcript_seconds,
            generation_seconds=generation_seconds,
        )
