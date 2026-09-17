"""Chapter-output generation helpers for pipeline execution."""

from __future__ import annotations

import contextlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import structlog

from notewise._constants import (
    CHAPTER_MARKDOWN_FILE_EXTENSION,
    CHAPTER_RESUME_CACHE_DIR_NAME,
    DEFAULT_NOTES_OUTPUT_FORMAT,
)
from notewise.config import get_state_dir
from notewise.config import settings as config
from notewise.domain.events import EventType
from notewise.errors import PartialChapterGenerationError
from notewise.pipeline._artifacts import prefix_chapter_heading_with_timestamp
from notewise.pipeline._documents import build_chapter_bundle, get_output_extension
from notewise.pipeline._output_rendering import render_notes_with_warning
from notewise.utils import sanitize_filename


if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


logger = structlog.get_logger(__name__)


class ChapterPayload(Protocol):
    start_seconds: int
    text: str


class ChapterNotesGenerator(Protocol):
    async def generate_single_chapter_notes(
        self,
        *,
        chapter_title: str,
        chapter_text: str,
        on_chunk: Callable[[int, int], None] | None = None,
        on_combine: Callable[[int], None] | None = None,
    ) -> str: ...

    def generate_chapter_notes_concurrent(
        self,
        chapters: dict[str, str],
        *,
        max_concurrent: int,
        semaphore: object,
        video_title: str,
        on_chapter_start: Callable[[int, int], None] | None = None,
        generate_single: Callable[..., Awaitable[str]] | None = None,
    ) -> Awaitable[dict[str, str]]: ...


class PipelineProtocol(Protocol):
    output_formats: list[str]
    output_format: str
    output_dir: Path
    force: bool
    timestamps: bool
    target_language: str
    chapter_directory_output: bool
    generator: ChapterNotesGenerator
    _chapter_semaphore: object

    async def _reserve_output_target(
        self,
        base: Path,
        video_id: str,
        *,
        allow_existing_base: bool = False,
    ) -> Path: ...

    def _write_output_target_metadata(
        self,
        target: Path,
        video_id: str,
        chapter_files: list[Path] | None = None,
    ) -> None: ...


@dataclass(frozen=True)
class ChapterOutputTargets:
    rendered_output_targets: dict[str, Path]
    output_target: Path | None
    transcript_output_dir: Path
    bundled_chapter_cache_dir: Path | None
    temporary_chapter_dir: Path | None


@dataclass(frozen=True)
class ChapterGenerationPlan:
    chapters_to_generate: dict[str, str]
    chapter_targets: list[tuple[str, int, Path | None]]
    chapter_output_files: dict[str, Path]


