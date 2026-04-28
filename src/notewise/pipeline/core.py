"""
Core pipeline orchestrator with concurrent processing.

This module now owns the pipeline state and persistence boundary.
Batch execution and single-video orchestration live in
``notewise.pipeline._execution``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.exc import SQLAlchemyError

from notewise._constants import (
    DEFAULT_MODEL,
    DEFAULT_NOTES_OUTPUT_FORMAT,
    DEFAULT_TARGET_LANGUAGE,
    DEFAULT_THROTTLE_SECONDS,
    DEFAULT_USE_COMBINE_CHUNK,
    OUTPUT_METADATA_FILENAME,
    OUTPUT_METADATA_VIDEO_ID_KEY,
)
from notewise.config import get_cache_db_path
from notewise.config import settings as config
from notewise.domain.events import EventType, PipelineEvent
from notewise.domain.results import PipelineMetrics, PipelineResult
from notewise.llm.provider import UsageTotals, get_provider
from notewise.pipeline._artifacts import (
    export_transcript,
    generate_and_write_quiz,
    prefix_chapter_heading_with_timestamp,
)
from notewise.pipeline._documents import (
    build_chapter_bundle,
    get_output_extension,
    normalize_output_format,
    normalize_output_formats,
    render_notes_document,
    render_notes_documents,
)
from notewise.pipeline._helpers import (
    coerce_usage_float,
    coerce_usage_int,
    coerce_usage_totals,
    estimate_tokens_used,
    suffix_output_target,
)
from notewise.pipeline._limiter import LimiterProtocol, get_youtube_limiter
from notewise.pipeline._state import PipelineSharedState, dedupe_video_ids
from notewise.storage import DatabaseRepository, VideoSchema
from notewise.utils import sanitize_filename
from notewise.youtube.metadata import get_video_metadata  # noqa: F401
from notewise.youtube.transcript import (
    fetch_transcript,  # noqa: F401
    split_transcript_by_chapters,  # noqa: F401
    split_transcript_by_chapters_with_metadata,  # noqa: F401
)


logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

__all__ = [
    "CorePipeline",
    "UsageTotals",
    "coerce_usage_float",
    "coerce_usage_int",
    "coerce_usage_totals",
    "export_transcript",
    "fetch_transcript",
    "generate_and_write_quiz",
    "get_video_metadata",
    "PipelineSharedState",
    "dedupe_video_ids",
    "build_chapter_bundle",
    "get_output_extension",
    "split_transcript_by_chapters",
    "split_transcript_by_chapters_with_metadata",
    "normalize_output_format",
    "normalize_output_formats",
    "prefix_chapter_heading_with_timestamp",
    "render_notes_document",
    "render_notes_documents",
    "run_pipeline",
    "sanitize_filename",
]


class CorePipeline:
    """Core pipeline state and persistence boundary."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        output_dir: Path | None = None,
        output_format: str = DEFAULT_NOTES_OUTPUT_FORMAT,
        output_formats: list[str] | None = None,
        languages: list[str] | None = None,
        target_language: str = DEFAULT_TARGET_LANGUAGE,
        temperature: float | None = None,
        max_tokens: int | None = None,
        throttle_seconds: float = DEFAULT_THROTTLE_SECONDS,
        force: bool = False,
        quiz: bool = False,
        use_combine_chunk: bool = DEFAULT_USE_COMBINE_CHUNK,
        export_transcript: str | None = None,
        timestamps: bool = False,
        chapter_directory_output: bool = False,
        youtube_cookie_file: str | None = None,
        shared_state: PipelineSharedState | None = None,
    ):
        self.model = model
        self.output_dir = output_dir or config.default_output_dir
        requested_formats = (
            output_formats if output_formats is not None else output_format
        )
        self.output_formats = normalize_output_formats(requested_formats)
        self.output_format = self.output_formats[0]
        self.languages = languages or config.default_languages
        self.target_language = target_language.strip() or DEFAULT_TARGET_LANGUAGE
        self.temperature = (
            temperature if temperature is not None else config.temperature
        )
        self.max_tokens = max_tokens if max_tokens is not None else config.max_tokens
        self.provider = get_provider(model)
        from .generation import StudyMaterialGenerator

        self.generator = StudyMaterialGenerator(
            self.provider,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            throttle_seconds=throttle_seconds,
            use_combine_chunk=use_combine_chunk,
            target_language=self.target_language,
        )
        self.throttle_seconds = self.generator.throttle_seconds
        self.force = force
        self.quiz = quiz
        self.use_combine_chunk = use_combine_chunk
        self.export_transcript_format = export_transcript
        self.timestamps = timestamps
        self.chapter_directory_output = chapter_directory_output
        self.youtube_cookie_file = youtube_cookie_file or config.youtube_cookie_file
        self.youtube_requests_per_minute = config.youtube_requests_per_minute
        self.errors: dict[str, str] = {}
        self._metrics_lock = asyncio.Lock()
        self._run_metrics = PipelineMetrics()
        if shared_state is None:
            self.semaphore = asyncio.Semaphore(config.max_concurrent_videos)
            self._chapter_semaphore = asyncio.Semaphore(
                max(1, int(config.max_concurrent_chapters))
            )
            self._output_lock = asyncio.Lock()
            self._reserved_output_targets: set[Path] = set()
        else:
            self.semaphore = shared_state.semaphore
            if shared_state.chapter_semaphore is None:
                shared_state.chapter_semaphore = asyncio.Semaphore(
                    max(1, int(config.max_concurrent_chapters))
                )
            self._chapter_semaphore = shared_state.chapter_semaphore
            self._output_lock = shared_state.output_lock
            self._reserved_output_targets = shared_state.reserved_output_targets
        self.db = DatabaseRepository.get_instance(self._cache_db_path())

    def _get_youtube_request_limiter(self) -> LimiterProtocol:
        return get_youtube_limiter(self.youtube_requests_per_minute)

    async def _acquire_youtube_request_slot(self) -> None:
        async with self._get_youtube_request_limiter():
            return

    async def _rate_limited_to_thread(
        self,
        func: Callable[..., Any],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        await self._acquire_youtube_request_slot()
        return await asyncio.to_thread(func, *args, **kwargs)

    def _check_api_key(self) -> bool:
        missing_config = config.get_missing_config_names_for_model(self.model)
        if missing_config:
            expected = ", ".join(missing_config)
            logger.error(
                f"Missing provider config for {self.model}. Expected: {expected}"
            )
            return False
        return True

    def _cache_db_path(self) -> Path:
        return get_cache_db_path()

    async def _get_cached_video(self, video_id: str) -> VideoSchema | None:
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
        try:
            tokens_used = (
                total_tokens
                if total_tokens > 0
                else estimate_tokens_used(transcript_text)
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
        async with self._metrics_lock:
            self._run_metrics.add_from(metrics)

    @staticmethod
    def _coerce_usage_int(value: Any) -> int:
        return coerce_usage_int(value)

    @staticmethod
    def _coerce_usage_float(value: Any) -> float:
        return coerce_usage_float(value)

    def _coerce_usage_totals(self, raw_usage: Any) -> UsageTotals:
        return coerce_usage_totals(raw_usage)

    def _estimate_tokens_used(self, transcript_text: str) -> int:
        try:
            return max(1, int(self.generator.count_tokens(transcript_text)))
        except Exception:
            return estimate_tokens_used(transcript_text)

    async def _reserve_output_target(
        self,
        base: Path,
        video_id: str,
        *,
        allow_existing_base: bool = False,
    ) -> Path:
        async with self._output_lock:
            base_available = base not in self._reserved_output_targets and (
                allow_existing_base
                or not base.exists()
                or self._is_reusable_directory_output(base, video_id)
            )
            target = base if base_available else suffix_output_target(base, video_id)
            self._reserved_output_targets.add(target)
            return target

    def _is_reusable_directory_output(self, target: Path, video_id: str) -> bool:
        """Return True when a pre-existing chapter directory belongs to this video."""
        if not target.is_dir():
            return False

        metadata_path = target / OUTPUT_METADATA_FILENAME
        if not metadata_path.exists():
            return False

        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False

        return metadata.get(OUTPUT_METADATA_VIDEO_ID_KEY) == video_id

    def _write_output_target_metadata(self, target: Path, video_id: str) -> None:
        """Write lightweight output ownership metadata for chapter directories."""
        if not target.is_dir():
            return

        metadata_path = target / OUTPUT_METADATA_FILENAME
        metadata = {OUTPUT_METADATA_VIDEO_ID_KEY: video_id}
        metadata_path.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")

    async def _release_output_target(self, target: Path | None) -> None:
        """Release an in-memory reservation once processing for that target ends."""
        if target is None:
            return
        async with self._output_lock:
            self._reserved_output_targets.discard(target)

    def _emit_event(
        self,
        on_event: Callable[[PipelineEvent], None] | None,
    ) -> Callable[..., None]:
        def emit(event_type: EventType, video_id: str, **data: Any) -> None:
            if on_event:
                event = PipelineEvent(event_type=event_type, video_id=video_id, **data)
                try:
                    on_event(event)
                except Exception as exc:
                    logger.warning(f"Event handler error: {exc}")

        return emit

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
        target_dir = output_dir or self.output_dir
        await generate_and_write_quiz(
            self.generator,
            transcript_text,
            quiz_name,
            output_dir=target_dir,
            emit=emit,
            video_id=video_id,
            title=title,
        )

    def _export_transcript(
        self,
        transcript: Any,
        title: str,
        output_dir: Path,
        video_id: str,
    ) -> Path:
        return export_transcript(
            self.db,
            transcript,
            title,
            output_dir,
            video_id,
            self.export_transcript_format,
        )

    async def _process_single_video(
        self,
        video_id: str,
        on_event: Callable[[PipelineEvent], None] | None = None,
    ) -> bool:
        from notewise.pipeline._execution import process_single_video as _impl

        return await _impl(self, video_id, on_event=on_event)

    async def run(
        self,
        video_ids: list[str],
        on_event: Callable[[PipelineEvent], None] | None = None,
    ) -> PipelineResult:
        from notewise.pipeline._execution import run_pipeline as _impl

        return await _impl(self, video_ids, on_event=on_event)


async def run_pipeline(
    video_ids: list[str],
    output_dir: Path | None = None,
    model: str = DEFAULT_MODEL,
    output_format: str = DEFAULT_NOTES_OUTPUT_FORMAT,
    output_formats: list[str] | None = None,
    target_language: str = DEFAULT_TARGET_LANGUAGE,
    throttle_seconds: float = DEFAULT_THROTTLE_SECONDS,
    use_combine_chunk: bool = DEFAULT_USE_COMBINE_CHUNK,
    on_event: Callable[[PipelineEvent], None] | None = None,
) -> PipelineResult:
    pipeline_kwargs: dict[str, Any] = {
        "model": model,
        "output_dir": output_dir,
        "output_format": output_format,
        "target_language": target_language,
        "throttle_seconds": throttle_seconds,
        "use_combine_chunk": use_combine_chunk,
    }
    if output_formats is not None:
        pipeline_kwargs["output_formats"] = output_formats
    pipeline = CorePipeline(**pipeline_kwargs)
    return await pipeline.run(video_ids, on_event=on_event)
