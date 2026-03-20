"""Top-level CLI process coordinator."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from yt_study.cli._batch_runner import run_batch_file
from yt_study.cli._context import CliProcessContext
from yt_study.cli._single_runner import run_single_url


class CliProcessRunner(CliProcessContext):
    """Dispatch one CLI `process` input to single or batch execution."""

    async def run(
        self,
        source_input: str,
        *,
        looks_like_batch_file_path: Callable[[str], Any],
    ) -> bool:
        input_path = Path(source_input).expanduser()

        if input_path.exists():
            if not input_path.is_file():
                self.print_single_failure(
                    "Input Error",
                    f"Batch file path is not a file: {input_path}",
                    item_label="Batch File",
                )
                return True

            try:
                content = input_path.read_text(encoding="utf-8")
                urls = [
                    line.strip()
                    for line in content.splitlines()
                    if line.strip() and not line.strip().startswith("#")
                ]
            except Exception as error:
                self.print_single_failure(
                    "Input Error",
                    f"Could not read the batch file: {error}",
                    item_label="Batch File",
                )
                return True

            if not urls:
                self.print_single_failure(
                    "Input Error",
                    "The batch file is empty.",
                    item_label="Batch File",
                )
                return True

            return await run_batch_file(self, input_path, urls)

        if looks_like_batch_file_path(source_input):
            self.print_single_failure(
                "Input Error",
                f"Batch file does not exist: {input_path}",
                item_label="Batch File",
            )
            return True

        return not await run_single_url(self, source_input)
