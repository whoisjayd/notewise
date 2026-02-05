"""High-level API for yt-study core functionality."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .config import config
from .core.events import Event, EventEmitter, EventType
from .core.llm.generator import StudyMaterialGenerator
from .core.llm.providers import get_provider
from .core.youtube.metadata import (
    get_video_chapters,
    get_video_duration,
    get_video_title,
)
from .core.youtube.transcript import fetch_transcript


async def process_video(
    video_id: str,
    output_path: Path,
    model: str = "gemini/gemini-2.0-flash",
    languages: list[str] | None = None,
    event_emitter: EventEmitter | None = None,
    **kwargs: Any,
) -> bool:
    """
    High-level API to process a single video.

    Args:
        video_id: YouTube video ID.
        output_path: Path to save the generated markdown.
        model: LLM model to use.
        languages: Preferred transcript languages.
        event_emitter: Optional event emitter for progress updates.
        **kwargs: Additional parameters for StudyMaterialGenerator.

    Returns:
        True if successful, False otherwise.
    """
    if event_emitter:
        event_emitter.emit(Event(EventType.STARTED, video_id, {"title": video_id}))

    try:
        provider = get_provider(model)
        generator = StudyMaterialGenerator(
            provider, event_emitter=event_emitter, **kwargs
        )

        # 1. Fetch metadata
        title = await asyncio.to_thread(get_video_title, video_id)
        if event_emitter:
            event_emitter.emit_status(video_id, "Fetched title", title=title)

        await asyncio.to_thread(get_video_duration, video_id)
        chapters = await asyncio.to_thread(get_video_chapters, video_id)

        # 2. Fetch transcript
        if event_emitter:
            event_emitter.emit_progress(video_id, "Fetching transcript...")
        transcript_obj = await fetch_transcript(
            video_id, languages or config.default_languages
        )

        # 3. Generate notes
        if event_emitter:
            event_emitter.emit_progress(video_id, "Generating study notes...")

        notes = await generator.generate_study_notes(
            transcript_obj.to_timestamped_text(),
            video_title=title,
            video_id=video_id,
            chapters=chapters,
            transcript_obj=transcript_obj,
        )

        # 4. Save
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(notes, encoding="utf-8")

        if event_emitter:
            event_emitter.emit(
                Event(EventType.COMPLETED, video_id, {"path": str(output_path)})
            )

        return True
    except Exception as e:
        if event_emitter:
            event_emitter.emit(Event(EventType.ERROR, video_id, {"error": str(e)}))
        return False
