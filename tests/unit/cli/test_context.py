"""Tests for CLI process context parameter handoff."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from rich.console import Console

from notewise._constants import DEFAULT_TARGET_LANGUAGE
from notewise.cli._context import CliProcessContext


def test_build_pipeline_passes_target_language(tmp_path: Path) -> None:
    """CLI context should forward the requested target language to the pipeline."""
    core_pipeline_cls = MagicMock(return_value=object())
    output_dir = tmp_path / "custom-output"
    context = CliProcessContext(
        console=Console(),
        config=MagicMock(),
        core_pipeline_cls=core_pipeline_cls,
        parse_youtube_url=MagicMock(),
        extract_playlist_videos=MagicMock(),
        get_playlist_info=MagicMock(),
        dashboard_cls=MagicMock(),
        live_cls=MagicMock(),
        selected_model="demo-model",
        selected_output=Path("output"),
        selected_output_formats=["md"],
        selected_languages=["en"],
        selected_target_language="Hindi",
        selected_temperature=0.4,
        selected_max_tokens=1000,
        selected_throttle_seconds=0.0,
        force=False,
        no_ui=False,
        quiz=False,
        export_transcript=None,
        timestamps=False,
        chapter_directory_output=False,
        selected_cookie_file=None,
    )

    context.build_pipeline(output_dir)

    core_pipeline_cls.assert_called_once_with(
        model="demo-model",
        output_dir=output_dir,
        output_formats=["md"],
        languages=["en"],
        target_language="Hindi",
        temperature=0.4,
        max_tokens=1000,
        throttle_seconds=0.0,
        force=False,
        quiz=False,
        export_transcript=None,
        timestamps=False,
        chapter_directory_output=False,
        youtube_cookie_file=None,
        shared_state=None,
    )
    assert not output_dir.exists()


def test_build_pipeline_uses_default_target_language_when_not_overridden(
    tmp_path: Path,
) -> None:
    """CLI context should default the target language when not explicitly provided."""
    core_pipeline_cls = MagicMock(return_value=object())
    output_dir = tmp_path / "custom-output"
    context = CliProcessContext(
        console=Console(),
        config=MagicMock(),
        core_pipeline_cls=core_pipeline_cls,
        parse_youtube_url=MagicMock(),
        extract_playlist_videos=MagicMock(),
        get_playlist_info=MagicMock(),
        dashboard_cls=MagicMock(),
        live_cls=MagicMock(),
        selected_model="demo-model",
        selected_output=Path("output"),
        selected_output_formats=["md"],
        selected_languages=["en"],
        selected_temperature=0.4,
        selected_max_tokens=1000,
        selected_throttle_seconds=0.0,
        force=False,
        no_ui=False,
        quiz=False,
        export_transcript=None,
        timestamps=False,
        chapter_directory_output=False,
        selected_cookie_file=None,
    )

    context.build_pipeline(output_dir)

    core_pipeline_cls.assert_called_once_with(
        model="demo-model",
        output_dir=output_dir,
        output_formats=["md"],
        languages=["en"],
        target_language=DEFAULT_TARGET_LANGUAGE,
        temperature=0.4,
        max_tokens=1000,
        throttle_seconds=0.0,
        force=False,
        quiz=False,
        export_transcript=None,
        timestamps=False,
        chapter_directory_output=False,
        youtube_cookie_file=None,
        shared_state=None,
    )


def test_ensure_selected_output_dir_creates_missing_parent_directories(
    tmp_path: Path,
) -> None:
    """CLI context should create the configured base output directory on demand."""
    output_dir = tmp_path / "nested" / "output"
    context = CliProcessContext(
        console=Console(),
        config=MagicMock(),
        core_pipeline_cls=MagicMock(),
        parse_youtube_url=MagicMock(),
        extract_playlist_videos=MagicMock(),
        get_playlist_info=MagicMock(),
        dashboard_cls=MagicMock(),
        live_cls=MagicMock(),
        selected_model="demo-model",
        selected_output=output_dir,
        selected_output_formats=["md"],
        selected_languages=["en"],
        selected_temperature=0.4,
        selected_max_tokens=1000,
        selected_throttle_seconds=0.0,
        force=False,
        no_ui=False,
        quiz=False,
        export_transcript=None,
        timestamps=False,
        chapter_directory_output=False,
        selected_cookie_file=None,
    )

    context.ensure_selected_output_dir()

    assert output_dir.is_dir()


def _unsupported_model_context(config: object) -> CliProcessContext:
    """Build a minimal CLI context wired to the given config for preflight tests."""
    return CliProcessContext(
        console=MagicMock(),
        config=config,
        core_pipeline_cls=MagicMock(),
        parse_youtube_url=MagicMock(),
        extract_playlist_videos=MagicMock(),
        get_playlist_info=MagicMock(),
        dashboard_cls=MagicMock(),
        live_cls=MagicMock(),
        selected_model="openrouter/stealth/ox-alpha",
        selected_output=Path("output"),
        selected_output_formats=["md"],
        selected_languages=["en"],
        selected_temperature=0.7,
        selected_max_tokens=None,
        selected_throttle_seconds=0.0,
        force=False,
        no_ui=False,
        quiz=False,
        export_transcript=None,
        timestamps=False,
        chapter_directory_output=False,
        selected_cookie_file=None,
    )


def test_ensure_model_supported_short_circuits_when_unlisted_models_allowed() -> None:
    """Opting in must skip the catalog check entirely instead of rejecting."""
    config = MagicMock()
    config.allow_unlisted_models = True
    config.get_unsupported_model_message = MagicMock(
        return_value="Model is not currently supported."
    )
    context = _unsupported_model_context(config)

    assert context.ensure_model_supported() is True
    config.get_unsupported_model_message.assert_not_called()


def test_ensure_model_supported_still_rejects_when_opt_out_unchanged() -> None:
    """With the default opt-out, unlisted models keep failing preflight."""
    config = MagicMock()
    config.allow_unlisted_models = False
    config.get_unsupported_model_message = MagicMock(
        return_value="Model is not currently supported."
    )
    context = _unsupported_model_context(config)

    assert context.ensure_model_supported() is False
