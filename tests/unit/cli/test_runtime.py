"""Tests for the top-level CLI process coordinator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from yt_study.cli import _runtime


def test_read_batch_file_urls_supports_utf16(tmp_path: Path) -> None:
    """Batch files should load through the encoding fallback list."""
    batch_file = tmp_path / "urls.txt"
    batch_file.write_text(
        "# comment\nhttps://example.com/1\n\nhttps://example.com/2\n",
        encoding="utf-16",
    )

    assert _runtime._read_batch_file_urls(batch_file) == [
        "https://example.com/1",
        "https://example.com/2",
    ]


@pytest.mark.asyncio
async def test_cli_process_runner_reports_missing_batch_file() -> None:
    """Batch-looking missing paths should render a user-facing failure."""
    runner = MagicMock()
    runner.print_single_failure = MagicMock()

    result = await _runtime.CliProcessRunner.run(
        runner,
        "missing.txt",
        looks_like_batch_file_path=lambda value: value.endswith(".txt"),
    )

    assert result is True
    runner.print_single_failure.assert_called_once()


@pytest.mark.asyncio
async def test_cli_process_runner_reads_batch_file_and_dispatches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Existing batch files should be expanded and handed to the batch runner."""
    batch_file = tmp_path / "urls.txt"
    batch_file.write_text("https://example.com/a\n", encoding="utf-8")
    run_batch = AsyncMock(return_value=False)
    runner = MagicMock()

    monkeypatch.setattr(_runtime, "run_batch_file", run_batch)

    result = await _runtime.CliProcessRunner.run(
        runner,
        str(batch_file),
        looks_like_batch_file_path=lambda _value: False,
    )

    assert result is False
    run_batch.assert_awaited_once_with(runner, batch_file, ["https://example.com/a"])


@pytest.mark.asyncio
async def test_cli_process_runner_dispatches_single_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-file inputs should fall through to the single runner."""
    run_single = AsyncMock(return_value=True)
    runner = MagicMock()

    monkeypatch.setattr(_runtime, "run_single_url", run_single)

    result = await _runtime.CliProcessRunner.run(
        runner,
        "https://youtube.com/watch?v=abc",
        looks_like_batch_file_path=lambda _value: False,
    )

    assert result is False
    run_single.assert_awaited_once_with(runner, "https://youtube.com/watch?v=abc")