def _atomic_write_text(path: Path, text: str) -> None:
    """Write text to path atomically.

    Writes to a sibling temp file, then os.replace()s it into place, so a
    crash mid-write can never leave a truncated file that a later run's
    resume-skip check (see build_chapter_generation_plan) treats as complete.
    """
    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        Path(tmp_path).replace(path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.close(fd)
        Path(tmp_path).unlink(missing_ok=True)
        raise


def _chapter_file_has_timestamps(chapter_file: Path) -> bool:
    """Check if an existing chapter file has timestamp prefixes in its heading."""
    try:
        content = chapter_file.read_text(encoding="utf-8")
        # Look for timestamp pattern [HH:MM:SS] or [MM:SS] at the start of a heading
        heading_pattern = re.compile(
            r"^#{1,6}\s+\[(?:\d{2}:)?\d{2}:\d{2}\]", re.MULTILINE
        )
        return bool(heading_pattern.search(content))
    except (OSError, UnicodeDecodeError):
        # If we can't read the file, treat it as not having timestamps
        return False


def bundled_chapter_output_formats(
    output_formats: list[str],
    chapter_directory_output: bool,
) -> list[str]:
    if not chapter_directory_output:
        return list(output_formats)
    return [
        output_format
        for output_format in output_formats
        if output_format != DEFAULT_NOTES_OUTPUT_FORMAT
    ]


async def prepare_chapter_output_targets(
    pipeline: PipelineProtocol,
    video_id: str,
    title: str,
    current_cached_video: object | None,
    reserved_targets: list[Path],
    chapter_directory_output: bool,
) -> ChapterOutputTargets:
    bundled_output_formats = bundled_chapter_output_formats(
        pipeline.output_formats,
        chapter_directory_output,
    )
    rendered_output_targets: dict[str, Path] = {}
    output_target: Path | None = None
    transcript_output_dir = pipeline.output_dir

    if chapter_directory_output:
        output_target = await pipeline._reserve_output_target(
            pipeline.output_dir / sanitize_filename(title),
            video_id,
            allow_existing_base=pipeline.force or current_cached_video is not None,
        )
        reserved_targets.append(output_target)
        output_target.mkdir(parents=True, exist_ok=True)
        pipeline._write_output_target_metadata(output_target, video_id)
        transcript_output_dir = output_target

    for output_format in bundled_output_formats:
        bundled_output_target = await pipeline._reserve_output_target(
            pipeline.output_dir
            / (f"{sanitize_filename(title)}{get_output_extension(output_format)}"),
            video_id,
            allow_existing_base=pipeline.force or current_cached_video is not None,
        )
        reserved_targets.append(bundled_output_target)
        rendered_output_targets[output_format] = bundled_output_target

    if output_target is None and rendered_output_targets:
        output_target = next(iter(rendered_output_targets.values()))
        transcript_output_dir = output_target.parent

    bundled_chapter_cache_dir: Path | None = None
    temporary_chapter_dir: Path | None = None
    if rendered_output_targets and not chapter_directory_output:
        # Deterministic (keyed by video_id), not a random TemporaryDirectory,
        # so a fresh process invocation after a crash/interrupt can still
        # find and skip chapters a prior run already finished.
        bundled_chapter_cache_dir = (
            get_state_dir() / CHAPTER_RESUME_CACHE_DIR_NAME / video_id
        )
        bundled_chapter_cache_dir.mkdir(parents=True, exist_ok=True)
        temporary_chapter_dir = bundled_chapter_cache_dir

    return ChapterOutputTargets(
        rendered_output_targets=rendered_output_targets,
        output_target=output_target,
        transcript_output_dir=transcript_output_dir,
        bundled_chapter_cache_dir=bundled_chapter_cache_dir,
        temporary_chapter_dir=temporary_chapter_dir,
    )


def build_chapter_generation_plan(
    pipeline: PipelineProtocol,
    title: str,
    ordered_chapters: list[tuple[str, ChapterPayload]],
    total_chapters: int,
    output_target: Path | None,
    temporary_chapter_dir: Path | None,
    chapter_directory_output: bool,
) -> ChapterGenerationPlan:
    chapters_to_generate: dict[str, str] = {}
    chapter_targets: list[tuple[str, int, Path | None]] = []
    chapter_output_files: dict[str, Path] = {}

    for i, (chap_title, chapter_data) in enumerate(ordered_chapters, 1):
        chapter_file: Path | None = None
        safe_chapter = sanitize_filename(chap_title)
        if chapter_directory_output and output_target is not None:
            chapter_file = output_target / (
                f"{i:02d}_{safe_chapter}{CHAPTER_MARKDOWN_FILE_EXTENSION}"
            )
        elif temporary_chapter_dir is not None:
            chapter_file = temporary_chapter_dir / (
                f"{sanitize_filename(title)}_chapter_{i:02d}_{safe_chapter}"
                f"{CHAPTER_MARKDOWN_FILE_EXTENSION}"
            )

        if chapter_file is not None:
            chapter_output_files[chap_title] = chapter_file

        chapter_targets.append((chap_title, chapter_data.start_seconds, chapter_file))

        if chapter_file is not None and not pipeline.force and chapter_file.exists():
            # Only skip if the existing file's timestamp mode matches current setting
            file_has_timestamps = _chapter_file_has_timestamps(chapter_file)
            if file_has_timestamps == pipeline.timestamps:
                logger.info(
                    f"Skipping chapter {i}/{total_chapters}"
                    f" '{chap_title[:40]}' (already exists)"
                )
                continue
            # If timestamp modes don't match, regenerate the chapter
            logger.info(
                f"Regenerating chapter {i}/{total_chapters}"
                f" '{chap_title[:40]}' (timestamp mode changed)"
            )

        chapters_to_generate[chap_title] = chapter_data.text

    return ChapterGenerationPlan(
        chapters_to_generate=chapters_to_generate,
        chapter_targets=chapter_targets,
        chapter_output_files=chapter_output_files,
    )


async def generate_missing_chapter_notes(
    pipeline: PipelineProtocol,
    video_id: str,
    title: str,
    ordered_chapters: list[tuple[str, ChapterPayload]],
    total_chapters: int,
    plan: ChapterGenerationPlan,
    emit: Callable[..., None],
) -> dict[str, str]:
    if not plan.chapters_to_generate:
        return {}

    chapter_indices = {
        chapter_title: index
        for index, (chapter_title, _) in enumerate(ordered_chapters, start=1)
    }
    chapters_to_generate_titles = list(plan.chapters_to_generate)

    def _on_chapter_start(index: int, _total: int) -> None:
        chapter_title = chapters_to_generate_titles[index - 1]
        emit(
            EventType.CHAPTER_GENERATING,
            video_id,
            title=title,
            chapter_number=chapter_indices[chapter_title],
            total_chapters=total_chapters,
        )

    original_generate_single = pipeline.generator.generate_single_chapter_notes

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
                phase_label="Stitching",
            )
            if on_combine:
                on_combine(total_parts)

        result = await original_generate_single(
            chapter_title=chapter_title,
            chapter_text=chapter_text,
            on_chunk=_on_chapter_chunk,
            on_combine=_on_chapter_combine,
        )
        emit(
            EventType.CHAPTER_COMPLETE,
            video_id,
            title=title,
            chapter_number=chapter_number,
            total_chapters=total_chapters,
        )
        return result

    generate_chapter_notes = pipeline.generator.generate_chapter_notes_concurrent
    return await generate_chapter_notes(
        plan.chapters_to_generate,
        max_concurrent=config.max_concurrent_chapters,
        semaphore=pipeline._chapter_semaphore,
        video_title=title,
        on_chapter_start=_on_chapter_start,
        generate_single=_generate_single_chapter_notes_with_events,
    )


