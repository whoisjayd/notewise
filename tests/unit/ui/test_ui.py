"""Tests for UI dashboard."""

from rich.console import Console
from rich.panel import Panel

from notewise._constants import (
    DASHBOARD_ACTIVITY_TITLE_LIMIT,
    DASHBOARD_CONFIG_VALUE_LIMIT,
)
from notewise.ui.dashboard import DashboardConfigItem, PipelineDashboard


def test_dashboard_initialization():
    """Test dashboard state init."""
    dash = PipelineDashboard(
        total_videos=10, concurrency=3, playlist_name="Test List", model_name="gpt-4"
    )

    assert dash.playlist_name == "Test List"
    assert len(dash.worker_tasks) == 3
    assert dash.chapter_concurrency == 0
    assert dash.overall_progress.tasks[0].total == 10


def test_dashboard_updates():
    """Test updating worker status."""
    dash = PipelineDashboard(10, 2, "List", "Model")

    # Update worker 0
    dash.update_worker(0, "Processing...")

    # Check if the task description was updated in the progress instance
    task_id = dash.worker_tasks[0]
    assert "Processing..." in dash.worker_progress.tasks[task_id].description


def test_dashboard_update_worker_counts_legacy_status_as_running() -> None:
    """Legacy status updates should still count active workers as running."""
    dash = PipelineDashboard(3, 1, "List", "Model")

    dash.update_worker(0, "Processing...")

    console = Console(width=180)
    with console.capture() as capture:
        console.print(dash)

    output = capture.get()
    assert "Running" in output
    assert "Queued" in output


def test_dashboard_update_worker_keeps_preformatted_markup():
    """Styled worker strings should pass through without extra wrapping."""
    dash = PipelineDashboard(10, 1, "List", "Model")

    dash.update_worker(0, "[cyan]Already styled[/cyan]")

    task_id = dash.worker_tasks[0]
    assert dash.worker_progress.tasks[task_id].description == (
        "[cyan]Already styled[/cyan]"
    )


def test_dashboard_chapter_updates():
    """Chapter worker slots should be independently updatable."""
    dash = PipelineDashboard(10, 2, "List", "Model", chapter_concurrency=2)

    dash.start_chapter_worker("vid1:2", "vid1", "Chapter 2 running")

    task_id = dash.chapter_tasks[0]
    assert "Chapter 2 running" in dash.chapter_progress.tasks[task_id].description


def test_dashboard_clear_chapter_workers():
    """Clearing one worker's chapter slots should reset them to idle."""
    dash = PipelineDashboard(10, 1, "List", "Model", chapter_concurrency=3)
    dash.start_chapter_worker("vid1:1", "vid1", "Busy")
    dash.start_chapter_worker("vid1:2", "vid1", "Also busy")
    dash.start_chapter_worker("vid2:1", "vid2", "Other video")

    dash.clear_chapter_workers("vid1")

    first_slot = dash.chapter_progress.tasks[dash.chapter_tasks[0]]
    second_slot = dash.chapter_progress.tasks[dash.chapter_tasks[1]]
    third_slot = dash.chapter_progress.tasks[dash.chapter_tasks[2]]

    assert first_slot.description == "[dim]Idle[/dim]"
    assert second_slot.description == "[dim]Idle[/dim]"
    assert "Other video" in third_slot.description


def test_dashboard_start_chapter_worker_ignores_when_no_slots() -> None:
    """No chapter worker should start when dashboard chapter concurrency is zero."""
    dash = PipelineDashboard(10, 1, "List", "Model", chapter_concurrency=0)

    dash.start_chapter_worker("vid1:1", "vid1", "Busy")

    assert dash.chapter_tasks == []


def test_dashboard_start_chapter_worker_drops_when_all_slots_busy() -> None:
    """Extra chapter jobs should be ignored when all chapter slots are occupied."""
    dash = PipelineDashboard(10, 1, "List", "Model", chapter_concurrency=1)
    dash.start_chapter_worker("vid1:1", "vid1", "Busy")
    original = dash.chapter_progress.tasks[dash.chapter_tasks[0]].description

    dash.start_chapter_worker("vid2:1", "vid2", "Other busy")

    assert dash.chapter_progress.tasks[dash.chapter_tasks[0]].description == original


