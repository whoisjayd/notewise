"""Unit tests for process-scoped custom endpoint options."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, call


if TYPE_CHECKING:
    from pathlib import Path

from rich.console import Console
from typer.testing import CliRunner

from notewise.cli import app as cli_app
from notewise.cli._context import CliProcessContext


runner = CliRunner()


def _process_settings(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        default_model="gateway/default-model",
        default_output_dir=tmp_path,
        default_languages=["en"],
        temperature=0.2,
        max_tokens=None,
        youtube_cookie_file=None,
        get_custom_endpoint_for_model=MagicMock(return_value=None),
    )


def _capture_process_runner(mocker, tmp_path: Path):
    captured: dict[str, object] = {}
    settings = _process_settings(tmp_path)

    class CapturingRunner:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        async def run(self, *_args, **_kwargs) -> bool:
            return False

    mocker.patch.object(cli_app, "_get_config", return_value=settings)
    mocker.patch.object(cli_app, "_load_process_dependencies")
    mocker.patch("notewise.cli._runtime.CliProcessRunner", CapturingRunner)
    mocker.patch("notewise.llm.provider.suppress_litellm_noise")
    mocker.patch("notewise.logging.configure_logging")
    return captured, settings


def test_process_transports_normalized_endpoint_options(mocker, tmp_path: Path) -> None:
    """Explicit custom endpoint options must stay scoped to one process run."""
    captured, settings = _capture_process_runner(mocker, tmp_path)
    settings.get_custom_endpoint_for_model.return_value = (
        "https://stored.example/v1",
        "stored-key",
    )
    normalize = mocker.patch(
        "notewise.llm.custom_endpoint.normalize_openai_base_url",
        return_value="https://gateway.example/v1",
    )

    result = runner.invoke(
        cli_app.app,
        [
            "process",
            "https://youtube.com/watch?v=video",
            "--model",
            "gateway/selected-model",
            "--base-url",
            "https://gateway.example",
            "--api-key",
            "run-key",
        ],
    )

    assert result.exit_code == 0
    normalize.assert_called_once_with("https://gateway.example")
    settings.get_custom_endpoint_for_model.assert_called_once_with(
        "gateway/selected-model"
    )
    assert captured["selected_api_base"] == "https://gateway.example/v1"
    assert captured["selected_api_key"] == "run-key"


def test_process_selects_each_matching_configured_custom_profile(
    mocker,
    tmp_path: Path,
) -> None:
    """Each saved profile must supply its own endpoint credentials."""
    captured_runs: list[dict[str, object]] = []
    settings = _process_settings(tmp_path)
    profiles = {
        "first/model": ("https://first.example/v1", "first-key"),
        "second/model": ("https://second.example/v1", "second-key"),
    }
    settings.get_custom_endpoint_for_model.side_effect = profiles.get

    class CapturingRunner:
        def __init__(self, **kwargs) -> None:
            captured_runs.append(kwargs)

        async def run(self, *_args, **_kwargs) -> bool:
            return False

    mocker.patch.object(cli_app, "_get_config", return_value=settings)
    mocker.patch.object(cli_app, "_load_process_dependencies")
    mocker.patch("notewise.cli._runtime.CliProcessRunner", CapturingRunner)
    mocker.patch("notewise.llm.provider.suppress_litellm_noise")
    mocker.patch("notewise.logging.configure_logging")

    for model in profiles:
        result = runner.invoke(
            cli_app.app,
            ["process", "https://youtube.com/watch?v=video", "--model", model],
        )
        assert result.exit_code == 0

    assert settings.get_custom_endpoint_for_model.call_args_list == [
        call("first/model"),
        call("second/model"),
    ]
    assert [
        (run["selected_model"], run["selected_api_base"], run["selected_api_key"])
        for run in captured_runs
    ] == [
        ("first/model", "https://first.example/v1", "first-key"),
        ("second/model", "https://second.example/v1", "second-key"),
    ]


def test_process_explicit_key_overrides_matching_configured_key(
    mocker,
    tmp_path: Path,
) -> None:
    """A CLI key wins over the key stored for a matching custom endpoint."""
    captured, settings = _capture_process_runner(mocker, tmp_path)
    settings.get_custom_endpoint_for_model.return_value = (
        "https://configured.example/v1",
        "stored-key",
    )

    result = runner.invoke(
        cli_app.app,
        [
            "process",
            "https://youtube.com/watch?v=video",
            "--api-key",
            "run-key",
        ],
    )

    assert result.exit_code == 0
    assert captured["selected_api_base"] == "https://configured.example/v1"
    assert captured["selected_api_key"] == "run-key"


def test_custom_endpoint_skips_static_model_and_key_preflight(tmp_path: Path) -> None:
    """An endpoint-scoped model must not be rejected by the static catalog."""
    config = MagicMock()
    config.get_unsupported_model_message.return_value = "Not in static catalog"
    context = CliProcessContext(
        console=Console(),
        config=config,
        core_pipeline_cls=MagicMock(),
        parse_youtube_url=MagicMock(),
        extract_playlist_videos=MagicMock(),
        get_playlist_info=MagicMock(),
        dashboard_cls=MagicMock(),
        live_cls=MagicMock(),
        selected_model="gateway/gateway-model",
        selected_output=tmp_path,
        selected_output_formats=["md"],
        selected_languages=["en"],
        selected_temperature=0.2,
        selected_max_tokens=None,
        selected_throttle_seconds=0.0,
        force=False,
        no_ui=True,
        quiz=False,
        export_transcript=None,
        timestamps=False,
        chapter_directory_output=False,
        selected_cookie_file=None,
        selected_api_base="https://gateway.example/v1",
        selected_api_key="run-key",
    )

    assert context.ensure_model_supported() is True
    assert context.ensure_api_key_available() is True
    config.get_unsupported_model_message.assert_not_called()
    config.get_missing_config_names_for_model.assert_not_called()