def persist_completed_chapter_files(
    pipeline: PipelineProtocol,
    plan: ChapterGenerationPlan,
    completed_chapter_notes: dict[str, str],
) -> None:
    """Write whatever chapters finished generating to their chapter_file.

    Called from the partial-failure path so a chapter that timed out (or hit
    a transient provider error) doesn't also cost its already-completed
    siblings: with these written, a rerun's existing chapter_file.exists()
    skip-check (see build_chapter_generation_plan) picks them back up
    instead of regenerating -- and repaying -- them. Deliberately does not
    render/bundle a final output from partial data; that only happens once
    every chapter is present.
    """
    for chapter_title, start_seconds, chapter_file in plan.chapter_targets:
        if chapter_file is None:
            continue
        notes = completed_chapter_notes.get(chapter_title)
        if notes is None:
            continue
        if pipeline.timestamps:
            notes = prefix_chapter_heading_with_timestamp(
                notes,
                chapter_title,
                start_seconds,
            )
        _atomic_write_text(chapter_file, notes)


def write_chapter_outputs_and_collect_bundle(
    pipeline: PipelineProtocol,
    plan: ChapterGenerationPlan,
    generated_chapter_notes: dict[str, str],
    rendered_output_targets: dict[str, Path],
) -> list[str]:
    bundled_chapter_notes: list[str] = []

    for chapter_title, start_seconds, chapter_file in plan.chapter_targets:
        notes = generated_chapter_notes.get(chapter_title)
        if notes is None and chapter_file is not None and chapter_file.exists():
            notes = chapter_file.read_text(encoding="utf-8")
        if notes is None:
            continue

        if pipeline.timestamps:
            notes = prefix_chapter_heading_with_timestamp(
                notes,
                chapter_title,
                start_seconds,
            )

        if rendered_output_targets:
            bundled_chapter_notes.append(notes)

        if chapter_file is None:
            continue

        _atomic_write_text(chapter_file, notes)

    return bundled_chapter_notes