def test_dashboard_update_and_complete_missing_chapter_slot_are_safe() -> None:
    """Unknown chapter keys should not raise during update or completion."""
    dash = PipelineDashboard(10, 1, "List", "Model", chapter_concurrency=1)

    dash.update_chapter_worker("missing", "Ignored")
    dash.complete_chapter_worker("missing")

    assert dash.chapter_progress.tasks[dash.chapter_tasks[0]].description == (
        "[dim]Idle[/dim]"
    )


def test_dashboard_updates_invalid_index():
    """Test updating worker with invalid index (should be safe)."""
    dash = PipelineDashboard(10, 2, "List", "Model")

    # Should not raise exception
    dash.update_worker(99, "Processing...")


def test_dashboard_completion():
    """Test adding completion."""
    dash = PipelineDashboard(10, 1, "List", "Model")

    dash.add_completion("Video 1")

    assert "Video 1" in dash.recent_completions
    assert dash.overall_progress.tasks[0].completed == 1


def test_dashboard_skipped_completion_tracks_skipped_count() -> None:
    """Skipped videos should increment the skipped counter, not completed."""
    dash = PipelineDashboard(10, 1, "List", "Model")

    dash.add_skipped("Video 1")

    assert "Video 1 (skipped)" in dash.recent_completions
    assert dash.skipped_count == 1
    assert dash.completed_count == 0


def test_dashboard_failure():
    """Test adding failure."""
    dash = PipelineDashboard(10, 1, "List", "Model")

    dash.add_failure("Video 2")

    assert "Video 2" in dash.recent_failures
    assert dash.overall_progress.tasks[0].completed == 1  # Failures count as done


def test_dashboard_total_update():
    """Batch mode should be able to expand the overall total at runtime."""
    dash = PipelineDashboard(0, 1, "List", "Model")

    dash.set_total_videos(4)

    assert dash.overall_progress.tasks[0].total == 4


def test_dashboard_update_overall_status() -> None:
    """Overall progress description should be mutable at runtime."""
    dash = PipelineDashboard(1, 1, "List", "Model")

    dash.update_overall_status("Resolving playlist")

    assert dash.overall_progress.tasks[dash.overall_task].description == (
        "Resolving playlist"
    )


def test_dashboard_rendering_truncates_long_header_context() -> None:
    """Header run, model, and output values should clamp before rendering."""
    long_source = "Source-" + "A" * DASHBOARD_ACTIVITY_TITLE_LIMIT + "TAILSOURCE"
    long_model = "Model-" + "B" * DASHBOARD_CONFIG_VALUE_LIMIT + "TAILMODEL"
    long_output = "/tmp/" + "C" * DASHBOARD_CONFIG_VALUE_LIMIT + "TAILOUTPUT"
    dash = PipelineDashboard(
        1,
        1,
        "List",
        long_model,
        run_label=long_source,
        output_path=long_output,
    )

    console = Console(width=240)
    with console.capture() as capture:
        console.print(dash)

    output = capture.get()
    assert long_source not in output
    assert long_model not in output
    assert long_output not in output
    assert f"{long_source[:DASHBOARD_ACTIVITY_TITLE_LIMIT]}…" in output
    assert f"{long_model[:DASHBOARD_CONFIG_VALUE_LIMIT]}…" in output
    assert f"{long_output[:DASHBOARD_CONFIG_VALUE_LIMIT]}…" in output
    assert "TAILSOURCE" not in output
    assert "TAILMODEL" not in output
    assert "TAILOUTPUT" not in output


