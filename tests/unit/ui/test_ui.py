"""Tests for UI dashboard."""

from rich.console import Console
from rich.panel import Panel

from yt_study.ui.dashboard import PipelineDashboard


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
    assert "Active Tasks" in output
    assert "Chapter Tasks" in output
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
    assert "No videos completed yet" in output
