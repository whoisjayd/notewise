"""Tests for CLI entry point."""

import asyncio
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from yt_study.cli.app import app
from yt_study.errors import VideoUnavailableError as PublicAccessRequiredError
from yt_study.pipeline.core import (
    EventType,
    PipelineEvent,
    PipelineMetrics,
    PipelineResult,
)


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


def _make_pipeline_result(total: int = 1, success: int = 1) -> PipelineResult:
    return PipelineResult(
        success_count=success,
        failure_count=total - success,
        total_count=total,
        video_ids=["dQw4w9WgXcQ"],
        errors={},
        metrics=PipelineMetrics(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            cost_usd=0.015,
            transcript_seconds=1.2,
            generation_seconds=2.3,
        ),
    )


def _make_parsed_playlist(playlist_id: str = "PL123"):
    """Return a mock ParsedURL for a playlist."""
    parsed = MagicMock()
    parsed.url_type = "playlist"
    parsed.video_id = None
    parsed.playlist_id = playlist_id
    return parsed


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_config_exists():
    with patch("yt_study.cli.app.check_config_exists", return_value=True):
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
    dashboard_instance.configure_mock(recent_completions=[], recent_failures=[])

    with (
        patch(  # type: ignore[misc]
            "yt_study.cli.app.CorePipeline",
            return_value=pipeline_instance,
        ) as mock_cls,
        patch(
            "yt_study.cli.app.parse_youtube_url",
            return_value=_make_parsed_video(),
        ),
        patch("yt_study.cli.app.config") as mock_config,
        patch(
            "yt_study.cli.app.PipelineDashboard",
            return_value=dashboard_instance,
        ),
        patch("yt_study.cli.app.Live"),
    ):
        mock_config.default_model = "gemini/gemini-2.5-flash"
        mock_config.default_output_dir = tmp_path
        mock_config.default_languages = ["en"]
        mock_config.temperature = 0.7
        mock_config.max_tokens = None
        mock_config.max_concurrent_videos = 5
        mock_config.youtube_requests_per_minute = 10
        mock_config.youtube_cookie_file = None
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
        patch("yt_study.cli.app.check_config_exists", return_value=True),
        patch(
            "yt_study.cli.app.parse_youtube_url",
            return_value=_make_parsed_video(),
        ),
        patch(
            "yt_study.config.AppSettings.get_api_key_name_for_model",
            return_value="FAKE_KEY",
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
    with patch("yt_study.cli.app.run_setup_wizard") as mock_wizard:
        result = runner.invoke(app, ["setup"])
        assert result.exit_code == 0
        assert mock_wizard.call_count >= 1
        mock_wizard.assert_any_call(force=False)


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


def test_process_batch_file_runs_items_concurrently(tmp_path):
    """Batch-file entries should start in parallel up to the configured worker count."""
    batch_file = tmp_path / "urls.txt"
    batch_file.write_text(
        "https://youtube.com/watch?v=vid1\nhttps://youtube.com/watch?v=vid2"
    )

    first_started = None
    second_started = None

    async def _run(video_ids, on_event=None):  # noqa: ANN001, ARG001
        nonlocal first_started, second_started
        if first_started is None or second_started is None:
            first_started = asyncio.Event()
            second_started = asyncio.Event()

        current_id = video_ids[0]
        if current_id == "vid1":
            first_started.set()
            await asyncio.wait_for(second_started.wait(), timeout=0.2)
        else:
            await asyncio.wait_for(first_started.wait(), timeout=0.2)
            second_started.set()

        return PipelineResult(
            success_count=1,
            failure_count=0,
            total_count=1,
            video_ids=video_ids,
            errors={},
            metrics=PipelineMetrics(),
        )

    def _parse(url):  # noqa: ANN001
        return _make_parsed_video(url.rsplit("=", 1)[-1])

    pipeline_instance = MagicMock()
    pipeline_instance.run = AsyncMock(side_effect=_run)

    with (
        patch("yt_study.cli.app.check_config_exists", return_value=True),
        patch(
            "yt_study.cli.app.CorePipeline",
            return_value=pipeline_instance,
        ),
        patch("yt_study.cli.app.parse_youtube_url", side_effect=_parse),
        patch("yt_study.cli.app.config") as mock_config,
    ):
        mock_config.default_model = "gemini/gemini-2.5-flash"
        mock_config.default_output_dir = tmp_path
        mock_config.default_languages = ["en"]
        mock_config.temperature = 0.7
        mock_config.max_tokens = None
        mock_config.max_concurrent_videos = 2
        mock_config.youtube_requests_per_minute = 10
        mock_config.youtube_cookie_file = None
        mock_config.get_api_key_name_for_model.return_value = None

        result = runner.invoke(app, ["process", str(batch_file), "--no-ui"])

    assert result.exit_code == 0
    assert pipeline_instance.run.await_count == 2


def test_process_batch_file_expands_playlist_into_shared_video_jobs(tmp_path):
    """Batch playlist URLs should enqueue per-video jobs into the shared pool."""
    batch_file = tmp_path / "urls.txt"
    batch_file.write_text(
        "\n".join(
            [
                "https://youtube.com/playlist?list=PL_BATCH",
                "https://youtube.com/watch?v=solo123",
            ]
        )
    )

    def _parse(url):  # noqa: ANN001
        if "playlist" in url:
            return _make_parsed_playlist("PL_BATCH")
        return _make_parsed_video(url.rsplit("=", 1)[-1])

    async def _run(video_ids, on_event=None):  # noqa: ANN001, ARG001
        return PipelineResult(
            success_count=1,
            failure_count=0,
            total_count=1,
            video_ids=video_ids,
            errors={},
            metrics=PipelineMetrics(),
        )

    pipeline_instance = MagicMock()
    pipeline_instance.run = AsyncMock(side_effect=_run)

    with (
        patch("yt_study.cli.app.check_config_exists", return_value=True),
        patch(
            "yt_study.cli.app.CorePipeline",
            return_value=pipeline_instance,
        ),
        patch("yt_study.cli.app.parse_youtube_url", side_effect=_parse),
        patch(
            "yt_study.cli.app.extract_playlist_videos",
            new_callable=AsyncMock,
            return_value=["pl_vid1", "pl_vid2"],
        ),
        patch(
            "yt_study.cli.app.get_playlist_info",
            return_value=("Batch Playlist", 2),
        ),
        patch("yt_study.cli.app.config") as mock_config,
    ):
        mock_config.default_model = "gemini/gemini-2.5-flash"
        mock_config.default_output_dir = tmp_path
        mock_config.default_languages = ["en"]
        mock_config.temperature = 0.7
        mock_config.max_tokens = None
        mock_config.max_concurrent_videos = 2
        mock_config.youtube_requests_per_minute = 10
        mock_config.youtube_cookie_file = None
        mock_config.get_api_key_name_for_model.return_value = None

        result = runner.invoke(app, ["process", str(batch_file), "--no-ui"])

    assert result.exit_code == 0
    assert pipeline_instance.run.await_count == 3
    queued_video_ids = sorted(
        call.args[0][0] for call in pipeline_instance.run.await_args_list
    )
    assert queued_video_ids == ["pl_vid1", "pl_vid2", "solo123"]


def test_process_batch_file_aggregates_private_video_and_playlist_failures(tmp_path):
    """Private batch entries should not block other items."""
    batch_file = tmp_path / "urls.txt"
    batch_file.write_text(
        "\n".join(
            [
                "https://youtube.com/watch?v=public123",
                "https://youtube.com/watch?v=private123",
                "https://youtube.com/playlist?list=PL_PRIVATE",
            ]
        )
    )

    def _parse(url):  # noqa: ANN001
        if "playlist" in url:
            return _make_parsed_playlist("PL_PRIVATE")
        return _make_parsed_video(url.rsplit("=", 1)[-1])

    async def _run(video_ids, on_event=None):  # noqa: ANN001, ARG001
        video_id = video_ids[0]
        if video_id == "private123":
            return PipelineResult(
                success_count=0,
                failure_count=1,
                total_count=1,
                video_ids=video_ids,
                errors={
                    "private123": (
                        "Private YouTube videos are not supported. "
                        "Make the video unlisted or public to process it."
                    )
                },
                metrics=PipelineMetrics(),
            )
        return PipelineResult(
            success_count=1,
            failure_count=0,
            total_count=1,
            video_ids=video_ids,
            errors={},
            metrics=PipelineMetrics(),
        )

    pipeline_instance = MagicMock()
    pipeline_instance.run = AsyncMock(side_effect=_run)

    with (
        patch("yt_study.cli.app.check_config_exists", return_value=True),
        patch(
            "yt_study.cli.app.CorePipeline",
            return_value=pipeline_instance,
        ),
        patch("yt_study.cli.app.parse_youtube_url", side_effect=_parse),
        patch(
            "yt_study.cli.app.extract_playlist_videos",
            new_callable=AsyncMock,
            side_effect=PublicAccessRequiredError(
                "Private YouTube playlists are not supported. "
                "Make the playlist unlisted or public to process it."
            ),
        ),
        patch(
            "yt_study.cli.app.get_playlist_info", new_callable=AsyncMock
        ) as mock_playlist_info,
        patch("yt_study.cli.app.config") as mock_config,
    ):
        mock_config.default_model = "gemini/gemini-2.5-flash"
        mock_config.default_output_dir = tmp_path
        mock_config.default_languages = ["en"]
        mock_config.temperature = 0.7
        mock_config.max_tokens = None
        mock_config.max_concurrent_videos = 3
        mock_config.get_api_key_name_for_model.return_value = None

        result = runner.invoke(app, ["process", str(batch_file), "--no-ui"])

    assert result.exit_code == 1
    assert "Batch Completed with Failures" in result.output
    assert "private123" in result.output
    assert "Private YouTube videos are not supported" in result.output
    assert "PL_PRIVATE" in result.output
    assert "Private YouTube playlists are not supported" in result.output
    assert "Videos completed successfully: 1/2" in result.output
    assert pipeline_instance.run.await_count == 2
    mock_playlist_info.assert_not_called()


def test_process_batch_file_empty(mock_config_exists, mock_pipeline, tmp_path):  # noqa: ARG001
    """Test processing an empty batch file prints a warning."""
    _, pipeline_instance = mock_pipeline
    batch_file = tmp_path / "empty.txt"
    batch_file.write_text("")

    result = runner.invoke(app, ["process", str(batch_file)])

    assert result.exit_code == 1
    assert "The batch file is empty." in result.stdout
    pipeline_instance.run.assert_not_awaited()


def test_process_batch_file_error(mock_config_exists, mock_pipeline, tmp_path):  # noqa: ARG001
    """Test error reading batch file prints an error message."""
    batch_file = tmp_path / "restricted.txt"
    batch_file.touch()

    with patch("pathlib.Path.read_text", side_effect=OSError("Access denied")):
        result = runner.invoke(app, ["process", str(batch_file)])

    assert result.exit_code == 1
    assert "Could not read the batch file" in result.stdout


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
        patch("yt_study.cli.app.check_config_exists", return_value=False),
        patch("yt_study.cli.app.run_setup_wizard") as mock_setup,
    ):
        runner.invoke(app, ["process", "url"])
        assert mock_setup.call_count >= 1


