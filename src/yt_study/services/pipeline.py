"""
Core pipeline orchestrator with concurrent processing.

This module provides the single entry point for the pipeline.
All UI concerns are handled externally via event callbacks.
No Rich, no Console, no Dashboard imports here.
"""

import asyncio
import json
import os
import time
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.exc import SQLAlchemyError

from yt_study._constants import (
    DEFAULT_MODEL,
)
from yt_study.config import get_cache_db_path
from yt_study.config import settings as config

# Domain objects also available from yt_study.domain for new code
from yt_study.domain.events import EventType, PipelineEvent
from yt_study.domain.results import PipelineMetrics, PipelineResult
from yt_study.domain.youtube import VideoMetadata, VideoTranscript
from yt_study.errors import (
    IPBlockError,
    VideoUnavailableError,
    format_user_error,
)
from yt_study.infrastructure.llm.provider import UsageTotals, get_provider
from yt_study.infrastructure.youtube.metadata import get_video_metadata
from yt_study.infrastructure.youtube.transcript import (
    fetch_transcript,
    split_transcript_by_chapters,
)
from yt_study.persistence import DatabaseRepository, VideoSchema
from yt_study.services._limiter import LimiterProtocol, get_youtube_limiter
from yt_study.services.generation import StudyMaterialGenerator
from yt_study.utils import dedupe_ordered, sanitize_filename


logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


def dedupe_video_ids(video_ids: list[str]) -> list[str]:
    """Return video IDs in first-seen order with duplicates removed."""
    return dedupe_ordered(video_ids)


@dataclass
class PipelineSharedState:
    """Shared coordination primitives for multi-pipeline batch processing."""

    semaphore: asyncio.Semaphore
    output_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    reserved_output_targets: set[Path] = field(default_factory=set)


