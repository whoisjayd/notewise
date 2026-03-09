"""Tests for CLI entry point."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from yt_study.cli import app


runner = CliRunner()

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_VIDEO_URL = "https://youtube.com/watch?v=dQw4w9WgXcQ"


def _make_parsed_video(video_id: str = "dQw4w9WgXcQ"):
    """Return a mock ParsedURL for a single video."""
    parsed = MagicMock()
    parsed.url_type = "video"
    parsed.video_id = video_id
    parsed.playlist_id = None
    return parsed


def _make_pipeline_result(total: int = 1, success: int = 1):
    result = MagicMock()
    result.total_count = total
    result.success_count = success
    result.failure_count = total - success
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_config_exists():
    with patch("yt_study.cli.check_config_exists", return_value=True):
        yield


@pytest.fixture
def mock_pipeline(tmp_path):
    """
    Patch CorePipeline (via its source module) and supporting helpers so
    that tests never touch network / LLM.
    """
    pipeline_result = _make_pipeline_result()

    pipeline_instance = MagicMock()
    pipeline_instance.run = AsyncMock(return_value=pipeline_result)

    dashboard_instance = MagicMock()
    dashboard_instance.recent_completions = []
    dashboard_instance.recent_failures = []

    with (
        patch(  # type: ignore[misc]
            "yt_study.core.pipeline.CorePipeline",
            return_value=pipeline_instance,
        ) as mock_cls,
        patch(
            "yt_study.core.youtube.parser.parse_youtube_url",
            return_value=_make_parsed_video(),
        ),
        patch("yt_study.core.config.config") as mock_config,
        patch(
            "yt_study.ui.dashboard.PipelineDashboard",
            return_value=dashboard_instance,
        ),
        patch("rich.live.Live.__enter__", return_value=None),
        patch("rich.live.Live.__exit__", return_value=False),
    ):
        mock_config.default_model = "gemini/gemini-2.0-flash"
        mock_config.default_output_dir = tmp_path
        mock_config.default_languages = ["en"]
        mock_config.temperature = 0.7
        mock_config.max_tokens = None
        mock_config.max_concurrent_videos = 5
        mock_config.get_api_key_name_for_model.return_value = None  # no key needed
        yield mock_cls, pipeline_instance


# ---------------------------------------------------------------------------
# Version / config-path / setup commands (no pipeline involved)
# ---------------------------------------------------------------------------


def test_process_missing_api_key_exits_with_error(monkeypatch):
    """CLI exits with code 1 and helpful message when required API key is missing."""

    # Ensure FAKE_KEY is not set in the environment
    monkeypatch.delenv("FAKE_KEY", raising=False)

    # Patch config to require FAKE_KEY for the selected model
    with (
        patch(
            "yt_study.core.config.config.get_api_key_name_for_model",
            return_value="FAKE_KEY",
        ),
        patch("yt_study.cli.check_config_exists", return_value=True),
        patch(
            "yt_study.core.youtube.parser.parse_youtube_url",
            return_value=_make_parsed_video(),
        ),
    ):
        result = runner.invoke(app, ["process", _VIDEO_URL])

    assert result.exit_code == 1
    # The error message should mention the missing env var name
    assert "FAKE_KEY" in result.output
    # And it should clearly indicate it's about an API key
    assert "Missing API Key" in result.output or "API key" in result.output


def test_version():
    """Test version command."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "version" in result.stdout


def test_config_path_exists(mock_config_exists):  # noqa: ARG001
    """Test config-path command when config exists."""
    with patch("pathlib.Path.exists", return_value=True):
        result = runner.invoke(app, ["config-path"])
        assert result.exit_code == 0
        assert "Configuration file:" in result.stdout


def test_config_path_missing():
    """Test config-path command when config is missing."""
    with patch("pathlib.Path.exists", return_value=False):
        result = runner.invoke(app, ["config-path"])
        assert result.exit_code == 0
        assert "No configuration found" in result.stdout


def test_setup_command():
    """Test setup command triggers wizard."""
    with patch("yt_study.setup_wizard.run_setup_wizard") as mock_wizard:
        result = runner.invoke(app, ["setup"])
        assert result.exit_code == 0
        mock_wizard.assert_called_once()


