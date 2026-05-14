"""Pipeline execution helpers for single-video and batch processing."""

from __future__ import annotations

import asyncio
import time
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from notewise._constants import (
    CHAPTER_MARKDOWN_FILE_EXTENSION,
    DEFAULT_NOTES_OUTPUT_FORMAT,
    EMPTY_TRANSCRIPT_ERROR,
    MIN_VIDEO_WORKER_COUNT,
    OUTPUT_METADATA_CHAPTER_FILES_KEY,
    PDF_NOTES_OUTPUT_FORMAT,
    QUIZ_MARKDOWN_FILE_SUFFIX,
    TRANSCRIPT_JSON_OUTPUT_FORMAT,
    TRANSCRIPT_TEXT_OUTPUT_FORMAT,
)
from notewise.domain.events import EventType, PipelineEvent
from notewise.domain.results import PipelineMetrics, PipelineResult
from notewise.errors import (
    IPBlockError,
    TranscriptUnavailableError,
    VideoUnavailableError,
    format_user_error,
)
from notewise.llm.provider import LLMProvider, UsageTotals
from notewise.logging import make_log_safe_text
from notewise.pipeline._artifacts import generate_and_write_quiz
from notewise.pipeline._chapter_outputs import generate_chapter_outputs
from notewise.pipeline._documents import get_output_extension
from notewise.pipeline._helpers import coerce_usage_totals
from notewise.pipeline._output_rendering import render_notes_with_warning
from notewise.pipeline._state import dedupe_video_ids
from notewise.utils import sanitize_filename
from notewise.youtube.metadata import (
    get_video_details,
    video_metadata_from_details,
)
from notewise.youtube.transcript import (
    fetch_transcript,
    split_transcript_by_chapters_with_metadata,
)


if TYPE_CHECKING:
    from collections.abc import Callable
    from tempfile import TemporaryDirectory


logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class _VideoInputs:
    title: str
    duration: int
    chapters: list[Any]
    transcript: Any
    transcript_text: str
    transcript_seconds: float


@dataclass(frozen=True)
class _GeneratedOutputs:
    rendered_output_targets: dict[str, Path]
    render_warning: str | None
    output_target: Path | None
    transcript_output_dir: Path
    chapter_directory_output: bool
    temporary_chapter_directory: TemporaryDirectory[str] | None


def _notes_artifact_exists(target: Path, output_format: str) -> bool:
    if target.exists():
        return True
    return (
        output_format == PDF_NOTES_OUTPUT_FORMAT
        and target.with_suffix(CHAPTER_MARKDOWN_FILE_EXTENSION).exists()
    )


def _cached_video_has_requested_artifacts(
    pipeline: Any,
    video_id: str,
    title: str,
) -> bool:
    safe_title = sanitize_filename(title or video_id)
    output_dir = pipeline.output_dir
    transcript_dir = output_dir

    if pipeline.chapter_directory_output:
        chapter_dir = output_dir / safe_title
        if not pipeline._is_reusable_directory_output(chapter_dir, video_id):
            return False
        if not _chapter_directory_has_complete_manifest(
            pipeline,
            chapter_dir,
            video_id,
        ):
            return False
        transcript_dir = chapter_dir

    for output_format in pipeline.output_formats:
        if (
            pipeline.chapter_directory_output
            and output_format == DEFAULT_NOTES_OUTPUT_FORMAT
        ):
            continue
        output_extension = get_output_extension(output_format)
        artifact = output_dir / f"{safe_title}{output_extension}"
        if not _notes_artifact_exists(artifact, output_format):
            return False

    if pipeline.export_transcript_format:
        transcript_extension = (
            TRANSCRIPT_JSON_OUTPUT_FORMAT
            if pipeline.export_transcript_format == TRANSCRIPT_JSON_OUTPUT_FORMAT
            else TRANSCRIPT_TEXT_OUTPUT_FORMAT
        )
        transcript_artifact = transcript_dir / (
            f"{safe_title}_transcript.{transcript_extension}"
        )
        if not transcript_artifact.exists():
            return False

    if pipeline.quiz:
        quiz_dir = transcript_dir if pipeline.chapter_directory_output else output_dir
        quiz_name = quiz_dir.name if pipeline.chapter_directory_output else safe_title
        if not (
            quiz_dir / f"{sanitize_filename(quiz_name)}{QUIZ_MARKDOWN_FILE_SUFFIX}"
        ).exists():
            return False

    return True


