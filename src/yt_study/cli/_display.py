"""CLI process display helpers for headless and Rich UI modes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from yt_study.cli._context import CliProcessContext
from yt_study.cli._formatters import print_cost_summary, print_run_summary
from yt_study.cli._types import (
    _BatchJobResult,
    _OrderedBatchFailure,
    _WorkerSlotManager,
)
from yt_study.domain.events import EventType, PipelineEvent
from yt_study.domain.results import PipelineMetrics
from yt_study.logging import get_session_log_path


_DashboardStatusFn = Callable[[str, PipelineEvent], str]

HEADLESS_LABELS: dict[EventType, str] = {
    EventType.METADATA_START: "Fetching metadata",
    EventType.METADATA_FETCHED: "Metadata ready",
    EventType.TRANSCRIPT_FETCHING: "Fetching transcript",
    EventType.TRANSCRIPT_FETCHED: "Transcript ready",
    EventType.GENERATION_START: "Generating notes",
    EventType.CHUNK_GENERATING: "Generating chunk",
    EventType.GENERATION_COMBINING: "Combining notes",
    EventType.CHAPTER_GENERATING: "Generating chapter",
    EventType.CHAPTER_CHUNK_GENERATING: "Generating chapter part",
    EventType.CHAPTER_COMBINING: "Combining chapter",
    EventType.QUIZ_GENERATING: "Generating quiz",
    EventType.QUIZ_CHUNK_GENERATING: "Generating quiz part",
    EventType.QUIZ_COMBINING: "Combining quiz",
    EventType.QUIZ_COMPLETE: "Quiz ready",
    EventType.GENERATION_COMPLETE: "Generation complete",
    EventType.VIDEO_SUCCESS: "Done",
    EventType.VIDEO_SKIPPED: "Skipped (already processed)",
}

UI_STATUS_MAP: dict[EventType, _DashboardStatusFn] = {
    EventType.METADATA_START: lambda title, _: (
        f"[yellow]{title}... (Metadata)[/yellow]"
    ),
    EventType.METADATA_FETCHED: lambda title, _: f"[cyan]{title}... (Fetched)[/cyan]",
    EventType.TRANSCRIPT_FETCHING: lambda title, _: (
        f"[cyan]> {title}... (Transcript)[/cyan]"
    ),
    EventType.TRANSCRIPT_FETCHED: lambda title, _: (
        f"[green]OK {title}... (Transcript Ready)[/green]"
    ),
    EventType.GENERATION_START: lambda title, _: (
        f"[cyan]* {title}... (Generating)[/cyan]"
    ),
    EventType.CHUNK_GENERATING: lambda title, event: (
        f"[cyan]* {title}... (Chunk {event.chunk_number}/{event.total_chunks})[/cyan]"
    ),
    EventType.GENERATION_COMBINING: lambda title, event: (
        f"[cyan]* {title}... (Combining {event.total_chunks} note parts)[/cyan]"
    ),
    EventType.CHAPTER_GENERATING: lambda title, event: (
        f"[cyan]* {title}... (Ch {event.chapter_number}/{event.total_chapters})[/cyan]"
    ),
    EventType.CHAPTER_CHUNK_GENERATING: lambda title, event: (
        f"[cyan]* {title}... (Ch {event.chapter_number}/{event.total_chapters},"
        f" Part {event.chunk_number}/{event.total_chunks})[/cyan]"
    ),
    EventType.CHAPTER_COMBINING: lambda title, event: (
        f"[cyan]* {title}... (Ch {event.chapter_number}/{event.total_chapters},"
        f" Combining {event.total_chunks} parts)[/cyan]"
    ),
    EventType.QUIZ_GENERATING: lambda title, _: (
        f"[magenta]* {title}... (Quiz)[/magenta]"
    ),
    EventType.QUIZ_CHUNK_GENERATING: lambda title, event: (
        "[magenta]* "
        f"{title}... (Quiz Part {event.chunk_number}/{event.total_chunks})[/magenta]"
    ),
    EventType.QUIZ_COMBINING: lambda title, event: (
        f"[magenta]* {title}... (Combining {event.total_chunks} quiz parts)[/magenta]"
    ),
    EventType.QUIZ_COMPLETE: lambda title, _: (
        f"[green]OK {title}... (Quiz Ready)[/green]"
    ),
    EventType.GENERATION_COMPLETE: lambda title, _: (
        f"[green]OK {title}... (Generated)[/green]"
    ),
}


def emit_headless_event(context: CliProcessContext, event: PipelineEvent) -> None:
    """Render a plain-text event line in `--no-ui` mode."""
    if event.event_type in (
        EventType.PIPELINE_START,
        EventType.PIPELINE_COMPLETE,
        EventType.VIDEO_FAILED,
    ):
        return
    label = HEADLESS_LABELS.get(event.event_type, event.event_type.value)
    title = event.title or event.video_id
    extra = ""
    if (
        event.event_type == EventType.CHAPTER_CHUNK_GENERATING
        and event.chapter_number
        and event.total_chapters
        and event.chunk_number
        and event.total_chunks
    ):
        extra = (
            f" [Ch {event.chapter_number}/{event.total_chapters},"
            f" Part {event.chunk_number}/{event.total_chunks}]"
        )
    elif event.chunk_number and event.total_chunks:
        extra = f" [{event.chunk_number}/{event.total_chunks}]"
    elif event.chapter_number and event.total_chapters:
        extra = f" [{event.chapter_number}/{event.total_chapters}]"
    elif event.total_chunks and event.event_type in (
        EventType.GENERATION_COMBINING,
        EventType.QUIZ_COMBINING,
        EventType.CHAPTER_COMBINING,
    ):
        extra = f" [{event.total_chunks} parts]"
    elif event.error:
        extra = f": {event.error}"
    context.console.print(f"{label}: {title}{extra}", markup=False)


def build_ui_event_handler(
    dashboard: Any,
    slot_manager: _WorkerSlotManager,
) -> Callable[[PipelineEvent], None]:
    """Build the Rich dashboard event bridge for a single run."""

    def on_event(event: PipelineEvent) -> None:
        video_id = event.video_id
        title = (event.title or video_id)[:40]
        slot = slot_manager.get(video_id)

        if event.event_type == EventType.METADATA_START:
            assigned = slot_manager.acquire(video_id)
            if assigned is not None:
                slot = assigned
                status_fn = UI_STATUS_MAP.get(event.event_type)
                if status_fn:
                    dashboard.update_worker(assigned, status_fn(title, event))

        elif event.event_type in UI_STATUS_MAP and slot is not None:
            status_fn = UI_STATUS_MAP[event.event_type]
            dashboard.update_worker(slot, status_fn(title, event))

        elif event.event_type in (
            EventType.VIDEO_SUCCESS,
            EventType.VIDEO_SKIPPED,
            EventType.VIDEO_FAILED,
        ):
            released = slot_manager.release(video_id)
            if released is not None:
                dashboard.update_worker(released, "[dim]Idle[/dim]")

            if event.event_type == EventType.VIDEO_SUCCESS:
                dashboard.add_completion(event.title or video_id)
            elif event.event_type == EventType.VIDEO_SKIPPED:
                dashboard.add_completion(f"{event.title or video_id} (skipped)")
            else:
                dashboard.add_failure(event.title or video_id)

    return on_event


def print_single_run_summary(
    context: CliProcessContext,
    result: Any,
    dashboard: Any,
) -> None:
    """Render the Rich UI summary for a single run."""
    print_run_summary(
        context.console,
        result,
        dashboard.recent_failures,
        dashboard.recent_completions,
    )


def print_batch_summary(
    context: CliProcessContext,
    batch_results: list[_BatchJobResult],
    early_failures: list[_OrderedBatchFailure],
    *,
    total_jobs: int,
) -> bool:
    """Render one final summary for a batch run."""
    success_jobs = sum(1 for result in batch_results if result.success)
    failed_rows = [
        (failure.item, failure.message)
        for failure in sorted(
            [
                *early_failures,
                *[
                    result.failure_row
                    for result in batch_results
                    if result.failure_row is not None
                ],
            ],
            key=lambda failure: failure.sort_key,
        )
    ]

    batch_metrics = PipelineMetrics()
    for result in batch_results:
        batch_metrics.add_from(result.metrics)

    if failed_rows:
        intro = None
        if success_jobs and total_jobs:
            intro = f"Videos completed successfully: {success_jobs}/{total_jobs}"
        context.print_failure_panel(
            "Batch Completed with Failures",
            failed_rows,
            intro=intro,
        )
        return True

    context.console.print(
        f"\nDone: {success_jobs}/{total_jobs} batch videos succeeded."
    )
    print_cost_summary(context.console, batch_metrics)
    context.console.print(f"[dim]Current log: {get_session_log_path()}[/dim]\n")
    return False
