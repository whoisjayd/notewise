"""Tests for CLI process context parameter handoff."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from rich.console import Console

from notewise.cli._context import CliProcessContext


def test_build_pipeline_passes_target_language() -> None:
    """CLI context should forward the requested target language to the pipeline."""
    core_pipeline_cls = MagicMock(return_value=object())
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
        use_combine_chunk=False,
        export_transcript=None,
        timestamps=False,
        selected_cookie_file=None,
    )

    context.build_pipeline(Path("custom-output"))

    core_pipeline_cls.assert_called_once_with(
        model="demo-model",
        output_dir=Path("custom-output"),
        output_formats=["md"],
        languages=["en"],
        target_language="Hindi",
        temperature=0.4,
        max_tokens=1000,
        throttle_seconds=0.0,
        force=False,
        quiz=False,
        use_combine_chunk=False,
        export_transcript=None,
        timestamps=False,
        youtube_cookie_file=None,
        shared_state=None,
    )
