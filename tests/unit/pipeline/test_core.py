"""Unit tests for pipeline core helpers and facades."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console
from sqlalchemy.exc import SQLAlchemyError

from notewise.cli._formatters import print_cost_summary
from notewise.domain.results import PipelineMetrics
from notewise.llm.provider import UsageTotals
from notewise.pipeline._artifacts import export_transcript, generate_and_write_quiz
from notewise.pipeline._execution import _usage_context
from notewise.pipeline._helpers import (
    coerce_usage_float,
    coerce_usage_int,
    coerce_usage_totals,
)
from notewise.pipeline.core import (
    CorePipeline,
    EventType,
    PipelineResult,
    PipelineSharedState,
    run_pipeline,
)
from notewise.youtube.transcript import TranscriptSegment, VideoTranscript


def _make_pipeline(temp_output_dir, mock_llm_provider):
    with patch("notewise.pipeline.core.get_provider", return_value=mock_llm_provider):
        pipeline = CorePipeline(model="mock-model", output_dir=temp_output_dir)
        pipeline.generator = MagicMock()
        pipeline.generator.count_tokens.return_value = 12
        return pipeline


def test_usage_coercion_helpers_handle_non_numeric_values():
    """Usage coercion should ignore non-numeric mock values safely."""
    assert coerce_usage_int("12") == 12
    assert coerce_usage_int("not-a-number") == 0
    assert coerce_usage_int(MagicMock()) == 0

    raw = MagicMock()
    raw.prompt_tokens = MagicMock()
    raw.completion_tokens = "9"
    raw.total_tokens = 4.8
    raw.cost_usd = "0.0025"
    totals = coerce_usage_totals(raw)

    assert totals.prompt_tokens == 0
    assert totals.completion_tokens == 9
    assert totals.total_tokens == 4
    assert totals.cost_usd == 0.0025


def test_usage_context_does_not_call_arbitrary_collect_usage_callable() -> None:
    """Only the real provider collector should be invoked as a context factory."""
    provider = MagicMock()
    provider.collect_usage = MagicMock(side_effect=AssertionError("called"))

    with _usage_context(provider) as usage:
        assert isinstance(usage, UsageTotals)

    provider.collect_usage.assert_not_called()


def test_pipeline_metrics_bool_truth_table():
    """Zero metrics should be falsy; any non-zero metric should be truthy."""
    assert bool(PipelineMetrics()) is False
    assert bool(PipelineMetrics(total_tokens=1)) is True
    assert bool(PipelineMetrics(cost_usd=0.01)) is True
    assert bool(PipelineMetrics(transcript_seconds=0.5)) is True


def test_print_cost_summary_skips_zero_metrics_output():
    """No cost table should render when the metrics object is all-zero."""
    console = Console(record=True, width=80)

    print_cost_summary(console, PipelineMetrics())

    assert console.export_text() == ""


def test_usage_coercion_helpers_cover_bool_float_and_passthrough():
    """Usage coercion should handle bools, negatives, bad strings, and passthrough."""
    totals = UsageTotals(
        prompt_tokens=1,
        completion_tokens=2,
        total_tokens=3,
        cost_usd=0.1,
    )

    assert coerce_usage_int(True) == 1
    assert coerce_usage_int(-2) == 0
    assert coerce_usage_float(True) == 1.0
    assert coerce_usage_float(-2) == 0.0
    assert coerce_usage_float("not-a-number") == 0.0
    assert coerce_usage_totals(totals) is totals


def test_pipeline_reuses_supplied_shared_state(temp_output_dir, mock_llm_provider):
    """Pipelines built for batch work should reuse the shared semaphore and locks."""
    shared_state = PipelineSharedState(
        semaphore=asyncio.Semaphore(3),
        chapter_semaphore=asyncio.Semaphore(2),
    )

    with patch("notewise.pipeline.core.get_provider", return_value=mock_llm_provider):
        pipeline = CorePipeline(
            model="mock-model",
            output_dir=temp_output_dir,
            shared_state=shared_state,
        )

    assert pipeline.semaphore is shared_state.semaphore
    assert pipeline._chapter_semaphore is shared_state.chapter_semaphore
    assert pipeline._output_lock is shared_state.output_lock
    assert pipeline._reserved_output_targets is shared_state.reserved_output_targets


def test_pipeline_passes_throttle_seconds_into_generator(
    temp_output_dir, mock_llm_provider
):
    """CorePipeline should pass the CLI throttle value into the generator."""
    with patch("notewise.pipeline.core.get_provider", return_value=mock_llm_provider):
        pipeline = CorePipeline(
            model="mock-model",
            output_dir=temp_output_dir,
            throttle_seconds=2.5,
        )

    assert pipeline.throttle_seconds == 2.5
    assert pipeline.generator.throttle_seconds == 2.5


def test_pipeline_passes_target_language_into_generator(
    temp_output_dir, mock_llm_provider
):
    """CorePipeline should pass the requested output language into the generator."""
    with patch("notewise.pipeline.core.get_provider", return_value=mock_llm_provider):
        pipeline = CorePipeline(
            model="mock-model",
            output_dir=temp_output_dir,
            target_language="French",
        )

    assert pipeline.target_language == "French"
    assert pipeline.generator.target_language == "French"


def test_pipeline_normalizes_blank_target_language(temp_output_dir, mock_llm_provider):
    """CorePipeline should normalize blank target languages to the default."""
    with patch("notewise.pipeline.core.get_provider", return_value=mock_llm_provider):
        pipeline = CorePipeline(
            model="mock-model",
            output_dir=temp_output_dir,
            target_language="   ",
        )

    assert pipeline.target_language == "English"
    assert pipeline.generator.target_language == "English"


@pytest.mark.asyncio
async def test_get_cached_video_returns_none_on_sqlalchemy_error(
    temp_output_dir,
    mock_llm_provider,
):
    """Cache read failures should degrade gracefully instead of aborting the run."""
    pipeline = _make_pipeline(temp_output_dir, mock_llm_provider)
    pipeline.db.get_video = MagicMock(side_effect=SQLAlchemyError("db down"))

    assert await pipeline._get_cached_video("vid-cache-fail") is None


@pytest.mark.asyncio
async def test_persist_video_cache_swallows_sqlalchemy_error(
    temp_output_dir,
    mock_llm_provider,
):
    """Cache write failures should be logged and ignored."""
    pipeline = _make_pipeline(temp_output_dir, mock_llm_provider)
    pipeline.db.upsert_video_cache = MagicMock(side_effect=SQLAlchemyError("db down"))
    pipeline.generator.count_tokens.return_value = 12

    await pipeline._persist_video_cache(
        video_id="vid-cache-fail",
        title="Video",
        duration=123,
        transcript_text="hello world",
        transcript_language="en",
    )

    pipeline.db.upsert_video_cache.assert_called_once()


@pytest.mark.asyncio
async def test_run_pipeline_convenience_wrapper_forwards_arguments(temp_output_dir):
    """run_pipeline should construct CorePipeline and delegate to run()."""
    expected = PipelineResult(
        success_count=1,
        failure_count=0,
        total_count=1,
        video_ids=["vid1"],
        errors={},
    )
    pipeline_instance = MagicMock()
    pipeline_instance.run = AsyncMock(return_value=expected)

    with patch(
        "notewise.pipeline.core.CorePipeline",
        return_value=pipeline_instance,
    ) as mock_pipeline_cls:
        result = await run_pipeline(
            ["vid1"],
            output_dir=temp_output_dir,
            model="demo-model",
            output_format="html",
            target_language="Spanish",
            throttle_seconds=3.0,
            on_event=None,
        )

    assert result is expected
    mock_pipeline_cls.assert_called_once_with(
        model="demo-model",
        output_dir=temp_output_dir,
        output_format="html",
        target_language="Spanish",
        throttle_seconds=3.0,
    )
    pipeline_instance.run.assert_awaited_once_with(["vid1"], on_event=None)


def test_emit_event_swallows_event_handler_errors(temp_output_dir, mock_llm_provider):
    """UI callback errors should not break the pipeline core."""
    pipeline = _make_pipeline(temp_output_dir, mock_llm_provider)
    on_event = MagicMock(side_effect=RuntimeError("ui boom"))
    emit = pipeline._emit_event(on_event)

    with patch("notewise.pipeline.core.logger.warning") as mock_warning:
        emit(EventType.PIPELINE_START, "vid", title="Video")

    on_event.assert_called_once()
    mock_warning.assert_called_once()


@pytest.mark.asyncio
async def test_generate_and_write_quiz_creates_output_directory(tmp_path):
    """Quiz writing should create the destination directory before writing."""
    generator = MagicMock()
    generator.generate_quiz = AsyncMock(return_value="# Quiz")
    output_dir = tmp_path / "nested" / "quiz"
    emit = MagicMock()

    await generate_and_write_quiz(
        generator,
        "transcript text",
        "Study Subject",
        output_dir=output_dir,
        emit=emit,
        video_id="vid1",
        title="Study Subject",
    )

    assert (output_dir / "Study Subject_quiz.md").exists()


def test_export_transcript_creates_output_directory(tmp_path):
    """Transcript export should create its parent directory before writing."""
    transcript = VideoTranscript(
        video_id="vid1",
        segments=[TranscriptSegment(text="hello", start=0.0, duration=1.0)],
        language="English",
        language_code="en",
        is_generated=False,
    )
    db = MagicMock()
    output_dir = tmp_path / "nested" / "transcripts"

    export_path = export_transcript(
        db,
        transcript,
        "Study Subject",
        output_dir,
        "vid1",
        "txt",
    )

    assert export_path.exists()
    assert export_path.parent == output_dir


def test_estimate_tokens_used_falls_back_when_counter_raises(
    temp_output_dir,
    mock_llm_provider,
):
    """Token estimation should fall back to a char-count heuristic on failure."""
    pipeline = _make_pipeline(temp_output_dir, mock_llm_provider)
    pipeline.generator.count_tokens.side_effect = RuntimeError("count failed")

    assert pipeline._estimate_tokens_used("") == 1
    assert pipeline._estimate_tokens_used("abcd" * 5) == 5
