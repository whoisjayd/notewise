"""Shared CLI process context and core helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console

from notewise._constants import CONFIG_FILENAME, DEFAULT_TARGET_LANGUAGE
from notewise.cli._formatters import print_failure_panel, print_single_failure
from notewise.config import get_state_dir
from notewise.pipeline.core import PipelineSharedState


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
    selected_output_formats: list[str]
    selected_languages: list[str]
    selected_temperature: float
    selected_max_tokens: int | None
    selected_throttle_seconds: float
    force: bool
    no_ui: bool
    quiz: bool
    export_transcript: str | None
    timestamps: bool
    chapter_directory_output: bool
    selected_cookie_file: str | None
    selected_target_language: str = DEFAULT_TARGET_LANGUAGE
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

    def ensure_model_supported(self) -> bool:
        """Reject known unsupported models before any YouTube network work."""
        get_unsupported_model_message = getattr(
            self.config,
            "get_unsupported_model_message",
            None,
        )
        if not callable(get_unsupported_model_message):
            return True

        message = get_unsupported_model_message(self.selected_model)
        if not isinstance(message, str) or not message.strip():
            return True

        self.print_failure_panel(
            "Unsupported Model",
            [
                ("Model", self.selected_model),
                ("Issue", message.strip()),
            ],
        )
        return False

    def ensure_api_key_available(self) -> bool:
        """Validate the selected model's API key after input preflight succeeds."""
        if self.api_key_checked is not None:
            return self.api_key_checked

        get_missing_config_names = getattr(
            self.config,
            "get_missing_config_names_for_model",
            None,
        )
        if callable(get_missing_config_names):
            missing_config_result = get_missing_config_names(self.selected_model)
            if isinstance(missing_config_result, (list, tuple, set)):
                missing_config = tuple(str(name) for name in missing_config_result)
            else:
                missing_config = None

        else:
            missing_config = None

        if missing_config is None:
            key_name = self.config.get_api_key_name_for_model(self.selected_model)
            configured_key = os.environ.get(key_name) if key_name else None
            missing_config = (key_name,) if key_name and not configured_key else ()

        if missing_config:
            expected_config = ", ".join(missing_config)
            config_file_exists = (get_state_dir() / CONFIG_FILENAME).exists()
            if not config_file_exists:
                self.print_failure_panel(
                    "Setup Required",
                    [
                        ("Issue", "notewise: no configuration found."),
                        ("Expected", expected_config),
                        ("Next Step", "Run `notewise setup` to get started."),
                    ],
                )
                self.api_key_checked = False
                return False
            self.print_failure_panel(
                "Setup Required",
                [
                    ("Model", f"Missing provider config for {self.selected_model}"),
                    ("Expected", expected_config),
                    ("Next Step", "Run `notewise setup` to configure it."),
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
            output_formats=self.selected_output_formats,
            languages=self.selected_languages,
            target_language=self.selected_target_language,
            temperature=self.selected_temperature,
            max_tokens=self.selected_max_tokens,
            throttle_seconds=self.selected_throttle_seconds,
            force=self.force,
            quiz=self.quiz,
            export_transcript=self.export_transcript,
            timestamps=self.timestamps,
            chapter_directory_output=self.chapter_directory_output,
            youtube_cookie_file=self.selected_cookie_file,
            shared_state=shared_state,
        )