def test_process_keyboard_interrupt(mock_config_exists, mock_pipeline):  # noqa: ARG001
    """Test KeyboardInterrupt is caught and exits with code 1."""
    _, pipeline_instance = mock_pipeline
    pipeline_instance.run.side_effect = KeyboardInterrupt()

    result = runner.invoke(app, ["process", _VIDEO_URL])

    assert result.exit_code == 1
    assert "Processing Stopped" in result.stdout
    assert "interrupted before it finished" in result.stdout


def test_process_general_exception(mock_config_exists, mock_pipeline):  # noqa: ARG001
    """Test unhandled exceptions are caught and exit with code 1."""
    _, pipeline_instance = mock_pipeline
    pipeline_instance.run.side_effect = Exception("Boom")

    result = runner.invoke(app, ["process", _VIDEO_URL])

    assert result.exit_code == 1
    assert "Unexpected Error" in result.stdout
    assert "internal error" in result.stdout
    assert "Current log:" in result.stdout


def test_process_invalid_url(mock_config_exists, mock_pipeline, tmp_path):  # noqa: ARG001
    """Invalid URLs should fail the command for shell automation."""
    with patch(
        "yt_study.cli.app.parse_youtube_url",
        side_effect=ValueError("Not a YouTube URL"),
    ):
        result = runner.invoke(app, ["process", "not-a-url"])

    assert result.exit_code == 1
    assert "Input Error" in result.stdout