def _chapter_directory_has_complete_manifest(
    pipeline: Any,
    chapter_dir: Path,
    video_id: str,
) -> bool:
    metadata_reader = getattr(pipeline, "_read_output_target_metadata", None)
    if not callable(metadata_reader):
        return False

    metadata: Any = metadata_reader(chapter_dir, video_id)
    if not isinstance(metadata, dict):
        return False
    chapter_files = metadata.get(OUTPUT_METADATA_CHAPTER_FILES_KEY)
    if not isinstance(chapter_files, list) or not chapter_files:
        return False

    return all(
        isinstance(filename, str)
        and Path(filename).name == filename
        and (chapter_dir / filename).is_file()
        for filename in chapter_files
    )


async def _fetch_video_inputs(
    pipeline: Any,
    video_id: str,
    emit: Callable[..., None],
) -> _VideoInputs:
    await pipeline._acquire_youtube_request_slot()
    video_data = await get_video_details(
        video_id,
        pipeline.youtube_cookie_file,
    )
    meta = video_metadata_from_details(video_id, video_data)
    title: str = meta.title
    chapters = meta.chapters

    emit(
        EventType.METADATA_FETCHED,
        video_id,
        title=title,
        total_chapters=len(chapters) if chapters else 0,
    )

    emit(EventType.TRANSCRIPT_FETCHING, video_id, title=title)

    transcript_start = time.perf_counter()
    transcript_kwargs: dict[str, Any] = {
        "on_request": pipeline._acquire_youtube_request_slot,
        "cookie_file": pipeline.youtube_cookie_file,
    }
    if video_data is not None:
        transcript_kwargs["video_data"] = video_data
    transcript = await fetch_transcript(
        video_id,
        pipeline.languages,
        **transcript_kwargs,
    )
    transcript_text = transcript.to_text()
    if not transcript_text.strip():
        raise TranscriptUnavailableError(EMPTY_TRANSCRIPT_ERROR)
    transcript_seconds = time.perf_counter() - transcript_start

    emit(EventType.TRANSCRIPT_FETCHED, video_id, title=title)

    return _VideoInputs(
        title=title,
        duration=meta.duration,
        chapters=chapters,
        transcript=transcript,
        transcript_text=transcript_text,
        transcript_seconds=transcript_seconds,
    )


def _usage_context(provider: Any) -> Any:
    usage_context = nullcontext(UsageTotals())
    usage_collector = getattr(provider, "collect_usage", None)
    if not callable(usage_collector):
        if hasattr(usage_collector, "__enter__") and hasattr(
            usage_collector,
            "__exit__",
        ):
            return usage_collector
        return usage_context
    if not (
        isinstance(getattr(usage_collector, "__self__", None), LLMProvider)
        and getattr(usage_collector, "__func__", None) is LLMProvider.collect_usage
    ):
        return usage_context

    candidate = usage_collector()
    if hasattr(candidate, "__enter__") and hasattr(candidate, "__exit__"):
        return candidate
    return usage_context


async def _generate_single_file_output(
    pipeline: Any,
    video_id: str,
    title: str,
    transcript_text: str,
    current_cached_video: Any,
    reserved_targets: list[Path],
    emit: Callable[..., None],
) -> tuple[dict[str, Path], str | None, Path, Path]:
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
            phase_label="Stitching",
        )

    notes = await pipeline.generator.generate_study_notes(
        transcript_text,
        video_title=title,
        on_chunk=_on_chunk,
        on_combine=_on_combine,
    )

    rendered_output_targets: dict[str, Path] = {}
    for output_format in pipeline.output_formats:
        current_output_target = await pipeline._reserve_output_target(
            pipeline.output_dir
            / (f"{sanitize_filename(title)}{get_output_extension(output_format)}"),
            video_id,
            allow_existing_base=pipeline.force or current_cached_video is not None,
        )
        reserved_targets.append(current_output_target)
        rendered_output_targets[output_format] = current_output_target

    rendered_output_targets, render_warning = render_notes_with_warning(
        notes,
        title,
        rendered_output_targets,
        pipeline.target_language,
    )
    output_target = rendered_output_targets[pipeline.output_format]
    return rendered_output_targets, render_warning, output_target, output_target.parent


async def _record_successful_video(
    pipeline: Any,
    *,
    video_id: str,
    title: str,
    duration: int,
    transcript_text: str,
    transcript_language: str,
    transcript_seconds: float,
    generation_seconds: float,
    raw_usage_totals: Any,
) -> PipelineMetrics:
    usage_totals = coerce_usage_totals(raw_usage_totals)
    video_metrics = PipelineMetrics(
        prompt_tokens=usage_totals.prompt_tokens,
        completion_tokens=usage_totals.completion_tokens,
        total_tokens=usage_totals.total_tokens,
        cost_usd=usage_totals.cost_usd,
        transcript_seconds=transcript_seconds,
        generation_seconds=generation_seconds,
    )
    await pipeline._record_metrics(video_metrics)
    await pipeline._persist_video_cache(
        video_id=video_id,
        title=title,
        duration=duration,
        transcript_text=transcript_text,
        transcript_language=transcript_language,
        prompt_tokens=video_metrics.prompt_tokens,
        completion_tokens=video_metrics.completion_tokens,
        total_tokens=video_metrics.total_tokens,
        cost_usd=video_metrics.cost_usd,
        transcript_seconds=video_metrics.transcript_seconds,
        generation_seconds=video_metrics.generation_seconds,
    )
    return video_metrics


