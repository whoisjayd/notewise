"""
Core pipeline orchestrator with concurrent processing.

This module provides the single entry point for the pipeline.
All UI concerns are handled externally via event callbacks.
No Rich, no Console, no Dashboard imports here.
"""

import asyncio
import json
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from aiolimiter import AsyncLimiter

from .config import config
from .llm.generator import StudyMaterialGenerator
from .llm.providers import get_provider
from .youtube.metadata import (
    get_video_chapters,
    get_video_duration,
    get_video_title,
)
from .youtube.transcript import (
    YouTubeIPBlockError,
    fetch_transcript,
    split_transcript_by_chapters,
)


logger = logging.getLogger(__name__)

# Windows reserved device names — compiled once at module level for reuse.
_RESERVED = re.compile(
    r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)",
    re.IGNORECASE,
)


class EventType(Enum):
    """Event types emitted by the pipeline."""

    METADATA_START = "metadata_start"
    METADATA_FETCHED = "metadata_fetched"
    TRANSCRIPT_FETCHING = "transcript_fetching"
    TRANSCRIPT_FETCHED = "transcript_fetched"
    GENERATION_START = "generation_start"
    CHUNK_GENERATING = "chunk_generating"
    CHAPTER_GENERATING = "chapter_generating"
    CHAPTER_CHUNK_GENERATING = "chapter_chunk_generating"
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


@dataclass
class PipelineResult:
    """Result of pipeline execution."""

    success_count: int
    failure_count: int
    total_count: int
    video_ids: list[str]
    errors: dict[str, str]  # video_id -> error message


def sanitize_filename(name: str) -> str:
    """
    Sanitize a string to be used as a filename.

    Handles all known cross-platform constraints:
    - Strips characters forbidden on Windows and POSIX (<>:"/\\|?* and NUL)
    - Removes ASCII control characters (0x00-0x1F, 0x7F)
    - Renames Windows reserved device names (CON, NUL, COM1–COM9, LPT1–LPT9)
    - Strips trailing dots and spaces (illegal on Windows; leading dots are kept)
    - Collapses internal whitespace to a single space
    - Trims to 100 characters
    - Returns "untitled" for empty or dot-only results

    Args:
        name: Raw filename string.

    Returns:
        Sanitized string safe for all supported file systems.
    """
    # Strip forbidden and control characters
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "", name)
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name)
    # Strip surrounding whitespace; strip only trailing dots (trailing dot is
    # illegal on Windows; leading dots like ".env" are valid)
    name = name.strip()
    name = name.rstrip(".")
    # Truncate to 100 characters
    name = name[:100]
    # Reject empty or dot-only names
    if not name:
        return "untitled"
    # Reject Windows reserved device names (case-insensitive, with or without extension)
    if _RESERVED.match(name):
        name = f"_{name}"[:100]
    return name


