"""Unit tests for CLI display helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from rich.console import Console

from yt_study.cli._display import build_ui_event_handler
from yt_study.cli._types import _WorkerSlotManager
from yt_study.domain.events import EventType, PipelineEvent
from yt_study.ui.dashboard import PipelineDashboard


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

    with patch("yt_study.cli._display.logger") as mock_logger:
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
