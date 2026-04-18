"""
Core pipeline orchestrator with concurrent processing.

This module now owns the pipeline state and persistence boundary.
Batch execution and single-video orchestration live in
``notewise.pipeline._execution``.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.exc import SQLAlchemyError

from notewise._constants import DEFAULT_MODEL
from notewise.config import get_cache_db_path
from notewise.config import settings as config
from notewise.domain.events import EventType, PipelineEvent
from notewise.domain.results import PipelineMetrics, PipelineResult
from notewise.llm.provider import UsageTotals, get_provider
from notewise.pipeline._artifacts import export_transcript, generate_and_write_quiz
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
    "split_transcript_by_chapters",
    "run_pipeline",
    "sanitize_filename",
]


class CorePipeline:
    """Core pipeline state and persistence boundary."""

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
        use_timestamps: bool = False,
        throttle: float = 0.0,
    ):
        self.model = model
        self.output_dir = output_dir or config.default_output_dir
        self.languages = languages or config.default_languages
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
            throttle=throttle,
        )
        self.force = force
        self.quiz = quiz
        self.export_transcript_format = export_transcript
        self.youtube_cookie_file = youtube_cookie_file or config.youtube_cookie_file
        self.use_timestamps = use_timestamps
        self.throttle = throttle
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
        key_name = config.get_api_key_name_for_model(self.model)
        if key_name and not os.environ.get(key_name):
            logger.error(f"Missing API Key for {self.model}. Expected: {key_name}")
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
                allow_existing_base or not base.exists()
            )
            target = base if base_available else suffix_output_target(base, video_id)
            self._reserved_output_targets.add(target)
            return target

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
    on_event: Callable[[PipelineEvent], None] | None = None,
) -> PipelineResult:
    pipeline = CorePipeline(
        model=model,
        output_dir=output_dir,
    )
    return await pipeline.run(video_ids, on_event=on_event)