class CorePipeline:
    """
    Core pipeline orchestrator.

    Pure business logic - no UI concerns.
    Single public entry point: `run()`

    Communicates progress via event callbacks.
    """

    def __init__(
        self,
        model: str = "gemini/gemini-2.0-flash",
        output_dir: Path | None = None,
        languages: list[str] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        force: bool = False,
        quiz: bool = False,
    ):
        """
        Initialize the core pipeline.

        Args:
            model: LLM model string.
            output_dir: Output directory path.
            languages: Preferred transcript languages.
            temperature: LLM temperature.
            max_tokens: Max tokens for generation.
            force: Re-process videos that already have saved output.
            quiz: Also generate a multiple-choice quiz file.
        """
        self.model = model
        self.output_dir = output_dir or config.default_output_dir
        self.languages = languages or config.default_languages
        self.temperature = (
            temperature if temperature is not None else config.temperature
        )
        self.max_tokens = max_tokens if max_tokens is not None else config.max_tokens

        self.provider = get_provider(model)
        self.generator = StudyMaterialGenerator(
            self.provider,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        self.force = force
        self.quiz = quiz
        self.semaphore = asyncio.Semaphore(config.max_concurrent_videos)
        self.youtube_request_limiter = AsyncLimiter(
            max_rate=config.youtube_requests_per_minute,
            time_period=60,
        )
        self.errors: dict[str, str] = {}
        self._manifest_lock = asyncio.Lock()

    async def _acquire_youtube_request_slot(self) -> None:
        """Acquire one slot from the global YouTube request rate limiter."""
        async with self.youtube_request_limiter:
            return

    async def _rate_limited_to_thread(
        self,
        func: Callable[..., Any],
        *args: Any,
    ) -> Any:
        """
        Run blocking YouTube work in a thread after passing the global limiter.

        The limiter controls request rate while `asyncio.to_thread` keeps
        blocking I/O off the event loop.
        """
        await self._acquire_youtube_request_slot()
        return await asyncio.to_thread(func, *args)

    def _check_api_key(self) -> bool:
        """
        Check if API key is configured.

        Returns:
            True if valid, False otherwise.
            Errors are logged but not printed (UI's responsibility).
        """
        key_name = config.get_api_key_name_for_model(self.model)

        if key_name and not os.environ.get(key_name):
            logger.error(f"Missing API Key for {self.model}. Expected: {key_name}")
            return False
        return True

    # ------------------------------------------------------------------
    # Manifest helpers (checkpoint by video ID)
    # ------------------------------------------------------------------

    def _manifest_path(self) -> Path:
        """Return the path to the processed-video manifest file."""
        return self.output_dir / ".yt_study_processed.json"

    def _load_manifest(self) -> dict[str, bool]:
        """Load the manifest dict from disk; return an empty dict on any error."""
        path = self._manifest_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return {k: bool(v) for k, v in data.items()}
            except Exception:
                return {}
        return {}

    async def _mark_processed(self, video_id: str) -> None:
        """Atomically record *video_id* as successfully processed."""
        async with self._manifest_lock:
            manifest = self._load_manifest()
            manifest[video_id] = True
            try:
                self.output_dir.mkdir(parents=True, exist_ok=True)
                self._manifest_path().write_text(
                    json.dumps(manifest, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
            except Exception as exc:
                logger.warning(f"Failed to update processed manifest: {exc}")

    # ------------------------------------------------------------------
    # Quiz helper
    # ------------------------------------------------------------------

    async def _generate_and_write_quiz(self, transcript_text: str, title: str) -> None:
        """Generate a quiz from *transcript_text* and write ``<title>_quiz.md``."""
        quiz_notes = await self.generator.generate_quiz(transcript_text)
        quiz_path = self.output_dir / f"{sanitize_filename(title)}_quiz.md"
        quiz_path.write_text(quiz_notes, encoding="utf-8")

    async def _process_single_video(
        self,
        video_id: str,
        on_event: Callable[[PipelineEvent], None] | None = None,
    ) -> bool:
        """
        Process a single video: fetch transcript and generate study notes.

        Args:
            video_id: YouTube Video ID.
            on_event: Callback for progress events.

        Returns:
            True on success, False on failure.
        """
        emit = self._emit_event(on_event)
        async with self.semaphore:
            try:
                # --- Metadata Phase ---
                emit(EventType.METADATA_START, video_id)

                # Fetch all metadata concurrently; title failure is non-fatal
                meta_results = await asyncio.gather(
                    self._rate_limited_to_thread(get_video_title, video_id),
                    self._rate_limited_to_thread(get_video_duration, video_id),
                    self._rate_limited_to_thread(get_video_chapters, video_id),
                    return_exceptions=True,
                )
                raw_title, duration, chapters = meta_results

                # Fall back to video_id when title cannot be retrieved
                title: str = (
                    (raw_title or video_id)
                    if not isinstance(raw_title, BaseException)
                    else video_id
                )

                # Duration and chapters are required; re-raise on failure
                if isinstance(duration, BaseException):
                    raise duration
                if isinstance(chapters, BaseException):
                    raise chapters

                emit(
                    EventType.METADATA_FETCHED,
                    video_id,
                    title=title,
                    total_chapters=len(chapters) if chapters else 0,
                )

                # --- Checkpoint: skip already-processed videos (unless --force) ---
                if not self.force and self._load_manifest().get(video_id):
                    logger.info(f"Skipping already-processed video: {title}")
                    emit(EventType.VIDEO_SKIPPED, video_id, title=title)
                    return True

                # --- Transcript Phase ---
                emit(EventType.TRANSCRIPT_FETCHING, video_id, title=title)

                transcript_obj = await fetch_transcript(
                    video_id,
                    self.languages,
                    on_request=self._acquire_youtube_request_slot,
                )

                emit(EventType.TRANSCRIPT_FETCHED, video_id, title=title)

                # --- Generation Strategy ---
                use_chapters = bool(
                    duration > config.chapter_generation_min_duration and chapters
                )

                if use_chapters:
                    # Chapter-based generation
                    chapter_transcripts = split_transcript_by_chapters(
                        transcript_obj, chapters
                    )

                    safe_title = sanitize_filename(title)
                    output_folder = self.output_dir / safe_title
                    output_folder.mkdir(parents=True, exist_ok=True)

                    total_chapters = len(chapter_transcripts)

                    for i, (chap_title, chap_text) in enumerate(
                        chapter_transcripts.items(), 1
                    ):
                        safe_chapter = sanitize_filename(chap_title)
                        chapter_file = output_folder / f"{i:02d}_{safe_chapter}.md"

                        if not self.force and chapter_file.exists():
                            logger.info(
                                f"Skipping chapter {i}/{total_chapters}"
                                f" '{chap_title[:40]}' (already exists)"
                            )
                            continue

                        emit(
                            EventType.CHAPTER_GENERATING,
                            video_id,
                            title=title,
                            chapter_number=i,
                            total_chapters=total_chapters,
                        )

                        def _on_chapter_chunk(
                            chunk_num: int, total: int, _i: int = i
                        ) -> None:
                            emit(
                                EventType.CHAPTER_CHUNK_GENERATING,
                                video_id,
                                title=title,
                                chapter_number=_i,
                                total_chapters=total_chapters,
                                chunk_number=chunk_num,
                                total_chunks=total,
                            )

                        notes = await self.generator.generate_single_chapter_notes(
                            chapter_title=chap_title,
                            chapter_text=chap_text,
                            on_chunk=_on_chapter_chunk,
                        )

                        chapter_file.write_text(notes, encoding="utf-8")

                    if self.quiz:
                        await self._generate_and_write_quiz(
                            transcript_obj.to_text(), title
                        )

                    await self._mark_processed(video_id)
                    emit(
                        EventType.GENERATION_COMPLETE,
                        video_id,
                        title=title,
                        output_path=output_folder,
                    )
                    emit(EventType.VIDEO_SUCCESS, video_id, title=title)
                    return True

                else:
                    # Single file generation
                    emit(EventType.GENERATION_START, video_id, title=title)

                    transcript_text = transcript_obj.to_text()

                    def _on_chunk(chunk_num: int, total: int) -> None:
                        emit(
                            EventType.CHUNK_GENERATING,
                            video_id,
                            title=title,
                            chunk_number=chunk_num,
                            total_chunks=total,
                        )

                    notes = await self.generator.generate_study_notes(
                        transcript_text,
                        video_title=title,
                        on_chunk=_on_chunk,
                    )

                    output_path = self.output_dir / f"{sanitize_filename(title)}.md"
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(notes, encoding="utf-8")

                    if self.quiz:
                        await self._generate_and_write_quiz(transcript_text, title)

                    await self._mark_processed(video_id)
                    emit(
                        EventType.GENERATION_COMPLETE,
                        video_id,
                        title=title,
                        output_path=output_path,
                    )
                    emit(EventType.VIDEO_SUCCESS, video_id, title=title)
                    return True

            except YouTubeIPBlockError as e:
                error_msg = "YouTube IP blocked - use VPN or wait 1 hour"
                logger.error(f"IP Block for {video_id}: {e}")
                self.errors[video_id] = error_msg
                emit(EventType.VIDEO_FAILED, video_id, error=error_msg)
                return False

            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"
                logger.error(f"Failed to process {video_id}: {e}", exc_info=True)
                self.errors[video_id] = error_msg
                emit(EventType.VIDEO_FAILED, video_id, error=error_msg)
                return False

    def _emit_event(
        self,
        on_event: Callable[[PipelineEvent], None] | None,
    ) -> Callable[..., None]:
        """Return a helper that constructs and dispatches a PipelineEvent."""

        def emit(
            event_type: EventType,
            video_id: str,
            **data: Any,
        ) -> None:
            if on_event:
                event = PipelineEvent(
                    event_type=event_type,
                    video_id=video_id,
                    **data,
                )
                try:
                    on_event(event)
                except Exception as e:
                    logger.warning(f"Event handler error: {e}")

        return emit

    async def run(
        self,
        video_ids: list[str],
        on_event: Callable[[PipelineEvent], None] | None = None,
    ) -> PipelineResult:
        """
        Process a list of video IDs concurrently.

        Args:
            video_ids: List of YouTube video IDs to process.
            on_event: Optional callback for progress events.
                     Signature: (event: PipelineEvent) -> None

        Returns:
            PipelineResult with success count, failures, and detailed errors.
        """
        # --- Validation ---
        if not self._check_api_key():
            errors = {vid: "Missing API key" for vid in video_ids}

            # Emit events so consumers relying on events see the failure as well
            if on_event is not None:
                emit = self._emit_event(on_event)
                emit(EventType.PIPELINE_START, "")

                # Per-video failure events
                for vid in video_ids:
                    emit(EventType.VIDEO_FAILED, vid, error="Missing API key")

                emit(EventType.PIPELINE_COMPLETE, "")

            return PipelineResult(
                success_count=0,
                failure_count=len(video_ids),
                total_count=len(video_ids),
                video_ids=video_ids,
                errors=errors,
            )

        if not video_ids:
            return PipelineResult(
                success_count=0,
                failure_count=0,
                total_count=0,
                video_ids=[],
                errors={},
            )

        emit = self._emit_event(on_event)
        emit(EventType.PIPELINE_START, "")

        self.errors.clear()
        success_count = 0

        # --- Process all videos concurrently ---
        tasks = [
            self._process_single_video(video_id, on_event=on_event)
            for video_id in video_ids
        ]

        results = await asyncio.gather(*tasks, return_exceptions=False)
        success_count = sum(1 for r in results if r is True)

        failure_count = len(video_ids) - success_count

        emit(EventType.PIPELINE_COMPLETE, "")

        return PipelineResult(
            success_count=success_count,
            failure_count=failure_count,
            total_count=len(video_ids),
            video_ids=video_ids,
            errors=dict(self.errors),  # Return copy to avoid shared state mutations
        )


async def run_pipeline(
    video_ids: list[str],
    output_dir: Path | None = None,
    model: str = "gemini/gemini-2.0-flash",
    on_event: Callable[[PipelineEvent], None] | None = None,
) -> PipelineResult:
    """
    Convenience function for simple usage.

    Alternative to CorePipeline class.

    Args:
        video_ids: List of YouTube video IDs to process.
        output_dir: Optional output directory.
        model: LLM model string.
        on_event: Optional callback for progress events.

    Returns:
        PipelineResult with success/failure counts.
    """
    pipeline = CorePipeline(model=model, output_dir=output_dir)
    return await pipeline.run(video_ids, on_event=on_event)