def render_bundled_chapter_outputs(
    pipeline: PipelineProtocol,
    title: str,
    bundled_chapter_notes: list[str],
    rendered_output_targets: dict[str, Path],
    output_target: Path | None,
    transcript_output_dir: Path,
    chapter_directory_output: bool,
) -> tuple[dict[str, Path], str | None, Path | None, Path]:
    render_warning: str | None = None
    if not rendered_output_targets:
        return (
            rendered_output_targets,
            render_warning,
            output_target,
            transcript_output_dir,
        )

    bundled_notes = build_chapter_bundle(
        title,
        bundled_chapter_notes,
    )
    rendered_output_targets, render_warning = render_notes_with_warning(
        bundled_notes,
        title,
        rendered_output_targets,
        pipeline.target_language,
    )
    if pipeline.output_format in rendered_output_targets:
        primary_output_target = rendered_output_targets[pipeline.output_format]
        if not chapter_directory_output:
            transcript_output_dir = primary_output_target.parent
            output_target = primary_output_target
        else:
            output_target = rendered_output_targets[pipeline.output_format]

    return rendered_output_targets, render_warning, output_target, transcript_output_dir


async def generate_chapter_outputs(
    pipeline: PipelineProtocol,
    video_id: str,
    title: str,
    chapter_transcripts: dict[str, ChapterPayload],
    current_cached_video: object | None,
    reserved_targets: list[Path],
    emit: Callable[..., None],
) -> tuple[
    dict[str, Path],
    str | None,
    Path | None,
    Path,
    Path | None,
]:
    chapter_directory_output = pipeline.chapter_directory_output
    total_chapters = len(chapter_transcripts)
    ordered_chapters = list(chapter_transcripts.items())
    output_targets = await prepare_chapter_output_targets(
        pipeline,
        video_id,
        title,
        current_cached_video,
        reserved_targets,
        chapter_directory_output,
    )
    # The caller only takes ownership of bundled_chapter_cache_dir (and
    # removes it) once this function returns it successfully -- a full
    # bundle means every chapter is accounted for, so the cache is no longer
    # needed. On any failure below, this function deliberately leaves the
    # directory in place (unlike the old random TemporaryDirectory, which
    # was always wiped): whatever chapters made it to disk stay there so a
    # future rerun's chapter_file.exists() skip-check can reuse them instead
    # of repaying for them.
    try:
        plan = build_chapter_generation_plan(
            pipeline,
            title,
            ordered_chapters,
            total_chapters,
            output_targets.output_target,
            output_targets.temporary_chapter_dir,
            chapter_directory_output,
        )
        generated_chapter_notes = await generate_missing_chapter_notes(
            pipeline,
            video_id,
            title,
            ordered_chapters,
            total_chapters,
            plan,
            emit,
        )
        bundled_chapter_notes = write_chapter_outputs_and_collect_bundle(
            pipeline,
            plan,
            generated_chapter_notes,
            output_targets.rendered_output_targets,
        )
        if chapter_directory_output and output_targets.output_target is not None:
            pipeline._write_output_target_metadata(
                output_targets.output_target,
                video_id,
                list(plan.chapter_output_files.values()),
            )
        (
            rendered_output_targets,
            render_warning,
            output_target,
            transcript_output_dir,
        ) = render_bundled_chapter_outputs(
            pipeline,
            title,
            bundled_chapter_notes,
            output_targets.rendered_output_targets,
            output_targets.output_target,
            output_targets.transcript_output_dir,
            chapter_directory_output,
        )
    except PartialChapterGenerationError as partial_error:
        # Persist whatever finished before re-raising -- this is what lets a
        # rerun's existing chapter_file.exists() skip-check pick these back
        # up instead of regenerating -- and repaying for -- them, in both
        # --chapter-directory-output and (now deterministic) bundled mode.
        persist_completed_chapter_files(pipeline, plan, partial_error.completed)
        raise

    return (
        rendered_output_targets,
        render_warning,
        output_target,
        transcript_output_dir,
        output_targets.bundled_chapter_cache_dir,
    )