def test_callback_help():
    """Test callback shows help when no command."""
    result = runner.invoke(app)
    assert result.exit_code == 0
    assert "Usage" in result.stdout


# ---------------------------------------------------------------------------
# process command — happy paths
# ---------------------------------------------------------------------------


def test_process_url_success(mock_config_exists, mock_pipeline):  # noqa: ARG001
    """Test processing a single video URL succeeds."""
    _, pipeline_instance = mock_pipeline
    result = runner.invoke(app, ["process", _VIDEO_URL])

    assert result.exit_code == 0
    pipeline_instance.run.assert_awaited_once()


def test_process_batch_file(mock_config_exists, mock_pipeline, tmp_path):  # noqa: ARG001
    """Test processing a batch file calls pipeline once per URL."""
    _, pipeline_instance = mock_pipeline
    batch_file = tmp_path / "urls.txt"
    batch_file.write_text(f"{_VIDEO_URL}\nhttps://youtube.com/watch?v=abc123")

    result = runner.invoke(app, ["process", str(batch_file)])

    assert result.exit_code == 0
    assert pipeline_instance.run.await_count == 2


def test_process_batch_file_empty(mock_config_exists, mock_pipeline, tmp_path):  # noqa: ARG001
    """Test processing an empty batch file prints a warning."""
    _, pipeline_instance = mock_pipeline
    batch_file = tmp_path / "empty.txt"
    batch_file.write_text("")

    result = runner.invoke(app, ["process", str(batch_file)])

    assert result.exit_code == 0
    assert "Batch file is empty" in result.stdout
    pipeline_instance.run.assert_not_awaited()


def test_process_batch_file_error(mock_config_exists, mock_pipeline, tmp_path):  # noqa: ARG001
    """Test error reading batch file prints an error message."""
    batch_file = tmp_path / "restricted.txt"
    batch_file.touch()

    with patch("pathlib.Path.read_text", side_effect=OSError("Access denied")):
        result = runner.invoke(app, ["process", str(batch_file)])

    assert result.exit_code == 0
    assert "Error reading batch file" in result.stdout


def test_process_with_temperature_flag(mock_config_exists, mock_pipeline):  # noqa: ARG001
    """Test --temperature flag is forwarded to CorePipeline."""
    mock_cls, pipeline_instance = mock_pipeline
    result = runner.invoke(app, ["process", _VIDEO_URL, "--temperature", "0.5"])

    assert result.exit_code == 0
    call_kwargs = mock_cls.call_args[1]
    assert call_kwargs["temperature"] == 0.5
    pipeline_instance.run.assert_awaited_once()


def test_process_with_max_tokens_flag(mock_config_exists, mock_pipeline):  # noqa: ARG001
    """Test --max-tokens flag is forwarded to CorePipeline."""
    mock_cls, pipeline_instance = mock_pipeline
    result = runner.invoke(app, ["process", _VIDEO_URL, "--max-tokens", "2000"])

    assert result.exit_code == 0
    call_kwargs = mock_cls.call_args[1]
    assert call_kwargs["max_tokens"] == 2000
    pipeline_instance.run.assert_awaited_once()


def test_process_with_temperature_and_max_tokens(mock_config_exists, mock_pipeline):  # noqa: ARG001
    """Test both --temperature and --max-tokens flags together."""
    mock_cls, pipeline_instance = mock_pipeline
    result = runner.invoke(
        app,
        ["process", _VIDEO_URL, "--temperature", "0.8", "--max-tokens", "3000"],
    )

    assert result.exit_code == 0
    call_kwargs = mock_cls.call_args[1]
    assert call_kwargs["temperature"] == 0.8
    assert call_kwargs["max_tokens"] == 3000
    pipeline_instance.run.assert_awaited_once()


# ---------------------------------------------------------------------------
# process command — error handling
# ---------------------------------------------------------------------------


def test_process_missing_config():
    """Test that missing config triggers the setup wizard."""
    with (
        patch("yt_study.cli.check_config_exists", return_value=False),
        patch("yt_study.setup_wizard.run_setup_wizard") as mock_setup,
    ):
        runner.invoke(app, ["process", "url"])
        mock_setup.assert_called_once()


