"""Artifact writing helpers for transcripts and generated quizzes."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.exc import SQLAlchemyError

from notewise.domain.events import EventType
from notewise.domain.youtube import VideoTranscript
from notewise.utils import sanitize_filename


logger = structlog.get_logger(__name__)


async def generate_and_write_quiz(
    generator: Any,
    transcript_text: str,
    quiz_name: str,
    *,
    output_dir: Path,
    emit: Callable[..., None],
    video_id: str,
    title: str,
) -> None:
    """Generate a quiz and write it to the resolved output directory."""

    emit(EventType.QUIZ_GENERATING, video_id, title=title)

    def _on_quiz_chunk(chunk_num: int, total: int) -> None:
        emit(
            EventType.QUIZ_CHUNK_GENERATING,
            video_id,
            title=title,
            chunk_number=chunk_num,
            total_chunks=total,
        )

    def _on_quiz_combine(total_parts: int) -> None:
        emit(
            EventType.QUIZ_COMBINING,
            video_id,
            title=title,
            total_chunks=total_parts,
        )

    quiz_notes = await generator.generate_quiz(
        transcript_text,
        on_chunk=_on_quiz_chunk,
        on_combine=_on_quiz_combine,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    quiz_path = output_dir / f"{sanitize_filename(quiz_name)}_quiz.md"
    quiz_path.write_text(quiz_notes, encoding="utf-8")
    emit(EventType.QUIZ_COMPLETE, video_id, title=title)


def export_transcript(
    db: Any,
    transcript: VideoTranscript,
    title: str,
    output_dir: Path,
    video_id: str,
    export_format: str | None,
) -> Path:
    """Export a transcript to disk and persist the export record."""

    safe_title = sanitize_filename(title)
    output_dir.mkdir(parents=True, exist_ok=True)

    if export_format == "json":
        export_path = output_dir / f"{safe_title}_transcript.json"
        data = {
            "video_id": transcript.video_id,
            "language": transcript.language,
            "language_code": transcript.language_code,
            "is_generated": transcript.is_generated,
            "segments": [
                {
                    "text": seg.text,
                    "start": seg.start,
                    "duration": seg.duration,
                }
                for seg in transcript.segments
            ],
        }
        export_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    else:
        export_path = output_dir / f"{safe_title}_transcript.txt"
        export_path.write_text(transcript.to_text(), encoding="utf-8")

    try:
        db.add_export_record(
            video_id=video_id,
            format=export_format or "txt",
            output_path=str(export_path),
        )
    except SQLAlchemyError as exc:
        logger.warning(
            f"Failed to persist export record for {video_id}: {exc}",
            exc_info=True,
        )

    return export_path
