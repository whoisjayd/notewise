"""SQLAlchemy ORM entity definitions for the notewise cache database."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class VideoRecord(Base):
    __tablename__ = "video"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    duration: Mapped[int] = mapped_column(Integer, nullable=False)
    cached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    transcripts: Mapped[list[TranscriptRecord]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    run_stats: Mapped[list[RunStatsRecord]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    export_records: Mapped[list[ExportRecord]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )


class TranscriptRecord(Base):
    __tablename__ = "transcript"
    __table_args__ = (UniqueConstraint("video_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(
        String, ForeignKey("video.id"), index=True, nullable=False
    )
    content: Mapped[str] = mapped_column(String, nullable=False)
    language: Mapped[str] = mapped_column(String, nullable=False)

    video: Mapped[VideoRecord] = relationship(back_populates="transcripts")


class RunStatsRecord(Base):
    __tablename__ = "runstats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(
        String, ForeignKey("video.id"), index=True, nullable=False
    )
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    model: Mapped[str] = mapped_column(String, nullable=False)
    transcript_seconds: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    generation_seconds: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    video: Mapped[VideoRecord] = relationship(back_populates="run_stats")


class ExportRecord(Base):
    __tablename__ = "exportrecord"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(
        String, ForeignKey("video.id"), index=True, nullable=False
    )
    format: Mapped[str] = mapped_column(String, nullable=False)
    output_path: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    video: Mapped[VideoRecord] = relationship(back_populates="export_records")