def _get_chapter_transcripts(
    video_id: str,
    video_inputs: _VideoInputs,
) -> dict[str, Any] | None:
    if not video_inputs.chapters:
        return None

    chapter_transcripts = split_transcript_by_chapters_with_metadata(
        video_inputs.transcript,
        video_inputs.chapters,
    )
    if chapter_transcripts:
        return chapter_transcripts

    logger.warning(
        f"No usable chapter transcripts found for {video_id}; "
        "falling back to single-file generation."
    )
    return None


async def _generate_video_outputs(
    pipeline: Any,
    video_id: str,
    video_inputs: _VideoInputs,
    current_cached_video: Any,
    reserved_targets: list[Path],
    emit: Callable[..., None],
) -> _GeneratedOutputs:
    chapter_transcripts = _get_chapter_transcripts(video_id, video_inputs)
    if chapter_transcripts is not None:
        (
            rendered_output_targets,
            render_warning,
            output_target,
            transcript_output_dir,
            temporary_chapter_directory,
        ) = await generate_chapter_outputs(
            pipeline,
            video_id,
            video_inputs.title,
            chapter_transcripts,
            current_cached_video,
            reserved_targets,
            emit,
        )
        return _GeneratedOutputs(
            rendered_output_targets=rendered_output_targets,
            render_warning=render_warning,
            output_target=output_target,
            transcript_output_dir=transcript_output_dir,
            chapter_directory_output=pipeline.chapter_directory_output,
            temporary_chapter_directory=temporary_chapter_directory,
        )

    (
        rendered_output_targets,
        render_warning,
        output_target,
        transcript_output_dir,
    ) = await _generate_single_file_output(
        pipeline,
        video_id,
        video_inputs.title,
        video_inputs.transcript_text,
        current_cached_video,
        reserved_targets,
        emit,
    )
    return _GeneratedOutputs(
        rendered_output_targets=rendered_output_targets,
        render_warning=render_warning,
        output_target=output_target,
        transcript_output_dir=transcript_output_dir,
        chapter_directory_output=False,
        temporary_chapter_directory=None,
    )


async def _write_optional_artifacts(
    pipeline: Any,
    video_id: str,
    video_inputs: _VideoInputs,
    outputs: _GeneratedOutputs,
    emit: Callable[..., None],
) -> None:
    if pipeline.export_transcript_format:
        pipeline._export_transcript(
            video_inputs.transcript,
            video_inputs.title,
            outputs.transcript_output_dir,
            video_id,
        )

    if not pipeline.quiz or outputs.output_target is None:
        return

    quiz_output_dir = (
        outputs.transcript_output_dir
        if outputs.chapter_directory_output
        else pipeline.output_dir
    )
    quiz_name = (
        outputs.transcript_output_dir.name
        if outputs.chapter_directory_output
        else outputs.output_target.stem
    )
    await generate_and_write_quiz(
        pipeline.generator,
        video_inputs.transcript_text,
        quiz_name,
        output_dir=quiz_output_dir,
        emit=emit,
        video_id=video_id,
        title=video_inputs.title,
    )