def test_process_invalid_url_reports_input_error_before_api_key(monkeypatch):
    """Invalid inputs should not be masked by missing model credentials."""
    monkeypatch.delenv("FAKE_KEY", raising=False)

    with (
        patch("yt_study.cli.app.check_config_exists", return_value=True),
        patch(
            "yt_study.config.AppSettings.get_api_key_name_for_model",
            return_value="FAKE_KEY",
        ),
        patch(
            "yt_study.cli.app.parse_youtube_url",
            side_effect=ValueError("Not a YouTube URL"),
        ),
    ):
        result = runner.invoke(app, ["process", "not-a-url"])

    assert result.exit_code == 1
    assert "Input Error" in result.stdout
    assert "Missing API Key" not in result.stdout


def test_process_missing_batch_file_reports_file_error():
    """Missing batch-file paths should not be misreported as invalid YouTube URLs."""
    with patch("yt_study.cli.app.check_config_exists", return_value=True):
        result = runner.invoke(app, ["process", "missing_urls.txt"])

    assert result.exit_code == 1
    assert "Batch file does not exist" in result.stdout
    assert "Invalid YouTube URL" not in result.stdout


def test_process_missing_nested_batch_file_reports_file_error():
    """Explicit local paths with separators should also be treated as file inputs."""
    with patch("yt_study.cli.app.check_config_exists", return_value=True):
        result = runner.invoke(app, ["process", "batches/urls"])

    assert result.exit_code == 1
    assert "Batch file does not exist" in result.stdout
    assert "Invalid YouTube URL" not in result.stdout


