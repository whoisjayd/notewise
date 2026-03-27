"""Tests for CLI Rich formatter helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from rich.console import Console

from notewise.cli import _formatters
from notewise.domain.results import PipelineMetrics, PipelineResult


def _console() -> Console:
    return Console(record=True, width=120)


def _text(console: Console) -> str:
    return console.export_text()


def test_print_failure_panel_includes_intro_and_log(monkeypatch) -> None:
    """Failure panels should include intro text and current log path when present."""
    console = _console()
    monkeypatch.setattr(
        _formatters,
        "get_session_log_path",
        lambda: Path("session.log"),
    )

    _formatters.print_failure_panel(
        console,
        "Processing Failed",
        [("Video", "boom")],
        intro="Completed successfully: 1/2",
    )

    output = _text(console)
    assert "Completed successfully: 1/2" in output
    assert "Current log: session.log" in output


def test_print_cost_summary_sanitizes_invalid_metric_values() -> None:
    """Cost summary should clamp invalid values to safe zero defaults."""
    console = _console()
    metrics = SimpleNamespace(
        prompt_tokens="bad",
        completion_tokens=object(),
        total_tokens=-4,
        cost_usd="oops",
        transcript_seconds=None,
        generation_seconds=-1,
    )

    _formatters.print_cost_summary(console, metrics)

    output = _text(console)
    assert "Cost Summary" in output
    assert "$0.000000" in output


def test_print_run_summary_handles_failures_and_zero_total(monkeypatch) -> None:
    """Run summary should no-op on empty totals and show failure panels otherwise."""
    console = _console()
    called: list[tuple[str, list[tuple[str, str]], str | None]] = []

    def _record_failure_panel(
        target_console: Console,
        title: str,
        rows: list[tuple[str, str]],
        *,
        intro: str | None = None,
    ) -> None:
        del target_console
        called.append((title, rows, intro))

    monkeypatch.setattr(_formatters, "print_failure_panel", _record_failure_panel)

    _formatters.print_run_summary(
        console,
        PipelineResult(
            success_count=0,
            failure_count=0,
            total_count=0,
            video_ids=[],
            errors={},
        ),
        [],
        [],
    )
    _formatters.print_run_summary(
        console,
        PipelineResult(
            success_count=1,
            failure_count=1,
            total_count=2,
            video_ids=["a", "b"],
            errors={"b": "boom"},
            metrics=PipelineMetrics(),
        ),
        [],
        ["Video A"],
    )

    assert called == [
        (
            "Processing Failed",
            [("b", "boom")],
            "Completed successfully: 1/2",
        )
    ]


def test_print_failure_panel_without_intro_or_log(monkeypatch) -> None:
    """Failure panels should still render when intro and log path are absent."""
    console = _console()
    monkeypatch.setattr(_formatters, "get_session_log_path", lambda: None)

    _formatters.print_failure_panel(console, "Oops", [("Video", "boom")])

    output = _text(console)
    assert "Oops" in output
    assert "Current log:" not in output


def test_print_run_summary_success_path(monkeypatch) -> None:
    """Successful runs should render the summary table and current log path."""
    console = _console()
    monkeypatch.setattr(
        _formatters, "get_session_log_path", lambda: Path("session.log")
    )

    _formatters.print_run_summary(
        console,
        PipelineResult(
            success_count=2,
            failure_count=0,
            total_count=2,
            video_ids=["a", "b"],
            errors={},
            metrics=PipelineMetrics(total_tokens=10, cost_usd=0.25),
        ),
        ["Failed Video"],
        ["Completed Video"],
    )

    output = _text(console)
    assert "Processing Summary" in output
    assert "FAILED" in output
    assert "SUCCESS" in output
    assert "Current log: session.log" in output