def test_process_keyboard_interrupt(mock_config_exists, mock_pipeline):  # noqa: ARG001
    """Test KeyboardInterrupt is caught and exits with code 1."""
    _, pipeline_instance = mock_pipeline
    pipeline_instance.run.side_effect = KeyboardInterrupt()

    result = runner.invoke(app, ["process", _VIDEO_URL])

    assert result.exit_code == 1
    assert "Process interrupted by user" in result.stdout


def test_process_general_exception(mock_config_exists, mock_pipeline):  # noqa: ARG001
    """Test unhandled exceptions are caught and exit with code 1."""
    _, pipeline_instance = mock_pipeline
    pipeline_instance.run.side_effect = Exception("Boom")

    result = runner.invoke(app, ["process", _VIDEO_URL])

    assert result.exit_code == 1
    assert "Fatal Error" in result.stdout
    assert "Boom" in result.stdout


def test_process_invalid_url(mock_config_exists, mock_pipeline, tmp_path):  # noqa: ARG001
    """Test that an invalid URL prints an error message but exits cleanly."""
    with patch(
        "yt_study.core.youtube.parser.parse_youtube_url",
        side_effect=ValueError("Not a YouTube URL"),
    ):
        result = runner.invoke(app, ["process", "not-a-url"])

    assert result.exit_code == 0
    assert "Input Error" in result.stdout


# ---------------------------------------------------------------------------
# process command — headless / --no-ui mode (#37)
# ---------------------------------------------------------------------------


def test_process_no_ui_flag_runs_without_dashboard(
    mock_config_exists,  # noqa: ARG001
    mock_pipeline,
):
    """--no-ui skips PipelineDashboard and still runs the pipeline."""
    _, pipeline_instance = mock_pipeline
    result = runner.invoke(app, ["process", _VIDEO_URL, "--no-ui"])

    assert result.exit_code == 0
    pipeline_instance.run.assert_awaited_once()


def test_process_no_ui_prints_done_summary(
    mock_config_exists,  # noqa: ARG001
    tmp_path,
):
    """--no-ui prints a plain 'Done: N/N succeeded.' summary line."""
    from yt_study.core.pipeline import PipelineResult

    real_result = PipelineResult(
        success_count=1,
        failure_count=0,
        total_count=1,
        video_ids=["dQw4w9WgXcQ"],
        errors={},
    )
    pipeline_instance = MagicMock()
    pipeline_instance.run = AsyncMock(return_value=real_result)

    with (
        patch(
            "yt_study.core.pipeline.CorePipeline",
            return_value=pipeline_instance,
        ),
        patch(
            "yt_study.core.youtube.parser.parse_youtube_url",
            return_value=_make_parsed_video(),
        ),
        patch("yt_study.core.config.config") as mock_config,
        patch("yt_study.cli.check_config_exists", return_value=True),
    ):
        mock_config.default_model = "gemini/gemini-2.0-flash"
        mock_config.default_output_dir = tmp_path
        mock_config.default_languages = ["en"]
        mock_config.temperature = 0.7
        mock_config.max_tokens = None
        mock_config.max_concurrent_videos = 5
        mock_config.get_api_key_name_for_model.return_value = None
        result = runner.invoke(app, ["process", _VIDEO_URL, "--no-ui"])

    assert result.exit_code == 0
    assert "Done:" in result.output
    assert "1/1 succeeded" in result.output


# ---------------------------------------------------------------------------
# process command — quiz flag (#30)
# ---------------------------------------------------------------------------


def test_process_quiz_flag_passed_to_pipeline(
    mock_config_exists,  # noqa: ARG001
    mock_pipeline,
):
    """--quiz is forwarded to CorePipeline as quiz=True."""
    mock_cls, pipeline_instance = mock_pipeline
    result = runner.invoke(app, ["process", _VIDEO_URL, "--quiz"])

    assert result.exit_code == 0
    call_kwargs = mock_cls.call_args.kwargs
    assert call_kwargs.get("quiz") is True
