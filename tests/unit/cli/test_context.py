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