def test_dashboard_rendering_shows_safe_config_items() -> None:
    """Dashboard should show config items that callers have already made safe."""
    dash = PipelineDashboard(
        10,
        1,
        "List",
        "Model",
        config_items=(
            DashboardConfigItem("Output", "./notes"),
            DashboardConfigItem("Formats", "markdown, pdf"),
            DashboardConfigItem("Cookies", "configured: cookies.txt"),
            DashboardConfigItem("API key", "present"),
        ),
    )

    console = Console(width=180)
    with console.capture() as capture:
        console.print(dash)

    output = capture.get()
    assert "Run setup" in output
    assert "Output" in output
    assert "./notes" in output
    assert "Formats" in output
    assert "markdown, pdf" in output
    assert "Cookies" in output
    assert "configured:" in output
    assert "cookies.txt" in output
    assert "API" in output
    assert "present" in output


def test_dashboard_rendering_shows_progress_summary_counts() -> None:
    """Dashboard should summarize completed, skipped, failed, and queued work."""
    dash = PipelineDashboard(5, 2, "List", "Model")
    dash.update_worker_state(
        0, phase="Generation", title="Video A", detail="chunks 2/5"
    )
    dash.add_completion("Video Done")
    dash.add_skipped("Video Cached")
    dash.add_failure("Video Failed")

    console = Console(width=180)
    with console.capture() as capture:
        console.print(dash)

    output = capture.get()
    assert "Progress" in output
    assert "Completed" in output
    assert "Skipped" in output
    assert "Failed" in output
    assert "Running" in output
    assert "Queued" in output


def test_dashboard_rendering_shows_structured_worker_state() -> None:
    """Detailed worker state should render phase, title, and progress detail."""
    dash = PipelineDashboard(10, 2, "List", "Model")

    dash.update_worker_state(
        0,
        phase="Generation",
        title="Video A",
        detail="chunks 2/5",
    )

    console = Console(width=120)
    with console.capture() as capture:
        console.print(dash)

    output = capture.get()
    assert "Video jobs" in output
    assert "Generation" in output
    assert "Video A" in output
    assert "chunks 2/5" in output


def test_dashboard_rendering():
    """Test that __rich__ returns a renderable Panel."""
    dash = PipelineDashboard(10, 1, "List", "Model", chapter_concurrency=1)

    # Add some data to render
    dash.add_completion("Completed Video")
    dash.add_failure("Failed Video")
    dash.start_chapter_worker("vid1:1", "vid1", "Chapter slot")

    renderable = dash.__rich__()

    assert isinstance(renderable, Panel)
    # Rendering validation via Console
    console = Console(width=100)
    with console.capture() as capture:
        console.print(renderable)

    output = capture.get()
    assert "Completed Video" in output
    assert "Failed Video" in output
    assert "Chapter jobs" in output
    assert "List" in output
    assert "Model" in output


def test_dashboard_rendering_shows_failures_before_completions():
    """Recent failures should render ahead of completions."""
    dash = PipelineDashboard(10, 1, "List", "Model")
    dash.add_completion("Completed Video")
    dash.add_failure("Failed Video")

    console = Console(width=100)
    with console.capture() as capture:
        console.print(dash)

    output = capture.get()
    assert output.index("Failed Video") < output.index("Completed Video")


def test_dashboard_rendering_uses_unicode_ellipsis_for_long_titles():
    """Long activity titles should clamp with a single Unicode ellipsis."""
    dash = PipelineDashboard(10, 1, "List", "Model")
    dash.add_completion("A" * 80)

    console = Console(width=100)
    with console.capture() as capture:
        console.print(dash)

    output = capture.get()
    assert "…" in output


def test_dashboard_rendering_empty():
    """Test rendering with no activity."""
    dash = PipelineDashboard(10, 1, "List", "Model")

    console = Console(width=100)
    with console.capture() as capture:
        console.print(dash)

    output = capture.get()
    assert "Waiting for the first result" in output


def test_dashboard_rendering_without_workers_omits_active_tasks() -> None:
    """Zero-worker dashboards should omit the active-tasks section."""
    dash = PipelineDashboard(10, 0, "List", "Model")

    console = Console(width=100)
    with console.capture() as capture:
        console.print(dash)

    output = capture.get()
    assert "Video jobs" not in output
    assert "Latest results" in output
