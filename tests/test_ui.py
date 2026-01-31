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
    assert dash.overall_progress.tasks[0].total == 10


def test_dashboard_updates():
    """Test updating worker status."""
    dash = PipelineDashboard(10, 2, "List", "Model")

    # Update worker 0
    dash.update_worker(0, "Processing...")

    # Check if the task description was updated in the progress instance
    task_id = dash.worker_tasks[0]
    assert "Processing..." in dash.worker_progress.tasks[task_id].description


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


def test_dashboard_rendering():
    """Test that __rich__ returns a renderable Panel."""
    dash = PipelineDashboard(10, 1, "List", "Model")

    # Add some data to render
    dash.add_completion("Completed Video")
    dash.add_failure("Failed Video")

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
    assert "List" in output
    assert "Model" in output


def test_dashboard_rendering_empty():
    """Test rendering with no activity."""
    dash = PipelineDashboard(10, 1, "List", "Model")

    console = Console(width=100)
    with console.capture() as capture:
        console.print(dash)

    output = capture.get()
    assert "No videos completed yet" in output
