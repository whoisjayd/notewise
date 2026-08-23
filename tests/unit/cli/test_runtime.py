"""Tests for the top-level CLI process coordinator."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

from notewise.cli import _batch_runner, _runtime
from notewise.domain.results import PipelineResult


if TYPE_CHECKING:
    import pytest


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


async def test_batch_summary_total_includes_early_failures(
    mocker: pytest.MockerFixture,
    tmp_path: Path,
) -> None:
    """Mixed batches must keep success + failure == total in the final summary."""
    prepared = SimpleNamespace(
        video_ids=["v-ok", "v-bad"],
        output_dir=tmp_path / "out",
        label="batch-entry",
        is_playlist=False,
    )

    async def _prepare_source(_context: object, source_url: str) -> SimpleNamespace:
        if source_url == "https://example.com/unresolvable":
            raise RuntimeError("resolution exploded")
        return prepared

    class _MixedPipeline:
        async def run(
            self,
            video_ids: list[str],
            *,
            on_event: object,
        ) -> PipelineResult:
            del on_event
            if video_ids[0] == "v-bad":
                return PipelineResult(
                    success_count=0,
                    failure_count=1,
                    total_count=1,
                    video_ids=video_ids,
                    errors={"v-bad": "boom"},
                )
            return PipelineResult(
                success_count=1,
                failure_count=0,
                total_count=1,
                video_ids=video_ids,
                errors={},
            )

    context = SimpleNamespace(
        config=SimpleNamespace(max_concurrent_videos=2),
        console=MagicMock(),
        selected_model="mock-model",
        selected_output=tmp_path / "out",
        api_key_checked=True,
        ensure_api_key_available=lambda: True,
        build_pipeline=lambda *_args, **_kwargs: _MixedPipeline(),
        no_ui=True,
    )
    mocker.patch.object(
        _batch_runner,
        "prepare_source",
        side_effect=_prepare_source,
    )
    summary = MagicMock(return_value=False)
    mocker.patch.object(_batch_runner, "print_batch_summary", summary)

    failed = await asyncio.wait_for(
        _batch_runner.run_batch_file(
            context,
            Path("urls.txt"),
            [
                "https://example.com/unresolvable",
                "https://youtube.com/watch?v=abc12345678",
            ],
        ),
        timeout=5,
    )

    assert failed is False
    summary.assert_called_once()
    _context, results, early_failures = summary.call_args.args
    total_jobs = summary.call_args.kwargs["total_jobs"]
    successes = sum(1 for result in results if result.success)
    failures = len(early_failures) + sum(1 for result in results if not result.success)
    assert successes == 1
    assert failures == 2
    assert successes + failures == total_jobs