# ---------------------------------------------------------------------------
# process command — headless / --no-ui mode (#37)
# ---------------------------------------------------------------------------


def test_process_no_ui_flag_runs_without_dashboard(
    mock_config_exists,  # noqa: ARG001
    mock_pipeline,
):
    """--no-ui skips PipelineDashboard and still runs the pipeline."""
    _, pipeline_instance = mock_pipeline
    with patch("yt_study.cli.app.PipelineDashboard") as mock_dashboard_cls:
        result = runner.invoke(app, ["process", _VIDEO_URL, "--no-ui"])

    assert result.exit_code == 0
    pipeline_instance.run.assert_awaited_once()
    mock_dashboard_cls.assert_not_called()


def test_process_no_ui_prints_done_summary(
    mock_config_exists,  # noqa: ARG001
    tmp_path,
):
    """--no-ui prints a plain 'Done: N/N succeeded.' summary line."""
    real_result = PipelineResult(
        success_count=1,
        failure_count=0,
        total_count=1,
        video_ids=["dQw4w9WgXcQ"],
        errors={},
        metrics=PipelineMetrics(
            prompt_tokens=11,
            completion_tokens=7,
            total_tokens=18,
            cost_usd=0.0018,
            transcript_seconds=0.5,
            generation_seconds=0.8,
        ),
    )
    pipeline_instance = MagicMock()
    pipeline_instance.run = AsyncMock(return_value=real_result)

    with (
        patch(
            "yt_study.cli.app.CorePipeline",
            return_value=pipeline_instance,
        ),
        patch(
            "yt_study.cli.app.parse_youtube_url",
            return_value=_make_parsed_video(),
        ),
        patch("yt_study.cli.app.config") as mock_config,
        patch("yt_study.cli.app.check_config_exists", return_value=True),
    ):
        mock_config.default_model = "gemini/gemini-2.5-flash"
        mock_config.default_output_dir = tmp_path
        mock_config.default_languages = ["en"]
        mock_config.temperature = 0.7
        mock_config.max_tokens = None
        mock_config.max_concurrent_videos = 5
        mock_config.youtube_requests_per_minute = 10
        mock_config.youtube_cookie_file = None
        mock_config.get_api_key_name_for_model.return_value = None
        result = runner.invoke(app, ["process", _VIDEO_URL, "--no-ui"])

    assert result.exit_code == 0
    assert "Done:" in result.output
    assert "1/1 succeeded" in result.output


