"""Shared CLI process context and core helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console

from yt_study.cli._formatters import print_failure_panel, print_single_failure
from yt_study.pipeline.core import PipelineSharedState


@dataclass
class CliProcessContext:
    """Shared state for one CLI `process` invocation."""

    console: Console
    config: Any
    core_pipeline_cls: Any
    parse_youtube_url: Any
    extract_playlist_videos: Any
    get_playlist_info: Any
    dashboard_cls: Any
    live_cls: Any
    selected_model: str
    selected_output: Path
    selected_languages: list[str]
    selected_temperature: float
    selected_max_tokens: int | None
    force: bool
    no_ui: bool
    quiz: bool
    export_transcript: str | None
    selected_cookie_file: str | None
    api_key_checked: bool | None = None

    def print_failure_panel(
        self,
        title: str,
        rows: list[tuple[str, str]],
        *,
        intro: str | None = None,
    ) -> None:
        print_failure_panel(self.console, title, rows, intro=intro)

    def print_single_failure(
        self,
        title: str,
        message: str,
        *,
        item_label: str = "Issue",
        intro: str | None = None,
    ) -> None:
        print_single_failure(
            self.console,
            title,
            message,
            item_label=item_label,
            intro=intro,
        )

    def ensure_api_key_available(self) -> bool:
        """Validate the selected model's API key after input preflight succeeds."""
        if self.api_key_checked is not None:
            return self.api_key_checked

        key_name = self.config.get_api_key_name_for_model(self.selected_model)
        if key_name and not os.environ.get(key_name):
            self.print_failure_panel(
                "Setup Required",
                [
                    ("Model", f"Missing API key for {self.selected_model}"),
                    ("Expected", key_name),
                    ("Next Step", "Run `yt-study setup` to configure it."),
                ],
            )
            self.api_key_checked = False
            return False

        self.api_key_checked = True
        return True

    def build_pipeline(
        self,
        output_dir: Path,
        *,
        shared_state: PipelineSharedState | None = None,
    ) -> Any:
        """Create a configured pipeline instance."""
        return self.core_pipeline_cls(
            model=self.selected_model,
            output_dir=output_dir,
            languages=self.selected_languages,
            temperature=self.selected_temperature,
            max_tokens=self.selected_max_tokens,
            force=self.force,
            quiz=self.quiz,
            export_transcript=self.export_transcript,
            youtube_cookie_file=self.selected_cookie_file,
            shared_state=shared_state,
        )
