"""Thread-safe SQLite repository; singleton per database path."""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, ClassVar

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from .migrations import run_migrations
from .models import Base, ExportRecord, RunStatsRecord, TranscriptRecord, VideoRecord
from .schemas import (
    CacheSummarySchema,
    ExportRecordSchema,
    ModelStatsSchema,
    RecentVideoSchema,
    RunStatsSchema,
    StatsSummarySchema,
    TranscriptSchema,
    VideoSchema,
)


if TYPE_CHECKING:
    from pathlib import Path


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
            run_migrations(conn)

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

    def get_cached_video_ids(self, video_ids: list[str]) -> set[str]:
        """Return cached video IDs from the provided IDs in one query."""
        if not video_ids:
            return set()
        with Session(self._engine) as session:
            return set(
                session.execute(
                    select(VideoRecord.id).where(VideoRecord.id.in_(video_ids))
                ).scalars()
            )

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

    def get_recent_videos(self, limit: int = 10) -> list[RecentVideoSchema]:
        """Return recently processed videos joined with their latest run record."""
        latest_runs = (
            select(
                RunStatsRecord.video_id.label("video_id"),
                func.max(RunStatsRecord.id).label("latest_run_id"),
            )
            .group_by(RunStatsRecord.video_id)
            .subquery()
        )

        with Session(self._engine) as session:
            rows = session.execute(
                select(VideoRecord, RunStatsRecord)
                .join(latest_runs, VideoRecord.id == latest_runs.c.video_id)
                .join(RunStatsRecord, RunStatsRecord.id == latest_runs.c.latest_run_id)
                .order_by(RunStatsRecord.timestamp.desc(), RunStatsRecord.id.desc())
                .limit(max(limit, 1))
            ).all()

        return [
            RecentVideoSchema(
                id=video.id,
                title=video.title,
                duration=video.duration,
                cached_at=video.cached_at,
                last_run_at=run.timestamp,
                model=run.model,
                cost_usd=run.cost_usd,
                tokens_used=run.tokens_used,
            )
            for video, run in rows
        ]

    def get_stats(
        self,
        since_days: int | None = None,
        model: str | None = None,
    ) -> StatsSummarySchema:
        """Return aggregate processing statistics with a per-model breakdown."""
        filters = []
        if since_days is not None:
            cutoff = datetime.now(UTC) - timedelta(days=since_days)
            filters.append(RunStatsRecord.timestamp >= cutoff)
        if model is not None:
            filters.append(RunStatsRecord.model == model)

        with Session(self._engine) as session:
            totals = session.execute(
                select(
                    func.count(func.distinct(RunStatsRecord.video_id)),
                    func.count(RunStatsRecord.id),
                    func.coalesce(func.sum(RunStatsRecord.tokens_used), 0),
                    func.coalesce(func.sum(RunStatsRecord.prompt_tokens), 0),
                    func.coalesce(func.sum(RunStatsRecord.completion_tokens), 0),
                    func.coalesce(func.sum(RunStatsRecord.cost_usd), 0.0),
                    func.coalesce(func.sum(RunStatsRecord.transcript_seconds), 0.0),
                    func.coalesce(func.sum(RunStatsRecord.generation_seconds), 0.0),
                ).where(*filters)
            ).one()
            model_rows = session.execute(
                select(
                    RunStatsRecord.model,
                    func.count(func.distinct(RunStatsRecord.video_id)),
                    func.count(RunStatsRecord.id),
                    func.coalesce(func.sum(RunStatsRecord.tokens_used), 0),
                    func.coalesce(func.sum(RunStatsRecord.prompt_tokens), 0),
                    func.coalesce(func.sum(RunStatsRecord.completion_tokens), 0),
                    func.coalesce(func.sum(RunStatsRecord.cost_usd), 0.0),
                    func.coalesce(func.sum(RunStatsRecord.transcript_seconds), 0.0),
                    func.coalesce(func.sum(RunStatsRecord.generation_seconds), 0.0),
                )
                .where(*filters)
                .group_by(RunStatsRecord.model)
                .order_by(
                    func.coalesce(func.sum(RunStatsRecord.cost_usd), 0.0).desc(),
                    RunStatsRecord.model.asc(),
                )
            ).all()

        return StatsSummarySchema(
            total_videos_processed=int(totals[0] or 0),
            total_runs=int(totals[1] or 0),
            total_tokens_used=int(totals[2] or 0),
            total_prompt_tokens=int(totals[3] or 0),
            total_completion_tokens=int(totals[4] or 0),
            total_cost_usd=float(totals[5] or 0.0),
            total_transcript_seconds=float(totals[6] or 0.0),
            total_generation_seconds=float(totals[7] or 0.0),
            models=[
                ModelStatsSchema(
                    model=str(row[0]),
                    videos_processed=int(row[1] or 0),
                    run_count=int(row[2] or 0),
                    total_tokens_used=int(row[3] or 0),
                    total_prompt_tokens=int(row[4] or 0),
                    total_completion_tokens=int(row[5] or 0),
                    total_cost_usd=float(row[6] or 0.0),
                    total_transcript_seconds=float(row[7] or 0.0),
                    total_generation_seconds=float(row[8] or 0.0),
                )
                for row in model_rows
            ],
        )

    def get_cache_summary(self) -> CacheSummarySchema:
        """Return aggregate cache metadata for cache-info style commands."""
        with Session(self._engine) as session:
            video_totals = session.execute(
                select(
                    func.count(VideoRecord.id),
                    func.min(VideoRecord.cached_at),
                    func.max(VideoRecord.cached_at),
                )
            ).one()
            transcript_count = session.execute(
                select(func.count(TranscriptRecord.id))
            ).scalar_one()
            run_count = session.execute(
                select(func.count(RunStatsRecord.id))
            ).scalar_one()
            export_count = session.execute(
                select(func.count(ExportRecord.id))
            ).scalar_one()

        return CacheSummarySchema(
            total_videos=int(video_totals[0] or 0),
            total_transcripts=int(transcript_count or 0),
            total_runs=int(run_count or 0),
            total_exports=int(export_count or 0),
            oldest_cached_at=video_totals[1],
            newest_cached_at=video_totals[2],
        )

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

    def prune_old_entries(self, older_than_days: int = 30) -> int:
        """Delete cached videos older than the provided age threshold."""
        cutoff = datetime.now(UTC) - timedelta(days=max(older_than_days, 0))
        with self._write_lock, Session(self._engine) as session:
            stale_videos = (
                session.execute(
                    select(VideoRecord).where(VideoRecord.cached_at < cutoff)
                )
                .scalars()
                .all()
            )
            deleted_count = len(stale_videos)
            for video in stale_videos:
                session.delete(video)
            session.commit()
        return deleted_count

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
                    timestamp=datetime.now(UTC),
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
            cached_at = datetime.now(UTC)
            video = session.get(VideoRecord, video_id)
            if video is None:
                video = VideoRecord(
                    id=video_id,
                    title=title,
                    duration=duration,
                    cached_at=cached_at,
                )
                session.add(video)
            else:
                video.title = title
                video.duration = duration
                video.cached_at = cached_at

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
                    timestamp=datetime.now(UTC),
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