def test_process_no_ui_cost_summary_handles_string_metrics(
    mock_config_exists,  # noqa: ARG001
    tmp_path,
):
    """Cost summary should tolerate string metrics without crashing."""

    class StringMetrics:
        prompt_tokens = "9"
        completion_tokens = "6"
        total_tokens = "15"
        cost_usd = "0.0045"
        transcript_seconds = "1.5"
        generation_seconds = "2.5"

    result_obj = PipelineResult(
        success_count=1,
        failure_count=0,
        total_count=1,
        video_ids=["dQw4w9WgXcQ"],
        errors={},
        metrics=StringMetrics(),  # type: ignore[arg-type]
    )
    pipeline_instance = MagicMock()
    pipeline_instance.run = AsyncMock(return_value=result_obj)

    with (
        patch(
            "yt_study.cli.app.CorePipeline",
            return_value=pipeline_instance,
        ),
        patch(
            "yt_study.cli.app.parse_youtube_url",
            return_value=_make_parsed_video(),
        ),
        patch("yt_study.cli.app.config") as mock_config,
        patch("yt_study.cli.app.check_config_exists", return_value=True),
    ):
        mock_config.default_model = "gemini/gemini-2.5-flash"
        mock_config.default_output_dir = tmp_path
        mock_config.default_languages = ["en"]
        mock_config.temperature = 0.7
        mock_config.max_tokens = None
        mock_config.max_concurrent_videos = 5
        mock_config.youtube_requests_per_minute = 10
        mock_config.youtube_cookie_file = None
        mock_config.get_api_key_name_for_model.return_value = None
        result = runner.invoke(app, ["process", _VIDEO_URL, "--no-ui"])

    assert result.exit_code == 0
    assert "Cost Summary" in result.output
    assert "Estimated Cost (USD)" in result.output


def test_process_ui_event_bridge_and_cost_summary_coercion(
    mock_config_exists,  # noqa: ARG001
    tmp_path,
):
    """UI path should exercise worker slot updates and robust metric coercion."""

    class MixedMetrics:
        prompt_tokens = True
        completion_tokens = 5.7
        total_tokens = "not-an-int"
        cost_usd = "not-a-float"
        transcript_seconds = "bad-float"
        generation_seconds = True

    async def _run_with_events(_video_ids, on_event=None):  # noqa: ANN001
        if on_event:
            on_event(
                PipelineEvent(
                    event_type=EventType.METADATA_START,
                    video_id="vid1",
                    title="Video One",
                )
            )
            on_event(
                PipelineEvent(
                    event_type=EventType.CHUNK_GENERATING,
                    video_id="vid1",
                    title="Video One",
                    chunk_number=1,
                    total_chunks=2,
                )
            )
            on_event(
                PipelineEvent(
                    event_type=EventType.VIDEO_SUCCESS,
                    video_id="vid1",
                    title="Video One",
                )
            )
            on_event(
                PipelineEvent(
                    event_type=EventType.METADATA_START,
                    video_id="vid2",
                    title="Video Two",
                )
            )
            on_event(
                PipelineEvent(
                    event_type=EventType.VIDEO_FAILED,
                    video_id="vid2",
                    title="Video Two",
                    error="boom",
                )
            )
        return PipelineResult(
            success_count=1,
            failure_count=1,
            total_count=2,
            video_ids=["vid1", "vid2"],
            errors={"vid2": "boom"},
            metrics=MixedMetrics(),  # type: ignore[arg-type]
        )

    pipeline_instance = MagicMock()
    pipeline_instance.run = AsyncMock(side_effect=_run_with_events)
    dashboard_instance = MagicMock()
    dashboard_instance.configure_mock(recent_completions=[], recent_failures=[])

    with (
        patch("yt_study.cli.app.CorePipeline", return_value=pipeline_instance),
        patch(
            "yt_study.cli.app.parse_youtube_url",
            return_value=_make_parsed_playlist("PL_UI"),
        ),
        patch(
            "yt_study.cli.app.get_playlist_info", new=AsyncMock(return_value=("P", 2))
        ),
        patch(
            "yt_study.cli.app.extract_playlist_videos",
            new_callable=AsyncMock,
            return_value=["vid1", "vid2"],
        ),
        patch("yt_study.cli.app.config") as mock_config,
        patch("yt_study.cli.app.PipelineDashboard", return_value=dashboard_instance),
        patch("yt_study.cli.app.Live"),
    ):
        mock_config.default_model = "gemini/gemini-2.5-flash"
        mock_config.default_output_dir = tmp_path
        mock_config.default_languages = ["en"]
        mock_config.temperature = 0.7
        mock_config.max_tokens = None
        mock_config.max_concurrent_videos = 5
        mock_config.youtube_requests_per_minute = 10
        mock_config.youtube_cookie_file = None
        mock_config.get_api_key_name_for_model.return_value = None

        result = runner.invoke(
            app, ["process", "https://youtube.com/playlist?list=PL_UI"]
        )

    assert result.exit_code == 1
    assert "Processing Failed" in result.output
    assert "Completed successfully: 1/2" in result.output
    assert "Processing Summary" not in result.output
    assert "Cost Summary" not in result.output
    assert "boom" in result.output
    assert "Current log:" in result.output


