"""Tests for CorePipeline (zero-UI core pipeline)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yt_study.core.pipeline import (
    CorePipeline,
    EventType,
    PipelineEvent,
    PipelineResult,
    sanitize_filename,
)


# ---------------------------------------------------------------------------
# sanitize_filename – extra cases not covered by the orchestrator tests
# ---------------------------------------------------------------------------


def test_sanitize_filename_dot_traversal():
    """Dot-only names must not slip through as directory traversal."""
    assert sanitize_filename(".") == "untitled"
    assert sanitize_filename("..") == "untitled"


def test_sanitize_filename_empty_after_strip():
    assert sanitize_filename("") == "untitled"
    assert sanitize_filename("   ") == "untitled"


def test_sanitize_filename_removes_forbidden_chars():
    assert sanitize_filename('foo<>:"/\\|?*bar') == "foobar"


def test_sanitize_filename_truncates_to_100():
    assert len(sanitize_filename("a" * 200)) == 100


# ---------------------------------------------------------------------------
# CorePipeline fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def pipeline(temp_output_dir, mock_llm_provider):
    with patch(
        "yt_study.core.pipeline.get_provider",
        return_value=mock_llm_provider,
    ):
        p = CorePipeline(model="mock-model", output_dir=temp_output_dir)
        p.generator = MagicMock()
        p.generator.generate_study_notes = AsyncMock(return_value="# Notes")
        p.generator.generate_single_chapter_notes = AsyncMock(
            return_value="# Chapter Notes"
        )
        return p


# ---------------------------------------------------------------------------
# CorePipeline.run – basic structural tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_empty_video_ids(pipeline):
    """run() with empty list returns zero-count result immediately."""
    result = await pipeline.run([])

    assert isinstance(result, PipelineResult)
    assert result.total_count == 0
    assert result.success_count == 0
    assert result.failure_count == 0


@pytest.mark.asyncio
async def test_run_missing_api_key(pipeline, monkeypatch):
    """run() returns all-failure result when API key is absent."""
    with patch(
        "yt_study.core.config.config.get_api_key_name_for_model",
        return_value="MISSING_KEY_XYZ",
    ):
        monkeypatch.delenv("MISSING_KEY_XYZ", raising=False)
        result = await pipeline.run(["vid1", "vid2"])

    assert result.success_count == 0
    assert result.failure_count == 2
    assert "vid1" in result.errors
    assert "vid2" in result.errors


# ---------------------------------------------------------------------------
# CorePipeline.run – single short video (no chapters)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_single_video_creates_file_named_after_title(pipeline):
    """Output file must use the video title, not the raw video_id."""
    with (
        patch(
            "yt_study.core.pipeline.get_video_title",
            return_value="My Awesome Video",
        ),
        patch("yt_study.core.pipeline.get_video_duration", return_value=300),
        patch("yt_study.core.pipeline.get_video_chapters", return_value=[]),
        patch(
            "yt_study.core.pipeline.fetch_transcript",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "yt_study.core.pipeline.config.get_api_key_name_for_model",
            return_value=None,
        ),
    ):
        mock_transcript = MagicMock()
        mock_transcript.to_text.return_value = "transcript text"
        mock_fetch.return_value = mock_transcript

        result = await pipeline.run(["vid123"])

    assert result.success_count == 1
    expected_file = pipeline.output_dir / "My Awesome Video.md"
    assert expected_file.exists(), f"Expected {expected_file} but it does not exist"


@pytest.mark.asyncio
async def test_run_single_video_events_emitted(pipeline):
    """Pipeline emits PIPELINE_START with empty video_id sentinel and correct events."""
    events: list[PipelineEvent] = []

    with (
        patch("yt_study.core.pipeline.get_video_title", return_value="Video Title"),
        patch("yt_study.core.pipeline.get_video_duration", return_value=100),
        patch("yt_study.core.pipeline.get_video_chapters", return_value=None),
        patch(
            "yt_study.core.pipeline.fetch_transcript",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "yt_study.core.pipeline.config.get_api_key_name_for_model",
            return_value=None,
        ),
    ):
        mock_transcript = MagicMock()
        mock_transcript.to_text.return_value = "text"
        mock_fetch.return_value = mock_transcript

        await pipeline.run(["abc"], on_event=events.append)

    event_types = [e.event_type for e in events]
    assert EventType.PIPELINE_START in event_types
    assert EventType.VIDEO_SUCCESS in event_types
    assert EventType.PIPELINE_COMPLETE in event_types

    pipeline_start = next(e for e in events if e.event_type == EventType.PIPELINE_START)
    pipeline_end = next(
        e for e in events if e.event_type == EventType.PIPELINE_COMPLETE
    )
    # Pipeline-level events must NOT use a video_id from the list
    assert pipeline_start.video_id == ""
    assert pipeline_end.video_id == ""


@pytest.mark.asyncio
async def test_metadata_fetched_uses_total_chapters_not_chapter_number(pipeline):
    """METADATA_FETCHED event must set total_chapters, not chapter_number."""
    events: list[PipelineEvent] = []
    dummy_chapters = [{"title": "Intro", "start_seconds": 0}] * 3

    with (
        patch("yt_study.core.pipeline.get_video_title", return_value="Title"),
        patch("yt_study.core.pipeline.get_video_duration", return_value=100),
        patch("yt_study.core.pipeline.get_video_chapters", return_value=dummy_chapters),
        patch(
            "yt_study.core.pipeline.fetch_transcript",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "yt_study.core.pipeline.config.get_api_key_name_for_model",
            return_value=None,
        ),
    ):
        mock_transcript = MagicMock()
        mock_transcript.to_text.return_value = "text"
        mock_fetch.return_value = mock_transcript

        await pipeline.run(["vid1"], on_event=events.append)

    meta_event = next(
        (e for e in events if e.event_type == EventType.METADATA_FETCHED), None
    )
    assert meta_event is not None
    assert meta_event.total_chapters == 3
    # chapter_number is an ordinal field; it must NOT hold the total count
    assert meta_event.chapter_number is None


# ---------------------------------------------------------------------------
# CorePipeline.run – chapters=None guard (no TypeError)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_chapters_none_does_not_raise(pipeline):
    """When get_video_chapters returns None the pipeline must not raise TypeError."""
    with (
        patch("yt_study.core.pipeline.get_video_title", return_value="Title"),
        patch("yt_study.core.pipeline.get_video_duration", return_value=7200),
        patch("yt_study.core.pipeline.get_video_chapters", return_value=None),
        patch(
            "yt_study.core.pipeline.fetch_transcript",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "yt_study.core.pipeline.config.get_api_key_name_for_model",
            return_value=None,
        ),
    ):
        mock_transcript = MagicMock()
        mock_transcript.to_text.return_value = "text"
        mock_fetch.return_value = mock_transcript

        result = await pipeline.run(["vid1"])

    # A long video without chapters falls through to single-file generation
    assert result.success_count == 1


# ---------------------------------------------------------------------------
# CorePipeline.run – title fetch failure falls back to video_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_title_failure_falls_back_to_video_id(pipeline):
    """When title fetch raises, the output file is named after the video_id."""
    with (
        patch(
            "yt_study.core.pipeline.get_video_title",
            side_effect=RuntimeError("network error"),
        ),
        patch("yt_study.core.pipeline.get_video_duration", return_value=100),
        patch("yt_study.core.pipeline.get_video_chapters", return_value=[]),
        patch(
            "yt_study.core.pipeline.fetch_transcript",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "yt_study.core.pipeline.config.get_api_key_name_for_model",
            return_value=None,
        ),
    ):
        mock_transcript = MagicMock()
        mock_transcript.to_text.return_value = "text"
        mock_fetch.return_value = mock_transcript

        result = await pipeline.run(["myVideoId"])

    assert result.success_count == 1
    expected_file = pipeline.output_dir / "myVideoId.md"
    assert expected_file.exists(), "Expected fallback filename using video_id"
