"""Unit tests for CLI display helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from rich.console import Console

from notewise.cli._context import CliProcessContext
from notewise.cli._display import (
    build_dashboard_config_items,
    build_ui_event_handler,
    emit_headless_event,
    print_batch_summary,
    restore_console_after_live,
    should_clear_dashboard_after_run,
    update_dashboard_chapter_slot,
    use_transient_live_display,
)
from notewise.cli._types import (
    _BatchJobResult,
    _OrderedBatchFailure,
    _WorkerSlotManager,
)
from notewise.domain.events import EventType, PipelineEvent
from notewise.domain.results import PipelineMetrics, PipelineResult
from notewise.ui.dashboard import PipelineDashboard


def test_worker_slot_manager_reuses_released_slots_in_queue_order() -> None:
    """Released slots should go back to the pool without list-shift behavior."""
    slot_manager = _WorkerSlotManager(3)

    assert slot_manager.acquire("vid1") == 0
    assert slot_manager.acquire("vid2") == 1
    assert slot_manager.release("vid1") == 0
    assert slot_manager.acquire("vid3") == 2
    assert slot_manager.acquire("vid4") == 0


def test_build_ui_event_handler_logs_slot_exhaustion_once_per_video() -> None:
    """The dashboard bridge should log when no worker slot can be assigned."""
    dashboard = MagicMock()
    slot_manager = _WorkerSlotManager(1)
    on_event = build_ui_event_handler(dashboard, slot_manager)

    on_event(
        PipelineEvent(
            event_type=EventType.METADATA_START,
            video_id="vid1",
            title="Video One",
        )
    )

    with patch("notewise.cli._display.logger") as mock_logger:
        on_event(
            PipelineEvent(
                event_type=EventType.METADATA_START,
                video_id="vid2",
                title="Video Two",
            )
        )
        on_event(
            PipelineEvent(
                event_type=EventType.METADATA_START,
                video_id="vid2",
                title="Video Two",
            )
        )

    mock_logger.warning.assert_called_once_with(
        "ui.worker_slot_exhausted",
        video_id="vid2",
        title="Video Two",
    )


def test_build_ui_event_handler_updates_structured_worker_state() -> None:
    """Dashboard bridge should keep detailed worker phase state in sync."""
    dashboard = PipelineDashboard(1, 1, "List", "Model")
    slot_manager = _WorkerSlotManager(1)
    on_event = build_ui_event_handler(dashboard, slot_manager)

    on_event(
        PipelineEvent(
            event_type=EventType.METADATA_START,
            video_id="vid1",
            title="Video A",
        )
    )
    assert dashboard.worker_snapshots[0].phase == "Metadata"
    assert dashboard.worker_snapshots[0].title == "Video A"

    on_event(
        PipelineEvent(
            event_type=EventType.CHUNK_GENERATING,
            video_id="vid1",
            title="Video A",
            chunk_number=2,
            total_chunks=5,
        )
    )
    assert dashboard.worker_snapshots[0].phase == "Generation"
    assert dashboard.worker_snapshots[0].detail == "chunks 2/5"

    on_event(
        PipelineEvent(
            event_type=EventType.VIDEO_SUCCESS,
            video_id="vid1",
            title="Video A",
        )
    )
    assert dashboard.worker_snapshots[0].phase == "Idle"
    assert dashboard.worker_snapshots[0].title == "—"


def test_build_dashboard_config_items_redacts_sensitive_values() -> None:
    """Safe dashboard config should summarize flags without leaking secrets."""
    context = SimpleNamespace(
        selected_output_formats=["md", "pdf"],
        selected_languages=["en", "hi"],
        selected_target_language="English",
        selected_temperature=0.3,
        selected_max_tokens=8192,
        selected_throttle_seconds=1.25,
        force=True,
        quiz=True,
        use_combine_chunk=False,
        export_transcript="srt",
        timestamps=True,
        chapter_directory_output=True,
        selected_cookie_file="/tmp/sk-secret-cookie-dir/youtube-cookies.txt",
        api_key_checked=True,
    )

    items = build_dashboard_config_items(
        context,
        output_dir=Path("/tmp/notewise-notes"),
        video_workers=3,
        chapter_workers=4,
    )
    rendered = "\n".join(f"{item.label}: {item.value}" for item in items)

    assert "Output: /tmp/notewise-notes" in rendered
    assert "Formats: md, pdf" in rendered
    assert "Languages: en, hi" in rendered
    assert "Target language: English" in rendered
    assert "Temperature: 0.3" in rendered
    assert "Max tokens: 8192" in rendered
    assert "Video workers: 3" in rendered
    assert "Chapter workers: 4" in rendered
    assert "Cookies: configured: youtube-cookies.txt" in rendered
    assert "API key: present" in rendered
    assert "sk-secret-cookie-dir" not in rendered


def test_build_ui_event_handler_escapes_worker_titles() -> None:
    """Worker titles containing Rich markup should render literally."""
    dashboard = PipelineDashboard(1, 1, "List", "Model")
    slot_manager = _WorkerSlotManager(1)
    on_event = build_ui_event_handler(dashboard, slot_manager)

    on_event(
        PipelineEvent(
            event_type=EventType.METADATA_START,
            video_id="vid1",
            title="Bad [boom]",
        )
    )

    console = Console(width=100)
    with console.capture() as capture:
        console.print(dashboard)

    assert "Bad [boom]" in capture.get()


def test_use_transient_live_display_respects_platform(monkeypatch) -> None:
    """Windows consoles should avoid transient live cleanup."""
    monkeypatch.setattr("notewise.cli._display.os.name", "nt")
    assert use_transient_live_display() is False

    monkeypatch.setattr("notewise.cli._display.os.name", "posix")
    assert use_transient_live_display() is True


def test_restore_console_after_live_best_effort() -> None:
    """Live cleanup should restore the cursor and flush the file if available."""
    console = MagicMock()
    console.file.flush = MagicMock()

    restore_console_after_live(console)

    console.show_cursor.assert_called_once_with(True)
    console.file.flush.assert_called_once_with()


def test_restore_console_after_live_handles_missing_hooks() -> None:
    """Cleanup should no-op when cursor or flush hooks are absent."""
    restore_console_after_live(SimpleNamespace(file=SimpleNamespace()))


def test_emit_headless_event_formats_chapter_chunk_progress() -> None:
    """Headless output should include chapter and chunk progress details."""
    context = MagicMock(spec=CliProcessContext)
    context.console = MagicMock()

    emit_headless_event(
        context,
        PipelineEvent(
            event_type=EventType.CHAPTER_CHUNK_GENERATING,
            video_id="vid1",
            title="Video",
            chapter_number=2,
            total_chapters=4,
            chunk_number=3,
            total_chunks=5,
        ),
    )

    context.console.print.assert_called_once_with(
        "Generating chapter part: Video [Ch 2/4, Part 3/5]",
        markup=False,
    )


def test_emit_headless_event_ignores_completion_only_events() -> None:
    """Pipeline boundary and chapter completion events should stay silent."""
    context = MagicMock(spec=CliProcessContext)
    context.console = MagicMock()

    emit_headless_event(
        context,
        PipelineEvent(event_type=EventType.CHAPTER_COMPLETE, video_id="vid1"),
    )

    context.console.print.assert_not_called()


def test_emit_headless_event_formats_stitching_progress() -> None:
    """Headless output should reflect stitching wording for note finalization."""
    context = MagicMock(spec=CliProcessContext)
    context.console = MagicMock()

    emit_headless_event(
        context,
        PipelineEvent(
            event_type=EventType.GENERATION_COMBINING,
            video_id="vid1",
            title="Video",
            total_chunks=3,
            phase_label="Stitching",
        ),
    )

    context.console.print.assert_called_once_with(
        "Stitching notes: Video [3 parts]",
        markup=False,
    )


def test_build_ui_event_handler_uses_stitching_status_for_generation_finalization() -> (
    None
):
    """Dashboard worker text should use the event phase label for note finalization."""
    dashboard = MagicMock()
    slot_manager = _WorkerSlotManager(1)
    on_event = build_ui_event_handler(dashboard, slot_manager)

    on_event(
        PipelineEvent(
            event_type=EventType.METADATA_START,
            video_id="vid1",
            title="Video",
        )
    )
    dashboard.update_worker.reset_mock()

    on_event(
        PipelineEvent(
            event_type=EventType.GENERATION_COMBINING,
            video_id="vid1",
            title="Video",
            total_chunks=3,
            phase_label="Stitching",
        )
    )

    dashboard.update_worker.assert_called_once_with(
        0,
        "[cyan]* Video… (Stitching 3 note parts)[/cyan]",
    )


def test_update_dashboard_chapter_slot_handles_start_update_complete() -> None:
    """Chapter slots should start, update, and release against the dashboard."""
    dashboard = MagicMock()
    dashboard.chapter_concurrency = 2
    title = "Video"

    update_dashboard_chapter_slot(
        dashboard,
        title,
        PipelineEvent(
            event_type=EventType.CHAPTER_GENERATING,
            video_id="vid1",
            chapter_number=1,
            total_chapters=3,
        ),
    )
    update_dashboard_chapter_slot(
        dashboard,
        title,
        PipelineEvent(
            event_type=EventType.CHAPTER_CHUNK_GENERATING,
            video_id="vid1",
            chapter_number=1,
            total_chapters=3,
            chunk_number=2,
            total_chunks=4,
        ),
    )
    update_dashboard_chapter_slot(
        dashboard,
        title,
        PipelineEvent(
            event_type=EventType.CHAPTER_COMPLETE,
            video_id="vid1",
            chapter_number=1,
        ),
    )

    dashboard.start_chapter_worker.assert_called_once()
    dashboard.update_chapter_worker.assert_called_once()
    dashboard.complete_chapter_worker.assert_called_once_with("vid1:1")


def test_update_dashboard_chapter_slot_returns_when_dashboard_missing_hooks() -> None:
    """No-op safety should apply when chapter support is absent."""
    dashboard = MagicMock()
    dashboard.chapter_concurrency = 1
    del dashboard.start_chapter_worker
    del dashboard.update_chapter_worker
    del dashboard.complete_chapter_worker

    update_dashboard_chapter_slot(
        dashboard,
        "Video",
        PipelineEvent(
            event_type=EventType.CHAPTER_GENERATING,
            video_id="vid1",
            chapter_number=1,
            total_chapters=2,
        ),
    )


def test_update_dashboard_chapter_slot_handles_complete_and_unsupported_status() -> (
    None
):
    """Completion should release a slot while unrelated events stay ignored."""
    dashboard = MagicMock()
    dashboard.chapter_concurrency = 1

    update_dashboard_chapter_slot(
        dashboard,
        "Video",
        PipelineEvent(
            event_type=EventType.CHAPTER_COMPLETE,
            video_id="vid1",
            chapter_number=1,
        ),
    )
    update_dashboard_chapter_slot(
        dashboard,
        "Video",
        PipelineEvent(
            event_type=EventType.VIDEO_SUCCESS,
            video_id="vid1",
            chapter_number=1,
        ),
    )

    dashboard.complete_chapter_worker.assert_called_once_with("vid1:1")
    dashboard.start_chapter_worker.assert_not_called()


def test_should_clear_dashboard_after_run_for_skipped_only_result() -> None:
    """Skipped-only runs should clear the transient dashboard before summary."""
    dashboard = MagicMock()
    dashboard.skipped_count = 2
    result = PipelineResult(
        success_count=2,
        failure_count=0,
        total_count=2,
        video_ids=["a", "b"],
        errors={},
    )

    assert should_clear_dashboard_after_run(dashboard, result) is True


def test_should_clear_dashboard_after_run_rejects_failures_or_zero_success() -> None:
    """Only skip-only success runs should clear the dashboard."""
    dashboard = MagicMock()
    dashboard.skipped_count = 1

    assert (
        should_clear_dashboard_after_run(
            dashboard,
            PipelineResult(
                success_count=0,
                failure_count=0,
                total_count=0,
                video_ids=[],
                errors={},
            ),
        )
        is False
    )
    assert (
        should_clear_dashboard_after_run(
            dashboard,
            PipelineResult(
                success_count=1,
                failure_count=1,
                total_count=2,
                video_ids=["a", "b"],
                errors={"b": "boom"},
            ),
        )
        is False
    )


def test_print_batch_summary_success_path() -> None:
    """Successful batch summaries should print totals and cost info."""
    context = MagicMock(spec=CliProcessContext)
    context.console = MagicMock()

    metrics = PipelineMetrics(total_tokens=5, cost_usd=1.25)
    batch_results = [
        _BatchJobResult(
            sort_key=(0, 0),
            success=True,
            display_title="One",
            metrics=metrics,
        )
    ]

    with (
        patch("notewise.cli._display.print_cost_summary") as print_cost,
        patch("notewise.cli._display.get_session_log_path", return_value="session.log"),
    ):
        failed = print_batch_summary(
            context,
            batch_results,
            [],
            total_jobs=1,
        )

    assert failed is False
    print_cost.assert_called_once()
    context.console.print.assert_any_call("\nDone: 1/1 batch videos succeeded.")


def test_print_batch_summary_failure_path_includes_intro() -> None:
    """Mixed batch outcomes should route through the failure panel with intro text."""
    context = MagicMock(spec=CliProcessContext)
    context.console = MagicMock()
    context.print_failure_panel = MagicMock()

    batch_results = [
        _BatchJobResult(sort_key=(0, 0), success=True, display_title="One"),
        _BatchJobResult(
            sort_key=(0, 1),
            success=False,
            display_title="Two",
            failure_row=_OrderedBatchFailure(
                sort_key=(0, 1),
                item="Two",
                message="boom",
            ),
        ),
    ]

    failed = print_batch_summary(
        context,
        batch_results,
        [],
        total_jobs=2,
    )

    assert failed is True
    context.print_failure_panel.assert_called_once()


def test_build_ui_event_handler_releases_without_clear_hook() -> None:
    """Worker release should not require chapter-clear support on the dashboard."""
    dashboard = SimpleNamespace(
        update_worker=MagicMock(),
        add_completion=MagicMock(),
        add_failure=MagicMock(),
    )
    slot_manager = _WorkerSlotManager(1)
    on_event = build_ui_event_handler(dashboard, slot_manager)

    on_event(
        PipelineEvent(
            event_type=EventType.METADATA_START,
            video_id="vid1",
            title="Video One",
        )
    )
    on_event(
        PipelineEvent(
            event_type=EventType.VIDEO_SUCCESS,
            video_id="vid1",
            title="Video One",
        )
    )

    dashboard.update_worker.assert_any_call(0, "[dim]Idle[/dim]")
    dashboard.add_completion.assert_called_once_with("Video One")