async def process_single_video(
    pipeline: Any,
    video_id: str,
    on_event: Callable[[PipelineEvent], None] | None = None,
) -> bool:
    """Process a single video: fetch transcript and generate study notes."""

    emit = pipeline._emit_event(on_event)
    async with pipeline.semaphore:
        reserved_targets: list[Path] = []
        temporary_chapter_directory: TemporaryDirectory[str] | None = None
        try:
            emit(EventType.METADATA_START, video_id)

            cached_video = (
                None if pipeline.force else await pipeline._get_cached_video(video_id)
            )
            if cached_video is not None and _cached_video_has_requested_artifacts(
                pipeline,
                video_id,
                cached_video.title,
            ):
                logger.info(f"Skipping already-processed video: {video_id}")
                emit(
                    EventType.VIDEO_SKIPPED,
                    video_id,
                    title=cached_video.title or video_id,
                )
                return True
            if cached_video is not None:
                logger.info(
                    "Cached video is missing requested artifacts; regenerating",
                    video_id=video_id,
                )

            current_cached_video = cached_video

            video_inputs = await _fetch_video_inputs(pipeline, video_id, emit)
            title = video_inputs.title
            transcript_text = video_inputs.transcript_text
            transcript_seconds = video_inputs.transcript_seconds

            generation_start = time.perf_counter()
            usage_context = _usage_context(pipeline.provider)

            with usage_context as raw_usage_totals:
                outputs = await _generate_video_outputs(
                    pipeline,
                    video_id,
                    video_inputs,
                    current_cached_video,
                    reserved_targets,
                    emit,
                )
                temporary_chapter_directory = outputs.temporary_chapter_directory
                await _write_optional_artifacts(
                    pipeline,
                    video_id,
                    video_inputs,
                    outputs,
                    emit,
                )

            generation_seconds = time.perf_counter() - generation_start
            await _record_successful_video(
                pipeline,
                video_id=video_id,
                title=title,
                duration=video_inputs.duration,
                transcript_text=transcript_text,
                transcript_language=video_inputs.transcript.language_code,
                transcript_seconds=transcript_seconds,
                generation_seconds=generation_seconds,
                raw_usage_totals=raw_usage_totals,
            )
            emit(
                EventType.GENERATION_COMPLETE,
                video_id,
                title=title,
                error=outputs.render_warning,
                output_path=outputs.output_target,
            )
            emit(EventType.VIDEO_SUCCESS, video_id, title=title)
            return True

        except IPBlockError as error:
            error_msg = format_user_error(error)
            logger.error(make_log_safe_text(f"IP Block for {video_id}: {error}"))
            pipeline.errors[video_id] = error_msg
            emit(EventType.VIDEO_FAILED, video_id, error=error_msg)
            return False

        except VideoUnavailableError as error:
            error_msg = str(error)
            logger.error(make_log_safe_text(f"Cannot process {video_id}: {error}"))
            pipeline.errors[video_id] = error_msg
            emit(EventType.VIDEO_FAILED, video_id, error=error_msg)
            return False

        except Exception as error:
            error_msg = format_user_error(error)
            logger.error(
                make_log_safe_text(f"Failed to process {video_id}: {error}"),
                exc_info=True,
            )
            pipeline.errors[video_id] = error_msg
            emit(EventType.VIDEO_FAILED, video_id, error=error_msg)
            return False
        finally:
            if temporary_chapter_directory is not None:
                temporary_chapter_directory.cleanup()
            for target in reserved_targets:
                await pipeline._release_output_target(target)


async def run_pipeline(
    pipeline: Any,
    video_ids: list[str],
    on_event: Callable[[PipelineEvent], None] | None = None,
) -> PipelineResult:
    """Process a list of video IDs concurrently."""

    video_ids = dedupe_video_ids(video_ids)

    if not pipeline._check_api_key():
        errors = dict.fromkeys(video_ids, "Missing API key")
        if on_event is not None:
            emit = pipeline._emit_event(on_event)
            emit(EventType.PIPELINE_START, "")
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

    emit = pipeline._emit_event(on_event)
    emit(EventType.PIPELINE_START, "")

    pipeline.errors.clear()
    pipeline._run_metrics = PipelineMetrics()

    results: list[bool] = [False] * len(video_ids)
    next_video_index = 0
    worker_count = min(
        len(video_ids),
        max(
            MIN_VIDEO_WORKER_COUNT,
            int(getattr(pipeline, "max_concurrent_videos", MIN_VIDEO_WORKER_COUNT)),
        ),
    )

    async def _worker() -> None:
        nonlocal next_video_index
        while next_video_index < len(video_ids):
            index = next_video_index
            next_video_index += 1
            vid = video_ids[index]
            try:
                result = await process_single_video(
                    pipeline,
                    vid,
                    on_event=on_event,
                )
            except asyncio.CancelledError:
                raise
            except Exception as error:
                err_msg = format_user_error(error)
                pipeline.errors[vid] = err_msg
                emit(EventType.VIDEO_FAILED, vid, error=err_msg)
                results[index] = False
            else:
                results[index] = bool(result)

    await asyncio.gather(*(_worker() for _ in range(worker_count)))

    success_count = sum(1 for result in results if result is True)
    failure_count = len(video_ids) - success_count

    emit(EventType.PIPELINE_COMPLETE, "")

    return PipelineResult(
        success_count=success_count,
        failure_count=failure_count,
        total_count=len(video_ids),
        video_ids=video_ids,
        errors=dict(pipeline.errors),
        metrics=pipeline._run_metrics.copy(),
    )
