"""Artifact writing helpers for transcripts and generated quizzes."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.exc import SQLAlchemyError

from notewise.domain.events import EventType
from notewise.domain.youtube import VideoTranscript
from notewise.utils import sanitize_filename


logger = structlog.get_logger(__name__)


def _format_timestamp(seconds: int) -> str:
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _normalize_heading_for_timestamp_match(text: str) -> str:
    text = re.sub(r"^\[(?:\d{2}:)?\d{2}:\d{2}\]\s+", "", text.strip())
    text = re.sub(r"\s+", " ", text)
    return text.casefold()


def _heading_matches_chapter_title(heading_text: str, chapter_title: str) -> bool:
    normalized_heading = _normalize_heading_for_timestamp_match(heading_text)
    normalized_title = _normalize_heading_for_timestamp_match(chapter_title)
    if normalized_heading == normalized_title:
        return True
    for separator in (":", " - ", " — ", " – "):
        if normalized_heading.startswith(f"{normalized_title}{separator}"):
            return True
    return False


def prefix_chapter_heading_with_timestamp(
    notes: str,
    chapter_title: str,
    start_seconds: int,
) -> str:
    """Prefix the matching chapter heading with a deterministic timestamp label."""
    heading_re = re.compile(r"^(?P<level>#{1,6})\s+(?P<text>.+?)\s*$", re.MULTILINE)
    for match in heading_re.finditer(notes):
        heading_text = match.group("text")
        if not _heading_matches_chapter_title(heading_text, chapter_title):
            continue
        cleaned_heading_text = re.sub(
            r"^\[(?:\d{2}:)?\d{2}:\d{2}\]\s+",
            "",
            heading_text.strip(),
        )
        timestamped_heading = (
            f"{match.group('level')} [{_format_timestamp(start_seconds)}] "
            f"{cleaned_heading_text}"
        )
        return f"{notes[:match.start()]}{timestamped_heading}{notes[match.end():]}"

    timestamped_heading = f"# [{_format_timestamp(start_seconds)}] {chapter_title}"
    return f"{timestamped_heading}\n\n{notes.lstrip()}"



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
