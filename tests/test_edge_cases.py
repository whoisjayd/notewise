import json
from unittest.mock import MagicMock, patch

import httpx

from yt_study.core.telemetry import Telemetry
from yt_study.core.updates import get_latest_version
from yt_study.ui.web import WebVisualizer


# --- Telemetry Edge Cases ---


def test_telemetry_posthog_timeout(tmp_path):
    with (
        patch("posthog.capture") as mock_capture,
        patch("pathlib.Path.home", return_value=tmp_path),
        patch("yt_study.core.telemetry.config") as mock_config,
    ):
        mock_config.telemetry_enabled = True
        # Force capture to raise an exception (like a timeout)
        mock_capture.side_effect = Exception("Timeout")

        telemetry = Telemetry()
        # Should not raise exception
        telemetry.capture_event("test_event")

        mock_capture.assert_called_once()


def test_telemetry_directory_unwritable(tmp_path):
    # Create a file where the directory should be to make it unwritable
    unwritable_dir = tmp_path / ".yt-study"
    unwritable_dir.touch()

    with patch("pathlib.Path.home", return_value=tmp_path):
        telemetry = Telemetry()
        # Should fallback to CWD
        assert ".telemetry" in str(telemetry.telemetry_dir)
        assert telemetry.telemetry_dir.exists()


# --- Update Edge Cases ---


def test_updates_pypi_404():
    with patch("httpx.Client.get") as mock_get:
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=mock_response
        )
        mock_get.return_value = mock_response

        assert get_latest_version() is None


def test_updates_malformed_json():
    with patch("httpx.Client.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.side_effect = json.JSONDecodeError("msg", "doc", 0)
        mock_get.return_value = mock_response

        assert get_latest_version() is None


def test_updates_empty_json():
    with patch("httpx.Client.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {}
        mock_get.return_value = mock_response

        assert get_latest_version() is None


# --- Web Visualizer Edge Cases ---


def test_web_visualizer_empty_dir(tmp_path):
    viz = WebVisualizer(tmp_path)
    assert viz.tree_data == []


def test_web_visualizer_corrupted_md(tmp_path):
    project_dir = tmp_path / "test_123"
    project_dir.mkdir()
    # New UI looks for {item.name}.md or chapters/
    md_file = project_dir / "test_123.md"
    md_file.write_bytes(b"\xff\xfe\xfd")  # Corrupted bytes

    viz = WebVisualizer(tmp_path)
    # The scan should find it as a standalone video
    assert len(viz.tree_data) == 1
    assert viz.tree_data[0]["label"] == "Videos"
    assert len(viz.tree_data[0]["children"]) == 1

    # Mock UI components
    viz.markdown_view = MagicMock()
    viz.title_label = MagicMock()
    viz.editor_container = MagicMock()
    viz.edit_btn = MagicMock()

    # Should handle encoding error gracefully via try-except
    with patch("yt_study.ui.web.ui") as mock_ui:
        viz.load_content(md_file, "123")
        mock_ui.notify.assert_called()
