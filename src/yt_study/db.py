"""SQLite-backed cache/storage primitives for pipeline state."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

from sqlmodel import Field, Session, SQLModel, create_engine, select


class Video(SQLModel, table=True):
    """Cached YouTube video metadata."""

    id: str = Field(primary_key=True, index=True)
    title: str
    duration: int


class Transcript(SQLModel, table=True):
    """Cached transcript payload for a processed video."""

    id: int | None = Field(default=None, primary_key=True)
    video_id: str = Field(foreign_key="video.id", index=True, unique=True)
    content: str
    language: str


class RunStats(SQLModel, table=True):
    """Per-run lightweight generation metadata."""

    id: int | None = Field(default=None, primary_key=True)
    video_id: str = Field(foreign_key="video.id", index=True)
    tokens_used: int
    model: str
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        index=True,
    )


class DatabaseManager:
    """Thread-safe SQLite manager shared per database path."""

    _instances: ClassVar[dict[Path, DatabaseManager]] = {}
    _instances_lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False},
        )
        self._write_lock = threading.Lock()
        SQLModel.metadata.create_all(self.engine)

    @classmethod
    def get_instance(cls, db_path: Path) -> DatabaseManager:
        """Return a singleton manager for a given SQLite file path."""
        resolved_path = db_path.expanduser().resolve()
        with cls._instances_lock:
            existing = cls._instances.get(resolved_path)
            if existing is not None:
                return existing

            instance = cls(resolved_path)
            cls._instances[resolved_path] = instance
            return instance

    @classmethod
    def close_instance(cls, db_path: Path) -> None:
        """Dispose and evict a singleton instance for the given DB path."""
        resolved_path = db_path.expanduser().resolve()
        with cls._instances_lock:
            instance = cls._instances.pop(resolved_path, None)
        if instance is not None:
            instance.close()

    @classmethod
    def close_all_instances(cls) -> None:
        """Dispose and evict all singleton instances."""
        with cls._instances_lock:
            instances = list(cls._instances.values())
            cls._instances.clear()
        for instance in instances:
            instance.close()

    def close(self) -> None:
        """Close pooled DB resources for this manager."""
        self.engine.dispose()

    def has_video(self, video_id: str) -> bool:
        """Return True when cached metadata exists for the video."""
        with Session(self.engine) as session:
            return session.get(Video, video_id) is not None

    def get_video(self, video_id: str) -> Video | None:
        """Load cached video metadata if present."""
        with Session(self.engine) as session:
            return session.get(Video, video_id)

    def mark_video_processed(self, video_id: str, title: str | None = None) -> None:
        """Create a minimal cached video row when only processed state is known."""
        with self._write_lock, Session(self.engine) as session:
            existing = session.get(Video, video_id)
            if existing is not None:
                return
            session.add(Video(id=video_id, title=title or video_id, duration=0))
            session.commit()

    def get_transcript(self, video_id: str) -> Transcript | None:
        """Load cached transcript row for a video."""
        with Session(self.engine) as session:
            return session.exec(
                select(Transcript).where(Transcript.video_id == video_id)
            ).first()

    def get_run_stats(self, video_id: str) -> list[RunStats]:
        """Load run stats for a video."""
        with Session(self.engine) as session:
            rows = session.exec(
                select(RunStats).where(RunStats.video_id == video_id)
            ).all()
        return list(rows)

    def upsert_video_cache(
        self,
        *,
        video_id: str,
        title: str,
        duration: int,
        transcript_content: str,
        language: str,
        tokens_used: int,
        model: str,
    ) -> None:
        """Persist metadata, transcript, and run stats in one transaction."""
        with self._write_lock, Session(self.engine) as session:
            video = session.get(Video, video_id)
            if video is None:
                video = Video(id=video_id, title=title, duration=duration)
                session.add(video)
            else:
                video.title = title
                video.duration = duration
                session.add(video)

            transcript = session.exec(
                select(Transcript).where(Transcript.video_id == video_id)
            ).first()
            if transcript is None:
                transcript = Transcript(
                    video_id=video_id,
                    content=transcript_content,
                    language=language,
                )
                session.add(transcript)
            else:
                transcript.content = transcript_content
                transcript.language = language
                session.add(transcript)

            session.add(
                RunStats(
                    video_id=video_id,
                    tokens_used=tokens_used,
                    model=model,
                )
            )

            session.commit()
