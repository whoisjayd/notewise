"""Top-level CLI process coordinator."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from notewise.cli._batch_runner import run_batch_file
from notewise.cli._context import CliProcessContext
from notewise.cli._single_runner import run_single_url


_BATCH_FILE_ENCODINGS = ("utf-8", "utf-8-sig", "utf-16")


def _read_batch_file_urls(input_path: Path) -> list[str]:
    """Read batch-file URLs with Windows-friendly encoding fallbacks."""
    last_decode_error: UnicodeDecodeError | None = None

    for encoding in _BATCH_FILE_ENCODINGS:
        try:
            content = input_path.read_text(encoding=encoding)
        except UnicodeDecodeError as error:
            last_decode_error = error
            continue

        return [
            line.strip()
            for line in content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    if last_decode_error is not None:
        raise last_decode_error
    raise UnicodeDecodeError("utf-8", b"", 0, 0, "No supported encoding matched")


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
                urls = _read_batch_file_urls(input_path)
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