class CorePipeline:
    """
    Core pipeline orchestrator.

    Pure business logic - no UI concerns.
    Single public entry point: `run()`

    Communicates progress via event callbacks.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        output_dir: Path | None = None,
        languages: list[str] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        force: bool = False,
        quiz: bool = False,
        export_transcript: str | None = None,
        youtube_cookie_file: str | None = None,
        shared_state: PipelineSharedState | None = None,
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
            export_transcript: Export format for raw transcript ('txt' or 'json').
            youtube_cookie_file: Optional path to a Netscape cookies file.
            shared_state: Optional shared semaphore/output reservation state.
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
        self.export_transcript = export_transcript
        self.youtube_cookie_file = youtube_cookie_file or config.youtube_cookie_file
        self.youtube_requests_per_minute = config.youtube_requests_per_minute
        self.errors: dict[str, str] = {}
        self._metrics_lock = asyncio.Lock()
        self._run_metrics = PipelineMetrics()
        if shared_state is None:
            self.semaphore = asyncio.Semaphore(config.max_concurrent_videos)
            self._output_lock = asyncio.Lock()
            self._reserved_output_targets: set[Path] = set()
        else:
            self.semaphore = shared_state.semaphore
            self._output_lock = shared_state.output_lock
            self._reserved_output_targets = shared_state.reserved_output_targets
        self.db = DatabaseRepository.get_instance(self._cache_db_path())

    def _get_youtube_request_limiter(self) -> LimiterProtocol:
        """Return the shared limiter for this pipeline's configured rate."""
        return get_youtube_limiter(self.youtube_requests_per_minute)

    async def _acquire_youtube_request_slot(self) -> None:
        """Acquire one slot from the global YouTube request rate limiter."""
        async with self._get_youtube_request_limiter():
            return

    async def _rate_limited_to_thread(
        self,
        func: Callable[..., Any],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Compatibility helper for callers/tests expecting the old boundary."""
        await self._acquire_youtube_request_slot()
        return await asyncio.to_thread(func, *args, **kwargs)

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

    def _cache_db_path(self) -> Path:
        """Return the global SQLite cache path used for pipeline state."""
        return get_cache_db_path()

    async def _get_cached_video(self, video_id: str) -> VideoSchema | None:
        """Return cached metadata for a video when present."""
        try:
            return await self.db.aget_video(video_id)
        except SQLAlchemyError as exc:
            logger.warning(
                f"Failed to read SQLite cache for {video_id}: {exc}",
                exc_info=True,
            )
            return None

    async def _persist_video_cache(
        self,
        *,
        video_id: str,
        title: str,
        duration: int,
        transcript_text: str,
        transcript_language: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        cost_usd: float = 0.0,
        transcript_seconds: float = 0.0,
        generation_seconds: float = 0.0,
    ) -> None:
        """Persist metadata/transcript/run stats for completed videos."""
        try:
            tokens_used = (
                total_tokens
                if total_tokens > 0
                else self._estimate_tokens_used(transcript_text)
            )
            await self.db.aupsert_video_cache(
                video_id=video_id,
                title=title,
                duration=duration,
                transcript_content=transcript_text,
                language=transcript_language,
                tokens_used=tokens_used,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                model=self.model,
                cost_usd=cost_usd,
                transcript_seconds=transcript_seconds,
                generation_seconds=generation_seconds,
            )
        except SQLAlchemyError as exc:
            logger.warning(
                f"Failed to persist SQLite cache for {video_id}: {exc}",
                exc_info=True,
            )

    async def _record_metrics(self, metrics: PipelineMetrics) -> None:
        """Thread-safe accumulation of per-video metrics into run totals."""
        async with self._metrics_lock:
            self._run_metrics.add_from(metrics)

    @staticmethod
    def _suffix_output_target(base: Path, video_id: str) -> Path:
        """Append a stable video-id suffix to an output file or directory name."""
        suffix = f" ({sanitize_filename(video_id)})"
        if base.suffix:
            return base.with_name(f"{base.stem}{suffix}{base.suffix}")
        return base.with_name(f"{base.name}{suffix}")

    async def _reserve_output_target(
        self,
        base: Path,
        video_id: str,
        *,
        allow_existing_base: bool = False,
    ) -> Path:
        """Reserve a unique output target for this run to avoid title collisions."""
        async with self._output_lock:
            base_available = base not in self._reserved_output_targets and (
                allow_existing_base or not base.exists()
            )
            target = (
                base if base_available else self._suffix_output_target(base, video_id)
            )
            self._reserved_output_targets.add(target)
            return target

    @staticmethod
    def _coerce_usage_int(value: Any) -> int:
        """Convert usage values to non-negative ints without trusting mock objects."""
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return max(0, value)
        if isinstance(value, float):
            return max(0, int(value))
        if isinstance(value, str):
            try:
                return max(0, int(value.strip()))
            except ValueError:
                return 0
        return 0

    @staticmethod
    def _coerce_usage_float(value: Any) -> float:
        """Convert usage values to non-negative floats safely."""
        if isinstance(value, bool):
            return float(value)
        if isinstance(value, (int, float)):
            return max(0.0, float(value))
        if isinstance(value, str):
            try:
                return max(0.0, float(value.strip()))
            except ValueError:
                return 0.0
        return 0.0

    def _coerce_usage_totals(self, raw_usage: Any) -> UsageTotals:
        """Normalize usage collector output into a concrete UsageTotals object."""
        if isinstance(raw_usage, UsageTotals):
            return raw_usage
        return UsageTotals(
            prompt_tokens=self._coerce_usage_int(
                getattr(raw_usage, "prompt_tokens", 0)
            ),
            completion_tokens=self._coerce_usage_int(
                getattr(raw_usage, "completion_tokens", 0)
            ),
            total_tokens=self._coerce_usage_int(getattr(raw_usage, "total_tokens", 0)),
            cost_usd=self._coerce_usage_float(getattr(raw_usage, "cost_usd", 0.0)),
        )

    def _estimate_tokens_used(self, transcript_text: str) -> int:
        """Estimate token usage for run stats using generator token counting."""
        try:
            return max(1, int(self.generator.count_tokens(transcript_text)))
        except Exception:
            return max(1, len(transcript_text) // 4)

    # ------------------------------------------------------------------
    # Quiz helper
    # ------------------------------------------------------------------

    async def _generate_and_write_quiz(
        self,
        transcript_text: str,
        quiz_name: str,
        output_dir: Path | None = None,
        *,
        emit: Callable[..., None],
        video_id: str,
        title: str,
    ) -> None:
        """Generate a quiz and write it using the resolved output target name."""
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

        quiz_notes = await self.generator.generate_quiz(
            transcript_text,
            on_chunk=_on_quiz_chunk,
            on_combine=_on_quiz_combine,
        )
        target_dir = output_dir or self.output_dir
        quiz_path = target_dir / f"{sanitize_filename(quiz_name)}_quiz.md"
        quiz_path.write_text(quiz_notes, encoding="utf-8")
        emit(EventType.QUIZ_COMPLETE, video_id, title=title)

    # ------------------------------------------------------------------
    # Transcript export helper
    # ------------------------------------------------------------------

    def _export_transcript(
        self,
        transcript: VideoTranscript,
        title: str,
        output_dir: Path,
        video_id: str,
    ) -> Path:
        """Export raw transcript to file in the configured format.

        Args:
            transcript: The video transcript object.
            title: VideoSchema title for filename.
            output_dir: Directory to write the export file.
            video_id: YouTube video ID for database record.

        Returns:
            Path to the created export file.
        """
        safe_title = sanitize_filename(title)
        format_ext = self.export_transcript

        if format_ext == "json":
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
            # Default to txt format
            export_path = output_dir / f"{safe_title}_transcript.txt"
            export_path.write_text(transcript.to_text(), encoding="utf-8")

        # Persist export record to database (fire-and-forget for performance)
        try:
            self.db.add_export_record(
                video_id=video_id,
                format=format_ext or "txt",
                output_path=str(export_path),
            )
        except SQLAlchemyError as exc:
            logger.warning(
                f"Failed to persist export record for {video_id}: {exc}",
                exc_info=True,
            )

        return export_path

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

                # --- Checkpoint: skip already-processed videos (unless --force) ---
                cached_video = (
                    None if self.force else await self._get_cached_video(video_id)
                )
                if cached_video is not None:
                    logger.info(f"Skipping already-processed video: {video_id}")
                    emit(
                        EventType.VIDEO_SKIPPED,
                        video_id,
                        title=cached_video.title or video_id,
                    )
                    return True
                current_cached_video = cached_video
                if self.force:
                    current_cached_video = await self._get_cached_video(video_id)

                # Fetch title, duration, and chapters in a single async call
                await self._acquire_youtube_request_slot()
                meta: VideoMetadata = await get_video_metadata(
                    video_id,
                    self.youtube_cookie_file,
                )
                title: str = meta.title
                duration: int = meta.duration
                chapters = meta.chapters

                emit(
                    EventType.METADATA_FETCHED,
                    video_id,
                    title=title,
                    total_chapters=len(chapters) if chapters else 0,
                )

                # --- Transcript Phase ---
                emit(EventType.TRANSCRIPT_FETCHING, video_id, title=title)

                transcript_start = time.perf_counter()
                transcript_obj = await fetch_transcript(
                    video_id,
                    self.languages,
                    on_request=self._acquire_youtube_request_slot,
                    cookie_file=self.youtube_cookie_file,
                )
                transcript_text = transcript_obj.to_text()
                transcript_seconds = time.perf_counter() - transcript_start

                emit(EventType.TRANSCRIPT_FETCHED, video_id, title=title)

                # --- Generation Strategy ---
                use_chapters = bool(
                    duration > config.chapter_generation_min_duration and chapters
                )

                # --- Transcript Export (if requested) ---
                # Export as single file per video (not per-chapter)
                if self.export_transcript:
                    self._export_transcript(
                        transcript_obj, title, self.output_dir, video_id
                    )

                generation_start = time.perf_counter()
                usage_context = nullcontext(UsageTotals())
                usage_collector = getattr(self.provider, "collect_usage", None)
                if callable(usage_collector):
                    candidate = usage_collector()
                    if hasattr(candidate, "__enter__") and hasattr(
                        candidate, "__exit__"
                    ):
                        usage_context = candidate

                with usage_context as raw_usage_totals:
                    if use_chapters:
                        # Chapter-based generation
                        chapter_transcripts = split_transcript_by_chapters(
                            transcript_obj, chapters
                        )

                        if not chapter_transcripts:
                            logger.warning(
                                f"No usable chapter transcripts found for {video_id}; "
                                "falling back to single-file generation."
                            )
                            use_chapters = False

                    if use_chapters:
                        safe_title = sanitize_filename(title)
                        output_target = await self._reserve_output_target(
                            self.output_dir / safe_title,
                            video_id,
                            allow_existing_base=current_cached_video is not None,
                        )
                        output_target.mkdir(parents=True, exist_ok=True)

                        total_chapters = len(chapter_transcripts)

                        for i, (chap_title, chap_text) in enumerate(
                            chapter_transcripts.items(), 1
                        ):
                            safe_chapter = sanitize_filename(chap_title)
                            chapter_file = output_target / f"{i:02d}_{safe_chapter}.md"

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

                            def _on_chapter_combine(
                                total_parts: int, _i: int = i
                            ) -> None:
                                emit(
                                    EventType.CHAPTER_COMBINING,
                                    video_id,
                                    title=title,
                                    chapter_number=_i,
                                    total_chapters=total_chapters,
                                    total_chunks=total_parts,
                                )

                            notes = await self.generator.generate_single_chapter_notes(
                                chapter_title=chap_title,
                                chapter_text=chap_text,
                                on_chunk=_on_chapter_chunk,
                                on_combine=_on_chapter_combine,
                            )
                            chapter_file.write_text(notes, encoding="utf-8")
                    else:
                        # Single file generation
                        emit(EventType.GENERATION_START, video_id, title=title)

                        def _on_chunk(chunk_num: int, total: int) -> None:
                            emit(
                                EventType.CHUNK_GENERATING,
                                video_id,
                                title=title,
                                chunk_number=chunk_num,
                                total_chunks=total,
                            )

                        def _on_combine(total_parts: int) -> None:
                            emit(
                                EventType.GENERATION_COMBINING,
                                video_id,
                                title=title,
                                total_chunks=total_parts,
                            )

                        notes = await self.generator.generate_study_notes(
                            transcript_text,
                            video_title=title,
                            on_chunk=_on_chunk,
                            on_combine=_on_combine,
                        )

                        output_target = await self._reserve_output_target(
                            self.output_dir / f"{sanitize_filename(title)}.md",
                            video_id,
                            allow_existing_base=current_cached_video is not None,
                        )
                        output_target.parent.mkdir(parents=True, exist_ok=True)
                        output_target.write_text(notes, encoding="utf-8")

                    if self.quiz:
                        quiz_output_dir = (
                            output_target if use_chapters else self.output_dir
                        )
                        quiz_name = (
                            output_target.name if use_chapters else output_target.stem
                        )
                        await self._generate_and_write_quiz(
                            transcript_text,
                            quiz_name,
                            output_dir=quiz_output_dir,
                            emit=emit,
                            video_id=video_id,
                            title=title,
                        )

                usage_totals = self._coerce_usage_totals(raw_usage_totals)
                generation_seconds = time.perf_counter() - generation_start
                video_metrics = PipelineMetrics(
                    prompt_tokens=usage_totals.prompt_tokens,
                    completion_tokens=usage_totals.completion_tokens,
                    total_tokens=usage_totals.total_tokens,
                    cost_usd=usage_totals.cost_usd,
                    transcript_seconds=transcript_seconds,
                    generation_seconds=generation_seconds,
                )
                await self._record_metrics(video_metrics)
                await self._persist_video_cache(
                    video_id=video_id,
                    title=title,
                    duration=duration,
                    transcript_text=transcript_text,
                    transcript_language=transcript_obj.language_code,
                    prompt_tokens=video_metrics.prompt_tokens,
                    completion_tokens=video_metrics.completion_tokens,
                    total_tokens=video_metrics.total_tokens,
                    cost_usd=video_metrics.cost_usd,
                    transcript_seconds=video_metrics.transcript_seconds,
                    generation_seconds=video_metrics.generation_seconds,
                )
                emit(
                    EventType.GENERATION_COMPLETE,
                    video_id,
                    title=title,
                    output_path=output_target,
                )
                emit(EventType.VIDEO_SUCCESS, video_id, title=title)
                return True

            except IPBlockError as e:
                error_msg = format_user_error(e)
                logger.error(f"IP Block for {video_id}: {e}")
                self.errors[video_id] = error_msg
                emit(EventType.VIDEO_FAILED, video_id, error=error_msg)
                return False

            except VideoUnavailableError as e:
                error_msg = str(e)
                logger.error(f"Cannot process {video_id}: {e}")
                self.errors[video_id] = error_msg
                emit(EventType.VIDEO_FAILED, video_id, error=error_msg)
                return False

            except Exception as e:
                error_msg = format_user_error(e)
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
        video_ids = dedupe_video_ids(video_ids)

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
        self._run_metrics = PipelineMetrics()

        # --- Process all videos concurrently ---
        tasks = [
            self._process_single_video(video_id, on_event=on_event)
            for video_id in video_ids
        ]

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        results: list[bool] = []
        for _vid, _result in zip(video_ids, raw_results, strict=False):
            if isinstance(_result, BaseException):
                _err_msg = format_user_error(
                    _result
                    if isinstance(_result, Exception)
                    else Exception(str(_result))
                )
                self.errors[_vid] = _err_msg
                emit(EventType.VIDEO_FAILED, _vid, error=_err_msg)
                results.append(False)
            else:
                results.append(bool(_result))
        success_count = sum(1 for r in results if r is True)
        failure_count = len(video_ids) - success_count

        emit(EventType.PIPELINE_COMPLETE, "")

        return PipelineResult(
            success_count=success_count,
            failure_count=failure_count,
            total_count=len(video_ids),
            video_ids=video_ids,
            errors=dict(self.errors),  # Return copy to avoid shared state mutations
            metrics=self._run_metrics.copy(),
        )


async def run_pipeline(
    video_ids: list[str],
    output_dir: Path | None = None,
    model: str = DEFAULT_MODEL,
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
    pipeline = CorePipeline(
        model=model,
        output_dir=output_dir,
    )
    return await pipeline.run(video_ids, on_event=on_event)
