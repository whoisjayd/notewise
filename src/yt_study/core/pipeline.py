"""
Core pipeline orchestrator with concurrent processing.

This module provides the single entry point for the pipeline.
All UI concerns are handled externally via event callbacks.
No Rich, no Console, no Dashboard imports here.
"""

import asyncio
import logging
import os
import re
import time
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from aiolimiter import AsyncLimiter
from sqlalchemy.exc import SQLAlchemyError

from ..db import (
    DatabaseManager,
    Video,
    build_cache_db_path,
)
from .config import config
from .llm.generator import StudyMaterialGenerator
from .llm.providers import UsageTotals, get_provider
from .youtube.metadata import (
    PublicAccessRequiredError,
    get_video_chapters,
    get_video_duration,
    get_video_title,
)
from .youtube.transcript import (
    TranscriptError,
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
_GLOBAL_YOUTUBE_LIMITERS: dict[tuple[int, int], AsyncLimiter] = {}


def _get_global_youtube_limiter(requests_per_minute: int) -> AsyncLimiter:
    """
    Return a shared AsyncLimiter for the current loop and rate cap.

    Sharing by `(loop, rate)` lets concurrent CorePipeline instances in the
    same event loop throttle together while avoiding undefined cross-loop reuse.
    """
    try:
        loop_key = id(asyncio.get_running_loop())
    except RuntimeError:
        # Fallback for synchronous contexts (for example, object construction in
        # tests before an event loop is running).
        loop_key = -1

    key = (loop_key, requests_per_minute)
    limiter = _GLOBAL_YOUTUBE_LIMITERS.get(key)
    if limiter is None:
        limiter = AsyncLimiter(max_rate=requests_per_minute, time_period=60)
        _GLOBAL_YOUTUBE_LIMITERS[key] = limiter
    return limiter


def dedupe_video_ids(video_ids: list[str]) -> list[str]:
    """Return video IDs in first-seen order with duplicates removed."""
    return list(dict.fromkeys(video_ids))


class EventType(Enum):
    """Event types emitted by the pipeline."""

    METADATA_START = "metadata_start"
    METADATA_FETCHED = "metadata_fetched"
    TRANSCRIPT_FETCHING = "transcript_fetching"
    TRANSCRIPT_FETCHED = "transcript_fetched"
    GENERATION_START = "generation_start"
    CHUNK_GENERATING = "chunk_generating"
    GENERATION_COMBINING = "generation_combining"
    CHAPTER_GENERATING = "chapter_generating"
    CHAPTER_CHUNK_GENERATING = "chapter_chunk_generating"
    CHAPTER_COMBINING = "chapter_combining"
    QUIZ_GENERATING = "quiz_generating"
    QUIZ_CHUNK_GENERATING = "quiz_chunk_generating"
    QUIZ_COMBINING = "quiz_combining"
    QUIZ_COMPLETE = "quiz_complete"
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
    metrics: "PipelineMetrics" = field(default_factory=lambda: PipelineMetrics())


@dataclass
class PipelineMetrics:
    """Aggregated token and timing metrics for one pipeline run."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    transcript_seconds: float = 0.0
    generation_seconds: float = 0.0

    def add_from(self, other: "PipelineMetrics") -> None:
        """Accumulate another metrics snapshot into this instance."""
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens
        self.cost_usd += other.cost_usd
        self.transcript_seconds += other.transcript_seconds
        self.generation_seconds += other.generation_seconds

    def copy(self) -> "PipelineMetrics":
        """Return an immutable snapshot copy."""
        return PipelineMetrics(
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            total_tokens=self.total_tokens,
            cost_usd=self.cost_usd,
            transcript_seconds=self.transcript_seconds,
            generation_seconds=self.generation_seconds,
        )


@dataclass
class PipelineSharedState:
    """Shared coordination primitives for multi-pipeline batch processing."""

    semaphore: asyncio.Semaphore
    output_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    reserved_output_targets: set[Path] = field(default_factory=set)


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
    # Truncation can reintroduce a trailing space or dot.
    name = name.rstrip(" .")
    # Reject empty or dot-only names
    if not name:
        return "untitled"
    # Reject Windows reserved device names (case-insensitive, with or without extension)
    if _RESERVED.match(name):
        name = f"_{name}"[:100].rstrip(" .")
        if not name:
            return "untitled"
    return name


def _format_user_error(error: Exception) -> str:
    """Convert internal exceptions into non-technical user-facing failures."""
    if isinstance(error, PublicAccessRequiredError):
        return str(error)

    if isinstance(error, YouTubeIPBlockError):
        return (
            "YouTube is temporarily blocking requests from this network. "
            "Try again later, lower the request rate, or switch networks."
        )

    if isinstance(error, TranscriptError):
        error_text = str(error).lower()
        if (
            "transcripts are disabled" in error_text
            or "no transcript" in error_text
            or "could not fetch transcript" in error_text
            or "no usable transcript" in error_text
        ):
            return (
                "We couldn't get a usable transcript for this video. "
                "Make sure captions are available, try another language, "
                "or use a different video."
            )
        return "We couldn't get a usable transcript for this video."

    error_text = str(error).strip().lower()

    if "timeout" in error_text or "timed out" in error_text:
        return "The request timed out while processing this video. Please try again."

    if (
        "network" in error_text
        or "connection reset" in error_text
        or "connection aborted" in error_text
        or "connection refused" in error_text
    ):
        return "A network problem interrupted processing. Please try again."

    if (
        "rate limit" in error_text
        or "too many requests" in error_text
        or " 429" in error_text
    ):
        return (
            "The upstream service is rate-limiting requests right now. "
            "Please try again later."
        )

    if (
        "api key" in error_text
        or "unauthorized" in error_text
        or "authentication" in error_text
    ):
        return (
            "The selected model or provider is not configured correctly. "
            "Check your API key and try again."
        )

    if "permission denied" in error_text or "access is denied" in error_text:
        return (
            "yt-study could not write the output files. "
            "Check the output folder permissions and try again."
        )

    return (
        "We couldn't process this video. "
        "Check the current session log for technical details."
    )


class CorePipeline:
    """
    Core pipeline orchestrator.

    Pure business logic - no UI concerns.
    Single public entry point: `run()`

    Communicates progress via event callbacks.
    """

    def __init__(
        self,
        model: str = "gemini/gemini-2.5-flash",
        output_dir: Path | None = None,
        languages: list[str] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        force: bool = False,
        quiz: bool = False,
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
        self.db = DatabaseManager.get_instance(self._cache_db_path())

    def _get_youtube_request_limiter(self) -> AsyncLimiter:
        """Return the shared limiter for this pipeline's configured rate."""
        return _get_global_youtube_limiter(self.youtube_requests_per_minute)

    async def _acquire_youtube_request_slot(self) -> None:
        """Acquire one slot from the global YouTube request rate limiter."""
        async with self._get_youtube_request_limiter():
            return

    async def _rate_limited_to_thread(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Run blocking YouTube work in a thread after passing the global limiter.

        The limiter controls request rate while `asyncio.to_thread` keeps
        blocking I/O off the event loop.
        """
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
        return build_cache_db_path()

    async def _get_cached_video(self, video_id: str) -> Video | None:
        """Return cached metadata for a video when present."""
        try:
            return await asyncio.to_thread(self.db.get_video, video_id)
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
            await asyncio.to_thread(
                self.db.upsert_video_cache,
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

                # Fetch all metadata concurrently; title failure is non-fatal
                meta_results = await asyncio.gather(
                    self._rate_limited_to_thread(get_video_title, video_id),
                    self._rate_limited_to_thread(get_video_duration, video_id),
                    self._rate_limited_to_thread(get_video_chapters, video_id),
                    return_exceptions=True,
                )
                raw_title, duration, chapters = meta_results

                for meta_value in meta_results:
                    if isinstance(meta_value, PublicAccessRequiredError):
                        raise meta_value

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

                # --- Transcript Phase ---
                emit(EventType.TRANSCRIPT_FETCHING, video_id, title=title)

                transcript_start = time.perf_counter()
                transcript_obj = await fetch_transcript(
                    video_id,
                    self.languages,
                    on_request=self._acquire_youtube_request_slot,
                )
                transcript_text = transcript_obj.to_text()
                transcript_seconds = time.perf_counter() - transcript_start

                emit(EventType.TRANSCRIPT_FETCHED, video_id, title=title)

                # --- Generation Strategy ---
                use_chapters = bool(
                    duration > config.chapter_generation_min_duration and chapters
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

            except YouTubeIPBlockError as e:
                error_msg = _format_user_error(e)
                logger.error(f"IP Block for {video_id}: {e}")
                self.errors[video_id] = error_msg
                emit(EventType.VIDEO_FAILED, video_id, error=error_msg)
                return False

            except PublicAccessRequiredError as e:
                error_msg = str(e)
                logger.error(f"Cannot process {video_id}: {e}")
                self.errors[video_id] = error_msg
                emit(EventType.VIDEO_FAILED, video_id, error=error_msg)
                return False

            except Exception as e:
                error_msg = _format_user_error(e)
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
            metrics=self._run_metrics.copy(),
        )


async def run_pipeline(
    video_ids: list[str],
    output_dir: Path | None = None,
    model: str = "gemini/gemini-2.5-flash",
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