def test_process_ui_shows_detailed_pipeline_states(
    mock_config_exists,  # noqa: ARG001
    tmp_path,
):
    """Rich UI should show detailed internal pipeline phases."""

    async def _run_with_generation_events(_video_ids, on_event=None):  # noqa: ANN001
        if on_event:
            on_event(
                PipelineEvent(
                    event_type=EventType.METADATA_START,
                    video_id="vid1",
                    title="Video One",
                )
            )
            on_event(
                PipelineEvent(
                    event_type=EventType.TRANSCRIPT_FETCHED,
                    video_id="vid1",
                    title="Video One",
                )
            )
            on_event(
                PipelineEvent(
                    event_type=EventType.CHUNK_GENERATING,
                    video_id="vid1",
                    title="Video One",
                    chunk_number=1,
                    total_chunks=3,
                )
            )
            on_event(
                PipelineEvent(
                    event_type=EventType.GENERATION_COMBINING,
                    video_id="vid1",
                    title="Video One",
                    total_chunks=3,
                )
            )
            on_event(
                PipelineEvent(
                    event_type=EventType.CHAPTER_CHUNK_GENERATING,
                    video_id="vid1",
                    title="Video One",
                    chapter_number=2,
                    total_chapters=5,
                    chunk_number=1,
                    total_chunks=2,
                )
            )
            on_event(
                PipelineEvent(
                    event_type=EventType.CHAPTER_COMBINING,
                    video_id="vid1",
                    title="Video One",
                    chapter_number=2,
                    total_chapters=5,
                    total_chunks=2,
                )
            )
            on_event(
                PipelineEvent(
                    event_type=EventType.QUIZ_GENERATING,
                    video_id="vid1",
                    title="Video One",
                )
            )
            on_event(
                PipelineEvent(
                    event_type=EventType.QUIZ_CHUNK_GENERATING,
                    video_id="vid1",
                    title="Video One",
                    chunk_number=1,
                    total_chunks=2,
                )
            )
            on_event(
                PipelineEvent(
                    event_type=EventType.QUIZ_COMBINING,
                    video_id="vid1",
                    title="Video One",
                    total_chunks=2,
                )
            )
            on_event(
                PipelineEvent(
                    event_type=EventType.QUIZ_COMPLETE,
                    video_id="vid1",
                    title="Video One",
                )
            )
            on_event(
                PipelineEvent(
                    event_type=EventType.GENERATION_COMPLETE,
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
        return PipelineResult(
            success_count=1,
            failure_count=0,
            total_count=1,
            video_ids=["vid1"],
            errors={},
            metrics=PipelineMetrics(),
        )

    pipeline_instance = MagicMock()
    pipeline_instance.run = AsyncMock(side_effect=_run_with_generation_events)
    dashboard_instance = MagicMock()
    dashboard_instance.configure_mock(recent_completions=[], recent_failures=[])

    with (
        patch("yt_study.cli.app.CorePipeline", return_value=pipeline_instance),
        patch(
            "yt_study.cli.app.parse_youtube_url",
            return_value=_make_parsed_video("vid1"),
        ),
        patch("yt_study.cli.app.config") as mock_config,
        patch(
            "yt_study.cli.app.PipelineDashboard",
            return_value=dashboard_instance,
        ),
        patch("yt_study.cli.app.Live"),
    ):
        mock_config.default_model = "gemini/gemini-2.5-flash"
        mock_config.default_output_dir = tmp_path
        mock_config.default_languages = ["en"]
        mock_config.temperature = 0.7
        mock_config.max_tokens = None
        mock_config.max_concurrent_videos = 5
        mock_config.youtube_requests_per_minute = 10
        mock_config.youtube_cookie_file = None
        mock_config.get_api_key_name_for_model.return_value = None

        result = runner.invoke(app, ["process", _VIDEO_URL])

    assert result.exit_code == 0
    statuses = [
        call.args[1] for call in dashboard_instance.update_worker.call_args_list
    ]
    rendered_statuses = "\n".join(statuses)
    assert "Transcript Ready" in rendered_statuses
    assert "Chunk 1/3" in rendered_statuses
    assert "Combining 3 note parts" in rendered_statuses
    assert "Ch 2/5, Part 1/2" in rendered_statuses
    assert "Ch 2/5, Combining 2 parts" in rendered_statuses
    assert "Quiz" in rendered_statuses
    assert "Quiz Part 1/2" in rendered_statuses
    assert "Combining 2 quiz parts" in rendered_statuses
    assert "Quiz Ready" in rendered_statuses
    assert "Generated" in rendered_statuses


def test_process_no_ui_failure_exits_nonzero(
    mock_config_exists,  # noqa: ARG001
    tmp_path,
):
    """Headless runs should return a failing exit code when any video fails."""
    failed_result = PipelineResult(
        success_count=0,
        failure_count=1,
        total_count=1,
        video_ids=["dQw4w9WgXcQ"],
        errors={"dQw4w9WgXcQ": "boom"},
        metrics=PipelineMetrics(),
    )
    pipeline_instance = MagicMock()
    pipeline_instance.run = AsyncMock(return_value=failed_result)

    with (
        patch(
            "yt_study.cli.app.CorePipeline",
            return_value=pipeline_instance,
        ),
        patch(
            "yt_study.cli.app.parse_youtube_url",
            return_value=_make_parsed_video(),
        ),
        patch("yt_study.cli.app.config") as mock_config,
        patch("yt_study.cli.app.check_config_exists", return_value=True),
    ):
        mock_config.default_model = "gemini/gemini-2.5-flash"
        mock_config.default_output_dir = tmp_path
        mock_config.default_languages = ["en"]
        mock_config.temperature = 0.7
        mock_config.max_tokens = None
        mock_config.max_concurrent_videos = 5
        mock_config.youtube_requests_per_minute = 10
        mock_config.youtube_cookie_file = None
        mock_config.get_api_key_name_for_model.return_value = None

        result = runner.invoke(app, ["process", _VIDEO_URL, "--no-ui"])

    assert result.exit_code == 1
    assert "Processing Failed" in result.output
    assert "dQw4w9WgXcQ" in result.output
    assert "boom" in result.output
    assert "Done: 0/1 succeeded." not in result.output
    assert "Cost Summary" not in result.output


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


@pytest.mark.parametrize(
    "args",
    [
        ["--use-oauth"],
        ["--token-file", "token.json"],
        ["--save-oauth-token"],
        ["--auto-refresh-oauth-token"],
    ],
)
def test_process_rejects_removed_youtube_auth_flags(args):
    """Removed YouTube auth flags should fail fast as unknown options.

    Typer/Rich does not consistently echo the rejected option text across
    platforms, so assert only the stable unknown-option behavior.
    """
    result = runner.invoke(app, ["process", _VIDEO_URL, *args])

    assert result.exit_code != 0
    assert "No such option" in result.output


def test_process_rich_ui_formats_skipped_videos_without_markup_leak(
    mock_config_exists,  # noqa: ARG001
    tmp_path,
):
    """Skipped dashboard entries should be plain text instead of raw markup."""

    async def _run_with_skip(video_ids, on_event=None):  # noqa: ARG001
        if on_event is not None:
            on_event(PipelineEvent(event_type=EventType.PIPELINE_START, video_id=""))
            on_event(
                PipelineEvent(
                    event_type=EventType.METADATA_START,
                    video_id="vid1",
                    title="Video One",
                )
            )
            on_event(
                PipelineEvent(
                    event_type=EventType.VIDEO_SKIPPED,
                    video_id="vid1",
                    title="Video One",
                )
            )
            on_event(PipelineEvent(event_type=EventType.PIPELINE_COMPLETE, video_id=""))
        return PipelineResult(
            success_count=1,
            failure_count=0,
            total_count=1,
            video_ids=["vid1"],
            errors={},
            metrics=PipelineMetrics(),
        )

    pipeline_instance = MagicMock()
    pipeline_instance.run = AsyncMock(side_effect=_run_with_skip)
    dashboard_instance = MagicMock()
    dashboard_instance.configure_mock(recent_completions=[], recent_failures=[])

    with (
        patch("yt_study.cli.app.CorePipeline", return_value=pipeline_instance),
        patch(
            "yt_study.cli.app.parse_youtube_url",
            return_value=_make_parsed_video("vid1"),
        ),
        patch("yt_study.cli.app.config") as mock_config,
        patch(
            "yt_study.cli.app.PipelineDashboard",
            return_value=dashboard_instance,
        ),
        patch("yt_study.cli.app.Live"),
    ):
        mock_config.default_model = "gemini/gemini-2.5-flash"
        mock_config.default_output_dir = tmp_path
        mock_config.default_languages = ["en"]
        mock_config.temperature = 0.7
        mock_config.max_tokens = None
        mock_config.max_concurrent_videos = 5
        mock_config.youtube_requests_per_minute = 10
        mock_config.youtube_cookie_file = None
        mock_config.get_api_key_name_for_model.return_value = None

        result = runner.invoke(app, ["process", _VIDEO_URL])

    assert result.exit_code == 0
    dashboard_instance.add_completion.assert_called_with("Video One (skipped)")


def test_process_playlist_deduplicates_video_ids_before_pipeline(
    mock_config_exists,  # noqa: ARG001
    tmp_path,
):
    """Playlist duplicates should be removed before dashboard sizing and run."""
    pipeline_instance = MagicMock()
    pipeline_instance.run = AsyncMock(
        return_value=_make_pipeline_result(total=2, success=2)
    )
    dashboard_instance = MagicMock()
    dashboard_instance.configure_mock(recent_completions=[], recent_failures=[])

    with (
        patch("yt_study.cli.app.CorePipeline", return_value=pipeline_instance),
        patch(
            "yt_study.cli.app.parse_youtube_url",
            return_value=_make_parsed_playlist("PL_DEDUPE"),
        ),
        patch(
            "yt_study.cli.app.get_playlist_info",
            return_value=("Playlist", 3),
        ),
        patch(
            "yt_study.cli.app.extract_playlist_videos",
            new_callable=AsyncMock,
            return_value=["vid1", "vid1", "vid2"],
        ),
        patch("yt_study.cli.app.config") as mock_config,
        patch(
            "yt_study.cli.app.PipelineDashboard",
            return_value=dashboard_instance,
        ) as mock_dashboard_cls,
        patch("yt_study.cli.app.Live"),
    ):
        mock_config.default_model = "gemini/gemini-2.5-flash"
        mock_config.default_output_dir = tmp_path
        mock_config.default_languages = ["en"]
        mock_config.temperature = 0.7
        mock_config.max_tokens = None
        mock_config.max_concurrent_videos = 5
        mock_config.youtube_requests_per_minute = 10
        mock_config.youtube_cookie_file = None
        mock_config.get_api_key_name_for_model.return_value = None

        result = runner.invoke(
            app,
            ["process", "https://youtube.com/playlist?list=PL_DEDUPE"],
        )

    assert result.exit_code == 0
    pipeline_instance.run.assert_awaited_once_with(["vid1", "vid2"], on_event=ANY)
    assert mock_dashboard_cls.call_args.kwargs["total_videos"] == 2


def test_process_private_playlist_shows_clean_error(
    mock_config_exists,  # noqa: ARG001
    tmp_path,
):
    """Private playlists should fail cleanly instead of falling into Fatal Error."""
    with (
        patch(
            "yt_study.cli.app.parse_youtube_url",
            return_value=_make_parsed_playlist("PL_PRIVATE"),
        ),
        patch(
            "yt_study.cli.app.extract_playlist_videos",
            new_callable=AsyncMock,
            side_effect=PublicAccessRequiredError(
                "Private YouTube playlists are not supported. "
                "Make the playlist unlisted or public to process it."
            ),
        ),
        patch(
            "yt_study.cli.app.get_playlist_info", new_callable=AsyncMock
        ) as mock_info,
        patch("yt_study.cli.app.config") as mock_config,
    ):
        mock_config.default_model = "gemini/gemini-2.5-flash"
        mock_config.default_output_dir = tmp_path
        mock_config.default_languages = ["en"]
        mock_config.temperature = 0.7
        mock_config.max_tokens = None
        mock_config.max_concurrent_videos = 5
        mock_config.youtube_requests_per_minute = 10
        mock_config.youtube_cookie_file = None
        mock_config.get_api_key_name_for_model.return_value = None

        result = runner.invoke(
            app, ["process", "https://youtube.com/playlist?list=PL_PRIVATE"]
        )

    assert result.exit_code == 1
    assert "Private YouTube playlists are not supported" in result.output
    assert "Fatal Error" not in result.output
    mock_info.assert_not_called()
