"""CLI process display helpers for headless and Rich UI modes."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from rich.markup import escape

from notewise._constants import (
    DASHBOARD_IDLE_MARKUP,
    DASHBOARD_SKIPPED_SUFFIX,
    GPT5_MODEL_MARKER,
    GPT5_REQUIRED_TEMPERATURE,
)
from notewise.cli._formatters import print_cost_summary, print_run_summary
from notewise.domain.events import EventType, PipelineEvent
from notewise.domain.results import PipelineMetrics, PipelineResult
from notewise.logging import get_session_log_path
from notewise.ui.dashboard import DashboardConfigItem


if TYPE_CHECKING:
    from notewise.cli._context import CliProcessContext
    from notewise.cli._types import (
        _BatchJobResult,
        _OrderedBatchFailure,
        _WorkerSlotManager,
    )


_DashboardStatusFn = Callable[[str, PipelineEvent], str]
logger = structlog.get_logger(__name__)
_TITLE_LIMIT = 40

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


def _phase_label(event: PipelineEvent, default: str) -> str:
    """Return the user-facing phase label for finalize-style events."""
    return event.phase_label or default


UI_STATUS_MAP: dict[EventType, _DashboardStatusFn] = {
    EventType.METADATA_START: lambda title, _: f"[yellow]Metadata[/yellow] · {title}",
    EventType.METADATA_FETCHED: lambda title, _: (
        f"[cyan]Metadata ready[/cyan] · {title}"
    ),
    EventType.TRANSCRIPT_FETCHING: lambda title, _: (
        f"[cyan]Transcript[/cyan] · {title}"
    ),
    EventType.TRANSCRIPT_FETCHED: lambda title, _: (
        f"[green]Transcript ready[/green] · {title}"
    ),
    EventType.GENERATION_START: lambda title, _: f"[cyan]Generating[/cyan] · {title}",
    EventType.CHUNK_GENERATING: lambda title, event: (
        f"[cyan]Generating[/cyan] · {title} · chunk "
        f"{event.chunk_number}/{event.total_chunks}"
    ),
    EventType.GENERATION_COMBINING: lambda title, event: (
        f"[cyan]{_phase_label(event, 'Finalizing')}[/cyan] · {title} · "
        f"{event.total_chunks} note parts"
    ),
    EventType.CHAPTER_GENERATING: lambda title, event: (
        f"[cyan]Chapter[/cyan] · {title} · "
        f"{event.chapter_number}/{event.total_chapters}"
    ),
    EventType.CHAPTER_CHUNK_GENERATING: lambda title, event: (
        f"[cyan]Chapter[/cyan] · {title} · "
        f"{event.chapter_number}/{event.total_chapters}, "
        f"part {event.chunk_number}/{event.total_chunks}"
    ),
    EventType.CHAPTER_COMBINING: lambda title, event: (
        f"[cyan]{_phase_label(event, 'Finalizing')} chapter[/cyan] · {title} · "
        f"{event.total_chunks} parts"
    ),
    EventType.QUIZ_GENERATING: lambda title, _: f"[magenta]Quiz[/magenta] · {title}",
    EventType.QUIZ_CHUNK_GENERATING: lambda title, event: (
        f"[magenta]Quiz[/magenta] · {title} · part "
        f"{event.chunk_number}/{event.total_chunks}"
    ),
    EventType.QUIZ_COMBINING: lambda title, event: (
        f"[magenta]Finalizing quiz[/magenta] · {title} · {event.total_chunks} parts"
    ),
    EventType.QUIZ_COMPLETE: lambda title, _: f"[green]Quiz ready[/green] · {title}",
    EventType.GENERATION_COMPLETE: lambda title, _: (
        f"[green]Notes ready[/green] · {title}"
    ),
}


def _truncate_title(title: str, *, limit: int = _TITLE_LIMIT) -> str:
    """Trim event titles to the dashboard width before status suffixes."""
    return title[:limit] if len(title) > limit else title


def _format_bool(value: bool) -> str:
    """Return an on/off display value for dashboard flags."""
    return "on" if value else "off"


def _format_api_key_status(api_key_checked: bool | None) -> str:
    """Return a safe API-key status without exposing provider config."""
    if api_key_checked is True:
        return "present"
    if api_key_checked is False:
        return "missing"
    return "not checked"


def _format_cookie_status(cookie_file: str | None) -> str:
    """Return a safe cookie-file status without showing the full local path."""
    if not cookie_file:
        return "not configured"
    basename = Path(cookie_file).name
    return f"configured: {basename}" if basename else "configured"


def _format_effective_temperature(model: str, temperature: float) -> str:
    """Return the temperature that will be sent to the provider."""
    if GPT5_MODEL_MARKER in model.strip().lower():
        return f"{GPT5_REQUIRED_TEMPERATURE:g} (provider fixed)"
    return f"{temperature:g}"


def build_dashboard_config_items(
    context: CliProcessContext,
    *,
    output_dir: Path,
    video_workers: int,
    chapter_workers: int,
) -> tuple[DashboardConfigItem, ...]:
    """Build safe runtime config rows for the Rich dashboard."""
    export_transcript = context.export_transcript or "off"
    return (
        DashboardConfigItem("Output", str(output_dir)),
        DashboardConfigItem(
            "Formats",
            ", ".join(str(item) for item in context.selected_output_formats),
        ),
        DashboardConfigItem(
            "Languages",
            ", ".join(str(item) for item in context.selected_languages),
        ),
        DashboardConfigItem("Target language", str(context.selected_target_language)),
        DashboardConfigItem(
            "Temperature",
            _format_effective_temperature(
                getattr(context, "selected_model", ""),
                context.selected_temperature,
            ),
        ),
        DashboardConfigItem(
            "Max tokens",
            "provider default"
            if context.selected_max_tokens is None
            else str(context.selected_max_tokens),
        ),
        DashboardConfigItem("Video workers", str(video_workers)),
        DashboardConfigItem("Chapter workers", str(chapter_workers)),
        DashboardConfigItem("Throttle", f"{context.selected_throttle_seconds:g}s"),
        DashboardConfigItem("Force", _format_bool(bool(context.force))),
        DashboardConfigItem("Quiz", _format_bool(bool(context.quiz))),
        DashboardConfigItem("Timestamps", _format_bool(bool(context.timestamps))),
        DashboardConfigItem("Export transcript", str(export_transcript)),
        DashboardConfigItem(
            "Chapter directories",
            _format_bool(bool(context.chapter_directory_output)),
        ),
        DashboardConfigItem(
            "Cookies",
            _format_cookie_status(context.selected_cookie_file),
        ),
        DashboardConfigItem(
            "API key",
            _format_api_key_status(context.api_key_checked),
        ),
    )


def _event_worker_phase_detail(event: PipelineEvent) -> tuple[str, str]:
    """Return the structured worker phase/detail for a pipeline event."""
    if event.event_type in (EventType.METADATA_START, EventType.METADATA_FETCHED):
        return (
            "Metadata",
            "fetching" if event.event_type == EventType.METADATA_START else "ready",
        )
    if event.event_type in (
        EventType.TRANSCRIPT_FETCHING,
        EventType.TRANSCRIPT_FETCHED,
    ):
        return "Transcript", (
            "fetching" if event.event_type == EventType.TRANSCRIPT_FETCHING else "ready"
        )
    if event.event_type == EventType.GENERATION_START:
        return "Generation", "starting"
    if event.event_type == EventType.CHUNK_GENERATING:
        return "Generation", f"chunks {event.chunk_number}/{event.total_chunks}"
    if event.event_type == EventType.GENERATION_COMBINING:
        return _phase_label(event, "Finalizing"), f"{event.total_chunks} note parts"
    if event.event_type == EventType.CHAPTER_GENERATING:
        return "Chapters", f"chapter {event.chapter_number}/{event.total_chapters}"
    if event.event_type == EventType.CHAPTER_CHUNK_GENERATING:
        return "Chapters", (
            f"chapter {event.chapter_number}/{event.total_chapters}, "
            f"part {event.chunk_number}/{event.total_chunks}"
        )
    if event.event_type == EventType.CHAPTER_COMBINING:
        return "Chapters", (
            f"chapter {event.chapter_number}/{event.total_chapters}, "
            f"{_phase_label(event, 'Finalizing').lower()} {event.total_chunks} parts"
        )
    if event.event_type == EventType.QUIZ_GENERATING:
        return "Quiz", "generating"
    if event.event_type == EventType.QUIZ_CHUNK_GENERATING:
        return "Quiz", f"parts {event.chunk_number}/{event.total_chunks}"
    if event.event_type == EventType.QUIZ_COMBINING:
        return "Quiz", f"combining {event.total_chunks} parts"
    if event.event_type == EventType.QUIZ_COMPLETE:
        return "Quiz", "ready"
    if event.event_type == EventType.GENERATION_COMPLETE:
        return "Export", "generated"
    return event.event_type.value, ""


def _update_structured_worker_state(
    dashboard: Any,
    slot: int,
    event: PipelineEvent,
    *,
    title: str | None = None,
) -> None:
    """Update detailed dashboard worker state when the dashboard supports it."""
    update_worker_state = getattr(dashboard, "update_worker_state", None)
    if not callable(update_worker_state):
        return
    phase, detail = _event_worker_phase_detail(event)
    update_worker_state(
        slot,
        phase=phase,
        title=title or event.title or event.video_id,
        detail=detail,
    )


def update_dashboard_worker_for_event(
    dashboard: Any,
    slot: int,
    title: str,
    event: PipelineEvent,
) -> None:
    """Reflect one video event into legacy and structured worker UI state."""
    status_fn = UI_STATUS_MAP.get(event.event_type)
    if status_fn is None:
        return
    dashboard.update_worker(slot, status_fn(escape(title), event))
    _update_structured_worker_state(dashboard, slot, event, title=title)


def _clear_structured_worker_state(dashboard: Any, slot: int) -> None:
    """Clear detailed dashboard worker state when the dashboard supports it."""
    clear_worker_state = getattr(dashboard, "clear_worker_state", None)
    if callable(clear_worker_state):
        clear_worker_state(slot)


def use_transient_live_display() -> bool:
    """Use transient live cleanup only where terminals handle it reliably."""
    return os.name != "nt"


def restore_console_after_live(console: Any) -> None:
    """Best-effort console cleanup after a Rich Live session."""
    show_cursor = getattr(console, "show_cursor", None)
    if callable(show_cursor):
        show_cursor(True)

    flush = getattr(getattr(console, "file", None), "flush", None)
    if callable(flush):
        flush()


def emit_headless_event(context: CliProcessContext, event: PipelineEvent) -> None:
    """Render a plain-text event line in `--no-ui` mode."""
    if event.event_type in (
        EventType.PIPELINE_START,
        EventType.PIPELINE_COMPLETE,
        EventType.VIDEO_FAILED,
        EventType.CHAPTER_COMPLETE,
    ):
        return
    label = HEADLESS_LABELS.get(event.event_type, event.event_type.value)
    if event.event_type == EventType.GENERATION_COMBINING:
        label = f"{_phase_label(event, 'Finalizing')} notes"
    elif event.event_type == EventType.CHAPTER_COMBINING:
        label = f"{_phase_label(event, 'Finalizing')} chapter"
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
    warned_slot_exhaustion: set[str] = set()

    def on_event(event: PipelineEvent) -> None:
        video_id = event.video_id
        title = _truncate_title(event.title or video_id)
        slot = slot_manager.get(video_id)

        if event.event_type == EventType.METADATA_START:
            assigned = slot_manager.acquire(video_id)
            if assigned is not None:
                slot = assigned
                warned_slot_exhaustion.discard(video_id)
                if hasattr(dashboard, "clear_chapter_workers"):
                    dashboard.clear_chapter_workers(video_id)
                status_fn = UI_STATUS_MAP.get(event.event_type)
                if status_fn:
                    update_dashboard_worker_for_event(dashboard, assigned, title, event)
            elif video_id not in warned_slot_exhaustion:
                warned_slot_exhaustion.add(video_id)
                logger.warning(
                    "ui.worker_slot_exhausted",
                    video_id=video_id,
                    title=event.title or video_id,
                )

        elif event.event_type in UI_STATUS_MAP and slot is not None:
            update_dashboard_worker_for_event(dashboard, slot, title, event)
            if event.event_type in (
                EventType.CHAPTER_GENERATING,
                EventType.CHAPTER_CHUNK_GENERATING,
                EventType.CHAPTER_COMBINING,
            ):
                update_dashboard_chapter_slot(dashboard, escape(title), event)

        elif event.event_type == EventType.CHAPTER_COMPLETE:
            update_dashboard_chapter_slot(dashboard, title, event)

        elif event.event_type in (
            EventType.VIDEO_SUCCESS,
            EventType.VIDEO_SKIPPED,
            EventType.VIDEO_FAILED,
        ):
            warned_slot_exhaustion.discard(video_id)
            released = slot_manager.release(video_id)
            if released is not None:
                if hasattr(dashboard, "clear_chapter_workers"):
                    dashboard.clear_chapter_workers(video_id)
                _clear_structured_worker_state(dashboard, released)
                dashboard.update_worker(released, DASHBOARD_IDLE_MARKUP)

            if event.event_type == EventType.VIDEO_SUCCESS:
                dashboard.add_completion(event.title or video_id)
            elif event.event_type == EventType.VIDEO_SKIPPED:
                add_skipped = getattr(dashboard, "add_skipped", None)
                if callable(add_skipped):
                    add_skipped(event.title or video_id)
                else:
                    dashboard.add_completion(
                        f"{event.title or video_id}{DASHBOARD_SKIPPED_SUFFIX}"
                    )
            else:
                dashboard.add_failure(event.title or video_id)

    return on_event


def update_dashboard_chapter_slot(
    dashboard: Any,
    title: str,
    event: PipelineEvent,
) -> None:
    """Reflect a chapter event into the dashboard's shared chapter worker lanes."""
    chapter_concurrency = int(getattr(dashboard, "chapter_concurrency", 0) or 0)
    if (
        chapter_concurrency <= 0
        or event.chapter_number is None
        or not hasattr(dashboard, "start_chapter_worker")
        or not hasattr(dashboard, "update_chapter_worker")
        or not hasattr(dashboard, "complete_chapter_worker")
    ):
        return
    chapter_key = f"{event.video_id}:{event.chapter_number}"
    status_fn = UI_STATUS_MAP.get(event.event_type)
    if event.event_type == EventType.CHAPTER_COMPLETE:
        dashboard.complete_chapter_worker(chapter_key)
        return
    if status_fn is None:
        return
    if event.event_type == EventType.CHAPTER_GENERATING:
        dashboard.start_chapter_worker(
            chapter_key,
            event.video_id,
            status_fn(title, event),
        )
        return
    dashboard.update_chapter_worker(chapter_key, status_fn(title, event))


def should_clear_dashboard_after_run(
    dashboard: Any,
    result: PipelineResult,
) -> bool:
    """Return True when a skipped-only run should clear the live dashboard."""
    if result.failure_count or result.success_count == 0:
        return False
    return int(getattr(dashboard, "skipped_count", 0) or 0) == result.success_count


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
