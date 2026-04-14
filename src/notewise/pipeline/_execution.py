"""Pipeline execution helpers for single-video and batch processing."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path
from typing import Any, cast

import structlog

from notewise.config import settings as config
from notewise.domain.events import EventType, PipelineEvent
from notewise.domain.results import PipelineMetrics, PipelineResult
from notewise.errors import (
    IPBlockError,
    VideoUnavailableError,
    format_user_error,
)
from notewise.pipeline._state import dedupe_video_ids
from notewise.utils import sanitize_filename

from . import core as pipeline_module


logger = structlog.get_logger(__name__)


async def process_single_video(
    pipeline: Any,
    video_id: str,
    on_event: Callable[[PipelineEvent], None] | None = None,
) -> bool:
    """Process a single video: fetch transcript and generate study notes."""

    emit = pipeline._emit_event(on_event)
    async with pipeline.semaphore:
        reserved_targets: list[Path] = []
        try:
            emit(EventType.METADATA_START, video_id)

            cached_video = (
                None if pipeline.force else await pipeline._get_cached_video(video_id)
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

            await pipeline._acquire_youtube_request_slot()
            meta = await pipeline_module.get_video_metadata(
                video_id,
                pipeline.youtube_cookie_file,
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

            emit(EventType.TRANSCRIPT_FETCHING, video_id, title=title)

            transcript_start = time.perf_counter()
            transcript_obj = await pipeline_module.fetch_transcript(
                video_id,
                pipeline.languages,
                on_request=pipeline._acquire_youtube_request_slot,
                cookie_file=pipeline.youtube_cookie_file,
            )
            transcript_text = transcript_obj.to_text()
            transcript_seconds = time.perf_counter() - transcript_start

            emit(EventType.TRANSCRIPT_FETCHED, video_id, title=title)

            use_chapters = bool(
                duration > config.chapter_generation_min_duration and chapters
            )
            output_target: Path | None = None
            transcript_output_dir = pipeline.output_dir

            generation_start = time.perf_counter()
            usage_context = nullcontext(pipeline_module.UsageTotals())
            usage_collector = getattr(pipeline.provider, "collect_usage", None)
            if callable(usage_collector):
                candidate = usage_collector()
                if hasattr(candidate, "__enter__") and hasattr(candidate, "__exit__"):
                    usage_context = candidate

            with usage_context as raw_usage_totals:
                if use_chapters:
                    chapter_transcripts = pipeline_module.split_transcript_by_chapters(
                        transcript_obj, chapters
                    )

                    if not chapter_transcripts:
                        logger.warning(
                            f"No usable chapter transcripts found for {video_id}; "
                            "falling back to single-file generation."
                        )
                        use_chapters = False

                if use_chapters:
                    output_target = await pipeline._reserve_output_target(
                        pipeline.output_dir / sanitize_filename(title),
                        video_id,
                        allow_existing_base=pipeline.force
                        or current_cached_video is not None,
                    )
                    reserved_targets.append(output_target)
                    output_target.mkdir(parents=True, exist_ok=True)
                    transcript_output_dir = output_target

                    total_chapters = len(chapter_transcripts)
                    ordered_chapters = list(chapter_transcripts.items())
                    chapters_to_generate: dict[str, str] = {}
                    chapter_targets: list[tuple[str, Path, int]] = []
                    chapter_start_seconds: dict[str, int] = {}
                    seen_titles: dict[str, int] = {}

                    for chapter in chapters:
                        seen_titles[chapter.title] = seen_titles.get(chapter.title, 0) + 1
                        occurrence = seen_titles[chapter.title]
                        unique_title = (
                            chapter.title
                            if occurrence == 1
                            else f"{chapter.title} ({occurrence})"
                        )
                        chapter_start_seconds[unique_title] = chapter.start_seconds

                    for i, (chap_title, chap_text) in enumerate(ordered_chapters, 1):
                        safe_chapter = sanitize_filename(chap_title)
                        chapter_file = output_target / f"{i:02d}_{safe_chapter}.md"
                        chapter_targets.append(
                            (chap_title, chapter_file, chapter_start_seconds.get(chap_title, 0))
                        )

                        if not pipeline.force and chapter_file.exists():
                            logger.info(
                                f"Skipping chapter {i}/{total_chapters}"
                                f" '{chap_title[:40]}' (already exists)"
                            )
                            continue

                        chapters_to_generate[chap_title] = chap_text

                    if chapters_to_generate:
                        chapter_indices = {
                            chapter_title: index
                            for index, (chapter_title, _) in enumerate(
                                ordered_chapters,
                                start=1,
                            )
                        }

                        def _on_chapter_start(
                            index: int,
                            _total: int,
                        ) -> None:
                            chapter_title = list(chapters_to_generate.keys())[index - 1]
                            emit(
                                EventType.CHAPTER_GENERATING,
                                video_id,
                                title=title,
                                chapter_number=chapter_indices[chapter_title],
                                total_chapters=total_chapters,
                            )

                        original_generate_single = (
                            pipeline.generator.generate_single_chapter_notes
                        )

                        async def _generate_single_chapter_notes_with_events(
                            chapter_title: str,
                            chapter_text: str,
                            on_chunk: Callable[[int, int], None] | None = None,
                            on_combine: Callable[[int], None] | None = None,
                        ) -> str:
                            chapter_number = chapter_indices[chapter_title]

                            def _on_chapter_chunk(chunk_num: int, total: int) -> None:
                                emit(
                                    EventType.CHAPTER_CHUNK_GENERATING,
                                    video_id,
                                    title=title,
                                    chapter_number=chapter_number,
                                    total_chapters=total_chapters,
                                    chunk_number=chunk_num,
                                    total_chunks=total,
                                )
                                if on_chunk:
                                    on_chunk(chunk_num, total)

                            def _on_chapter_combine(total_parts: int) -> None:
                                emit(
                                    EventType.CHAPTER_COMBINING,
                                    video_id,
                                    title=title,
                                    chapter_number=chapter_number,
                                    total_chapters=total_chapters,
                                    total_chunks=total_parts,
                                )
                                if on_combine:
                                    on_combine(total_parts)

                            try:
                                return cast(
                                    str,
                                    await original_generate_single(
                                        chapter_title=chapter_title,
                                        chapter_text=chapter_text,
                                        on_chunk=_on_chapter_chunk,
                                        on_combine=_on_chapter_combine,
                                    ),
                                )
                            finally:
                                emit(
                                    EventType.CHAPTER_COMPLETE,
                                    video_id,
                                    title=title,
                                    chapter_number=chapter_number,
                                    total_chapters=total_chapters,
                                )

                        pipeline.generator.generate_single_chapter_notes = (
                            _generate_single_chapter_notes_with_events
                        )
                        try:
                            generate_chapter_notes = (
                                pipeline.generator.generate_chapter_notes_concurrent
                            )
                            generated_chapter_notes = await generate_chapter_notes(
                                chapters_to_generate,
                                max_concurrent=config.max_concurrent_chapters,
                                semaphore=pipeline._chapter_semaphore,
                                video_title=title,
                                on_chapter_start=_on_chapter_start,
                            )
                        finally:
                            pipeline.generator.generate_single_chapter_notes = (
                                original_generate_single
                            )

                        for chapter_title, chapter_file, start_seconds in chapter_targets:
                            notes = generated_chapter_notes.get(chapter_title)
                            if notes is None:
                                continue
                            if pipeline.timestamps:
                                notes = pipeline_module.prefix_chapter_heading_with_timestamp(
                                    notes,
                                    chapter_title,
                                    start_seconds,
                                )
                            chapter_file.write_text(notes, encoding="utf-8")
                else:
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

                    notes = await pipeline.generator.generate_study_notes(
                        transcript_text,
                        video_title=title,
                        on_chunk=_on_chunk,
                        on_combine=_on_combine,
                    )

                    output_target = await pipeline._reserve_output_target(
                        pipeline.output_dir / f"{sanitize_filename(title)}.md",
                        video_id,
                        allow_existing_base=pipeline.force
                        or current_cached_video is not None,
                    )
                    reserved_targets.append(output_target)
                    output_target.parent.mkdir(parents=True, exist_ok=True)
                    output_target.write_text(notes, encoding="utf-8")
                    transcript_output_dir = output_target.parent

                if pipeline.export_transcript_format:
                    pipeline._export_transcript(
                        transcript_obj,
                        title,
                        transcript_output_dir,
                        video_id,
                    )

                if pipeline.quiz and output_target is not None:
                    quiz_output_dir = (
                        output_target if use_chapters else pipeline.output_dir
                    )
                    quiz_name = (
                        output_target.name if use_chapters else output_target.stem
                    )
                    await pipeline_module.generate_and_write_quiz(
                        pipeline.generator,
                        transcript_text,
                        quiz_name,
                        output_dir=quiz_output_dir,
                        emit=emit,
                        video_id=video_id,
                        title=title,
                    )

            usage_totals = pipeline_module.coerce_usage_totals(raw_usage_totals)
            generation_seconds = time.perf_counter() - generation_start
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

        except IPBlockError as error:
            error_msg = format_user_error(error)
            logger.error(f"IP Block for {video_id}: {error}")
            pipeline.errors[video_id] = error_msg
            emit(EventType.VIDEO_FAILED, video_id, error=error_msg)
            return False

        except VideoUnavailableError as error:
            error_msg = str(error)
            logger.error(f"Cannot process {video_id}: {error}")
            pipeline.errors[video_id] = error_msg
            emit(EventType.VIDEO_FAILED, video_id, error=error_msg)
            return False

        except Exception as error:
            error_msg = format_user_error(error)
            logger.error(f"Failed to process {video_id}: {error}", exc_info=True)
            pipeline.errors[video_id] = error_msg
            emit(EventType.VIDEO_FAILED, video_id, error=error_msg)
            return False
        finally:
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
        errors = {vid: "Missing API key" for vid in video_ids}
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

    tasks = [
        process_single_video(pipeline, video_id, on_event=on_event)
        for video_id in video_ids
    ]

    raw_results = await asyncio.gather(*tasks, return_exceptions=True)
    results: list[bool] = []
    for vid, result in zip(video_ids, raw_results, strict=False):
        if isinstance(result, BaseException):
            err_msg = format_user_error(
                result if isinstance(result, Exception) else Exception(str(result))
            )
            pipeline.errors[vid] = err_msg
            emit(EventType.VIDEO_FAILED, vid, error=err_msg)
            results.append(False)
        else:
            results.append(bool(result))

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
