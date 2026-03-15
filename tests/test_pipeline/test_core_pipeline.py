"""Tests for CorePipeline (zero-UI core pipeline)."""

import asyncio
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from yt_study.core.llm.providers import UsageTotals
from yt_study.core.pipeline import (
    CorePipeline,
    EventType,
    PipelineEvent,
    PipelineResult,
    PipelineSharedState,
    _format_user_error,
    run_pipeline,
    sanitize_filename,
)
from yt_study.core.youtube.metadata import PublicAccessRequiredError
from yt_study.core.youtube.transcript import TranscriptError, YouTubeIPBlockError
from yt_study.db import (
    DatabaseManager,
    build_cache_db_path,
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


def test_sanitize_filename_strips_control_characters():
    """ASCII control characters must be removed."""
    assert sanitize_filename("foo\x00bar") == "foobar"
    assert sanitize_filename("foo\x1fbar") == "foobar"
    assert sanitize_filename("foo\x7fbar") == "foobar"


def test_sanitize_filename_trailing_dots_removed():
    """Trailing dots are illegal on Windows and must be stripped."""
    assert sanitize_filename("filename.") == "filename"
    assert sanitize_filename("filename...") == "filename"
    assert sanitize_filename("...") == "untitled"


def test_sanitize_filename_preserves_leading_dot():
    """Leading dots (e.g. .env, .gitignore) are valid and must not be stripped."""
    assert sanitize_filename(".env") == ".env"
    assert sanitize_filename(".gitignore") == ".gitignore"


def test_sanitize_filename_trailing_spaces_removed():
    """Trailing spaces are illegal on Windows and must be stripped."""
    assert sanitize_filename("filename   ") == "filename"


def test_sanitize_filename_truncation_restrips_trailing_spaces():
    """Truncation must not leave an illegal trailing space behind."""
    raw_name = ("a" * 99) + " " + ("b" * 10)
    result = sanitize_filename(raw_name)

    assert len(result) <= 100
    assert not result.endswith(" ")


def test_sanitize_filename_reserved_name_stays_within_100_chars():
    """Reserved names at the 100-char limit stay within 100 chars after prefixing."""
    # "NUL." + 96 x "a" = 100 chars total; matches _RESERVED because of "NUL."
    long_nul = "NUL." + "a" * 96
    result = sanitize_filename(long_nul)
    assert len(result) <= 100
    assert result.startswith("_")


def test_sanitize_filename_windows_reserved_names():
    """Windows reserved device names must be prefixed with underscore."""
    for reserved in ("CON", "PRN", "AUX", "NUL"):
        result = sanitize_filename(reserved)
        assert result == f"_{reserved}", f"Expected _{reserved}, got {result}"
        # Case-insensitive
        result_lower = sanitize_filename(reserved.lower())
        assert result_lower == f"_{reserved.lower()}"

    for i in range(1, 10):
        assert sanitize_filename(f"COM{i}") == f"_COM{i}"
        assert sanitize_filename(f"LPT{i}") == f"_LPT{i}"

    # COM0 and LPT0 are NOT Windows reserved names
    assert sanitize_filename("COM0") == "COM0"
    assert sanitize_filename("LPT0") == "LPT0"


def test_sanitize_filename_reserved_names_with_extension():
    """Reserved names followed by a dot (e.g. NUL.txt pattern) must also be renamed."""
    assert sanitize_filename("NUL.txt") == "_NUL.txt"
    assert sanitize_filename("com1.log") == "_com1.log"


def test_sanitize_filename_non_reserved_prefix():
    """Names that start with a reserved word but aren't reserved must pass through."""
    assert sanitize_filename("CONSOLE") == "CONSOLE"
    assert sanitize_filename("NULLIFY") == "NULLIFY"
    assert sanitize_filename("auxillary") == "auxillary"


def test_sanitize_filename_mixed_forbidden_and_reserved():
    """NUL<video>.txt after stripping forbidden chars is NULvideo.txt — not reserved."""
    assert sanitize_filename("NUL<video>.txt") == "NULvideo.txt"
    # But bare NUL.txt (after stripping) is still reserved
    assert sanitize_filename("NUL.txt") == "_NUL.txt"


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
async def test_run_applies_rate_limiter_to_metadata_and_transcript(pipeline):
    """Each metadata request and transcript fetch should acquire the shared limiter."""
    acquire_mock = AsyncMock()
    pipeline._acquire_youtube_request_slot = acquire_mock

    async def _fetch_with_request_hook(
        _video_id,
        _languages,
        on_request=None,
        **kwargs,  # Accept additional kwargs like cookies
    ):  # pragma: no cover - signature exercise
        assert on_request is not None
        await on_request()
        transcript = MagicMock()
        transcript.to_text.return_value = "text"
        return transcript

    with (
        patch("yt_study.core.pipeline.get_video_title", return_value="Video Title"),
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
        mock_fetch.side_effect = _fetch_with_request_hook
        result = await pipeline.run(["abc"])

    assert result.success_count == 1
    # 3 metadata calls + 1 transcript call
    assert acquire_mock.await_count == 4


@pytest.mark.asyncio
async def test_rate_limited_to_thread_supports_kwargs(pipeline):
    """Internal helper should pass through keyword arguments to thread targets."""
    acquire_mock = AsyncMock()
    pipeline._acquire_youtube_request_slot = acquire_mock

    def _kw_only(*, value: str) -> str:
        return value

    result = await pipeline._rate_limited_to_thread(_kw_only, value="ok")

    assert result == "ok"
    acquire_mock.assert_awaited_once()


def test_core_pipeline_instances_share_global_youtube_limiter(
    temp_output_dir, mock_llm_provider
):
    """Pipelines in one process should share a single limiter by configured rate."""
    with patch("yt_study.core.pipeline.get_provider", return_value=mock_llm_provider):
        pipeline_one = CorePipeline(model="mock-model", output_dir=temp_output_dir)
        pipeline_two = CorePipeline(model="mock-model", output_dir=temp_output_dir)

    assert (
        pipeline_one._get_youtube_request_limiter()
        is pipeline_two._get_youtube_request_limiter()
    )


@pytest.mark.asyncio
async def test_run_calls_plain_metadata_helpers(temp_output_dir, mock_llm_provider):
    """Pipeline should call metadata helpers directly and pass transcript hook."""
    with patch("yt_study.core.pipeline.get_provider", return_value=mock_llm_provider):
        pipeline = CorePipeline(model="mock-model", output_dir=temp_output_dir)
        pipeline.generator = MagicMock()
        pipeline.generator.generate_study_notes = AsyncMock(return_value="# Notes")
        pipeline.generator.generate_single_chapter_notes = AsyncMock(
            return_value="# Chapter Notes"
        )

    with (
        patch(
            "yt_study.core.pipeline.get_video_title", return_value="Video Title"
        ) as mock_title,
        patch(
            "yt_study.core.pipeline.get_video_duration", return_value=100
        ) as mock_duration,
        patch(
            "yt_study.core.pipeline.get_video_chapters", return_value=[]
        ) as mock_chapters,
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
        result = await pipeline.run(["vid-auth"])

    assert result.success_count == 1
    mock_title.assert_called_once_with("vid-auth")
    mock_duration.assert_called_once_with("vid-auth")
    mock_chapters.assert_called_once_with("vid-auth")

    fetch_kwargs = mock_fetch.await_args.kwargs
    assert fetch_kwargs["on_request"] is not None


@pytest.mark.asyncio
async def test_run_fails_early_for_private_video(pipeline):
    """Private videos should fail before transcript fetching starts."""
    with (
        patch(
            "yt_study.core.pipeline.get_video_title",
            side_effect=PublicAccessRequiredError(
                "Private YouTube videos are not supported. "
                "Make the video unlisted or public to process it."
            ),
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
        result = await pipeline.run(["private123"])

    assert result.success_count == 0
    assert result.failure_count == 1
    assert result.errors["private123"] == (
        "Private YouTube videos are not supported. "
        "Make the video unlisted or public to process it."
    )
    mock_fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_fails_cleanly_for_private_transcript_access(pipeline):
    """Transcript-level private video failures should keep the clean message."""
    with (
        patch("yt_study.core.pipeline.get_video_title", return_value="Private Video"),
        patch("yt_study.core.pipeline.get_video_duration", return_value=100),
        patch("yt_study.core.pipeline.get_video_chapters", return_value=[]),
        patch(
            "yt_study.core.pipeline.fetch_transcript",
            new_callable=AsyncMock,
            side_effect=PublicAccessRequiredError(
                "Private YouTube videos are not supported. "
                "Make the video unlisted or public to process it."
            ),
        ) as mock_fetch,
        patch(
            "yt_study.core.pipeline.config.get_api_key_name_for_model",
            return_value=None,
        ),
    ):
        result = await pipeline.run(["private123"])

    assert result.success_count == 0
    assert result.failure_count == 1
    assert result.errors["private123"] == (
        "Private YouTube videos are not supported. "
        "Make the video unlisted or public to process it."
    )
    mock_fetch.assert_awaited_once()


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


# ---------------------------------------------------------------------------
# CorePipeline.run – error handling and event emission
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_ip_block_error_emits_video_failed_event(pipeline):
    """YouTubeIPBlockError triggers VIDEO_FAILED event."""
    events: list[PipelineEvent] = []

    with (
        patch("yt_study.core.pipeline.get_video_title", return_value="Title"),
        patch("yt_study.core.pipeline.get_video_duration", return_value=100),
        patch("yt_study.core.pipeline.get_video_chapters", return_value=[]),
        patch(
            "yt_study.core.pipeline.fetch_transcript",
            new_callable=AsyncMock,
            side_effect=YouTubeIPBlockError("IP blocked"),
        ),
        patch(
            "yt_study.core.pipeline.config.get_api_key_name_for_model",
            return_value=None,
        ),
    ):
        result = await pipeline.run(["vid123"], on_event=events.append)

    # Check result
    assert result.success_count == 0
    assert result.failure_count == 1
    assert "vid123" in result.errors
    assert "temporarily blocking requests" in result.errors["vid123"]

    # Check events
    event_types = [e.event_type for e in events]
    assert EventType.VIDEO_FAILED in event_types

    failed_event = next(e for e in events if e.event_type == EventType.VIDEO_FAILED)
    assert failed_event.video_id == "vid123"
    assert "temporarily blocking requests" in failed_event.error


@pytest.mark.asyncio
async def test_run_generic_error_emits_video_failed_event(pipeline):
    """When processing raises generic RuntimeError, VIDEO_FAILED event is emitted."""
    events: list[PipelineEvent] = []

    with (
        patch("yt_study.core.pipeline.get_video_title", return_value="Title"),
        patch("yt_study.core.pipeline.get_video_duration", return_value=100),
        patch("yt_study.core.pipeline.get_video_chapters", return_value=[]),
        patch(
            "yt_study.core.pipeline.fetch_transcript",
            new_callable=AsyncMock,
            side_effect=RuntimeError("network timeout"),
        ),
        patch(
            "yt_study.core.pipeline.config.get_api_key_name_for_model",
            return_value=None,
        ),
    ):
        result = await pipeline.run(["vid456"], on_event=events.append)

    # Check result
    assert result.success_count == 0
    assert result.failure_count == 1
    assert "vid456" in result.errors
    assert "timed out" in result.errors["vid456"]

    # Check events
    event_types = [e.event_type for e in events]
    assert EventType.VIDEO_FAILED in event_types

    failed_event = next(e for e in events if e.event_type == EventType.VIDEO_FAILED)
    assert failed_event.video_id == "vid456"
    assert "timed out" in failed_event.error


# ---------------------------------------------------------------------------
# CorePipeline.run – chapter-based generation path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_long_video_with_chapters_generates_per_chapter_files(pipeline):
    """Long videos with chapters generate per-chapter files."""
    video_id = "video-with-chapters"
    video_title = "My Great Video: Intro & Deep Dive"
    chapter_meta = [
        {"title": "Intro", "start_seconds": 0},
        {"title": "Deep Dive", "start_seconds": 600},
    ]

    with (
        patch(
            "yt_study.core.pipeline.get_video_title",
            return_value=video_title,
        ),
        patch(
            "yt_study.core.pipeline.get_video_duration",
            return_value=7200,  # 2 hours
        ),
        patch(
            "yt_study.core.pipeline.get_video_chapters",
            return_value=chapter_meta,
        ),
        patch(
            "yt_study.core.pipeline.fetch_transcript",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "yt_study.core.pipeline.split_transcript_by_chapters",
        ) as mock_split,
        patch(
            "yt_study.core.pipeline.config.get_api_key_name_for_model",
            return_value=None,
        ),
    ):
        # Mock transcript
        mock_transcript = MagicMock()
        mock_fetch.return_value = mock_transcript

        # Mock chapter-split transcripts
        chapter_transcripts = {
            "Intro": "intro transcript text",
            "Deep Dive": "deep dive transcript text",
        }
        mock_split.return_value = chapter_transcripts

        result = await pipeline.run([video_id])

    # Verify success
    assert result.success_count == 1

    # Verify chapter-based generation was called
    assert pipeline.generator.generate_single_chapter_notes.await_count == 2

    # Verify per-chapter files were created
    expected_folder = pipeline.output_dir / sanitize_filename(video_title)
    assert expected_folder.is_dir()

    expected_files = {
        f"01_{sanitize_filename('Intro')}.md",
        f"02_{sanitize_filename('Deep Dive')}.md",
    }
    actual_files = {p.name for p in expected_folder.iterdir() if p.is_file()}

    assert expected_files.issubset(actual_files)


@pytest.mark.asyncio
async def test_run_chapter_generation_emits_chapter_events(pipeline):
    """Chapter-based generation emits CHAPTER_GENERATING events with correct counts."""
    events: list[PipelineEvent] = []

    chapter_meta = [
        {"title": "Chapter 1", "start_seconds": 0},
        {"title": "Chapter 2", "start_seconds": 300},
        {"title": "Chapter 3", "start_seconds": 600},
    ]

    with (
        patch("yt_study.core.pipeline.get_video_title", return_value="My Video"),
        patch("yt_study.core.pipeline.get_video_duration", return_value=7200),
        patch("yt_study.core.pipeline.get_video_chapters", return_value=chapter_meta),
        patch(
            "yt_study.core.pipeline.fetch_transcript", new_callable=AsyncMock
        ) as mock_fetch,
        patch("yt_study.core.pipeline.split_transcript_by_chapters") as mock_split,
        patch(
            "yt_study.core.pipeline.config.get_api_key_name_for_model",
            return_value=None,
        ),
    ):
        mock_transcript = MagicMock()
        mock_fetch.return_value = mock_transcript

        chapter_transcripts = {
            "Chapter 1": "text1",
            "Chapter 2": "text2",
            "Chapter 3": "text3",
        }
        mock_split.return_value = chapter_transcripts

        await pipeline.run(["vid789"], on_event=events.append)

    # Verify chapter events
    chapter_events = [e for e in events if e.event_type == EventType.CHAPTER_GENERATING]
    assert len(chapter_events) == 3

    # Verify chapter numbers and totals
    for i, event in enumerate(chapter_events, 1):
        assert event.chapter_number == i
        assert event.total_chapters == 3


@pytest.mark.asyncio
async def test_run_chapter_generation_emits_internal_chapter_progress(
    temp_output_dir, mock_llm_provider
):
    """Chunked chapter generation should emit chapter part and combine events."""
    events: list[PipelineEvent] = []
    p = _make_pipeline(temp_output_dir, mock_llm_provider, force=False)

    async def _generate_chapter(
        chapter_title,
        chapter_text,
        on_chunk=None,
        on_combine=None,  # noqa: ANN001
    ):
        assert chapter_title
        assert chapter_text
        if on_chunk:
            on_chunk(1, 2)
            on_chunk(2, 2)
        if on_combine:
            on_combine(2)
        return "# Chapter Notes"

    p.generator.generate_single_chapter_notes.side_effect = _generate_chapter

    with (
        patch(_COMMON_PATCHES["title"], return_value="Long Chapter Video"),
        patch(_COMMON_PATCHES["duration"], return_value=7200),
        patch(
            _COMMON_PATCHES["chapters"],
            return_value=[
                {"title": "Chapter 1", "start_seconds": 0},
                {"title": "Chapter 2", "start_seconds": 300},
            ],
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(
            "yt_study.core.pipeline.split_transcript_by_chapters",
            return_value={"Chapter 1": "text1", "Chapter 2": "text2"},
        ),
        patch(_COMMON_PATCHES["api_key"], return_value=None),
    ):
        mock_transcript = MagicMock()
        mock_transcript.to_text.return_value = "full transcript"
        mock_transcript.language_code = "en"
        mock_fetch.return_value = mock_transcript

        result = await p.run(["vid-chapter-events"], on_event=events.append)

    assert result.success_count == 1
    chapter_chunk_events = [
        e for e in events if e.event_type == EventType.CHAPTER_CHUNK_GENERATING
    ]
    assert len(chapter_chunk_events) == 4
    assert [e.chapter_number for e in chapter_chunk_events] == [1, 1, 2, 2]

    chapter_combine_events = [
        e for e in events if e.event_type == EventType.CHAPTER_COMBINING
    ]
    assert len(chapter_combine_events) == 2
    assert [e.chapter_number for e in chapter_combine_events] == [1, 2]
    assert all(e.total_chunks == 2 for e in chapter_combine_events)


@pytest.mark.asyncio
async def test_run_empty_chapter_split_falls_back_to_single_file(
    temp_output_dir, mock_llm_provider
):
    """Empty chapter splits should fall back to normal single-file generation."""
    p = _make_pipeline(temp_output_dir, mock_llm_provider, force=False)

    with (
        patch(_COMMON_PATCHES["title"], return_value="Fallback Video"),
        patch(_COMMON_PATCHES["duration"], return_value=7200),
        patch(
            _COMMON_PATCHES["chapters"],
            return_value=[{"title": "Intro", "start_seconds": 0}],
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch("yt_study.core.pipeline.split_transcript_by_chapters", return_value={}),
        patch(_COMMON_PATCHES["api_key"], return_value=None),
    ):
        mock_transcript = MagicMock()
        mock_transcript.to_text.return_value = "fallback transcript"
        mock_transcript.language_code = "en"
        mock_fetch.return_value = mock_transcript

        result = await p.run(["vid-chapter-fallback"])

    assert result.success_count == 1
    assert (temp_output_dir / "Fallback Video.md").exists()
    p.generator.generate_study_notes.assert_awaited_once()
    p.generator.generate_single_chapter_notes.assert_not_awaited()


@pytest.mark.asyncio
async def test_quiz_flag_writes_chapter_video_quiz_inside_video_folder(
    temp_output_dir, mock_llm_provider
):
    """Chapter-mode quizzes should live inside the per-video chapter folder."""
    p = _make_pipeline(temp_output_dir, mock_llm_provider, quiz=True)

    with (
        patch(_COMMON_PATCHES["title"], return_value="Long Video"),
        patch(_COMMON_PATCHES["duration"], return_value=7200),
        patch(
            _COMMON_PATCHES["chapters"],
            return_value=[
                {"title": "Intro", "start_seconds": 0},
                {"title": "Part 2", "start_seconds": 120},
            ],
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(
            "yt_study.core.pipeline.split_transcript_by_chapters",
            return_value={"Intro": "intro text", "Part 2": "body text"},
        ),
        patch(_COMMON_PATCHES["api_key"], return_value=None),
    ):
        mock_transcript = MagicMock()
        mock_transcript.to_text.return_value = "full transcript"
        mock_transcript.language_code = "en"
        mock_fetch.return_value = mock_transcript

        result = await p.run(["vid-chapter-quiz"])

    assert result.success_count == 1
    chapter_dir = temp_output_dir / "Long Video"
    assert (chapter_dir / "Long Video_quiz.md").exists()
    assert not (temp_output_dir / "Long Video_quiz.md").exists()


# ---------------------------------------------------------------------------
# CorePipeline – playlist checkpointing (#38)
# ---------------------------------------------------------------------------

_COMMON_PATCHES = dict(
    title="yt_study.core.pipeline.get_video_title",
    duration="yt_study.core.pipeline.get_video_duration",
    chapters="yt_study.core.pipeline.get_video_chapters",
    fetch="yt_study.core.pipeline.fetch_transcript",
    api_key="yt_study.core.pipeline.config.get_api_key_name_for_model",
)


def _make_pipeline(
    tmp_path, mock_llm_provider, force: bool = False, quiz: bool = False
):
    with patch("yt_study.core.pipeline.get_provider", return_value=mock_llm_provider):
        p = CorePipeline(
            model="mock-model", output_dir=tmp_path, force=force, quiz=quiz
        )
        p.generator = MagicMock()
        p.generator.generate_study_notes = AsyncMock(return_value="# Notes")
        p.generator.generate_single_chapter_notes = AsyncMock(
            return_value="# Chapter Notes"
        )
        p.generator.generate_quiz = AsyncMock(return_value="# Quiz")
        return p


def _seed_cached_video(
    video_id: str,
    title: str = "Cached Video",
    duration: int = 100,
) -> None:
    """Seed SQLite cache with one processed video entry."""
    db = DatabaseManager.get_instance(build_cache_db_path())
    db.upsert_video_cache(
        video_id=video_id,
        title=title,
        duration=duration,
        transcript_content="cached transcript",
        language="en",
        tokens_used=50,
        model="mock-model",
    )


def test_usage_coercion_helpers_handle_non_numeric_values(
    temp_output_dir, mock_llm_provider
):
    """Usage coercion should ignore non-numeric mock values safely."""
    p = _make_pipeline(temp_output_dir, mock_llm_provider, force=False)

    assert p._coerce_usage_int("12") == 12
    assert p._coerce_usage_int("not-a-number") == 0
    assert p._coerce_usage_int(MagicMock()) == 0

    raw = MagicMock()
    raw.prompt_tokens = MagicMock()
    raw.completion_tokens = "9"
    raw.total_tokens = 4.8
    raw.cost_usd = "0.0025"
    totals = p._coerce_usage_totals(raw)

    assert totals.prompt_tokens == 0
    assert totals.completion_tokens == 9
    assert totals.total_tokens == 4
    assert totals.cost_usd == 0.0025


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            PublicAccessRequiredError("Public access required"),
            "Public access required",
        ),
        (
            YouTubeIPBlockError("ip blocked"),
            "YouTube is temporarily blocking requests from this network. "
            "Try again later, lower the request rate, or switch networks.",
        ),
        (
            TranscriptError("No transcript found"),
            "We couldn't get a usable transcript for this video. "
            "Make sure captions are available, try another language, "
            "or use a different video.",
        ),
        (
            TranscriptError("Different transcript failure"),
            "We couldn't get a usable transcript for this video.",
        ),
        (
            RuntimeError("network timeout"),
            "The request timed out while processing this video. Please try again.",
        ),
        (
            RuntimeError("Connection refused by host"),
            "A network problem interrupted processing. Please try again.",
        ),
        (
            RuntimeError("Too many requests"),
            "The upstream service is rate-limiting requests right now. "
            "Please try again later.",
        ),
        (
            RuntimeError("Unauthorized request"),
            "The selected model or provider is not configured correctly. "
            "Check your API key and try again.",
        ),
        (
            RuntimeError("Access is denied"),
            "yt-study could not write the output files. "
            "Check the output folder permissions and try again.",
        ),
        (
            RuntimeError("mystery"),
            "We couldn't process this video. "
            "Check the current session log for technical details.",
        ),
    ],
)
def test_format_user_error_variants(error, expected):
    """User-facing error formatting should map internal failures predictably."""
    assert _format_user_error(error) == expected


def test_pipeline_reuses_supplied_shared_state(temp_output_dir, mock_llm_provider):
    """Pipelines built for batch work should reuse the shared semaphore and locks."""
    shared_state = PipelineSharedState(semaphore=asyncio.Semaphore(3))

    with patch("yt_study.core.pipeline.get_provider", return_value=mock_llm_provider):
        pipeline = CorePipeline(
            model="mock-model",
            output_dir=temp_output_dir,
            shared_state=shared_state,
        )

    assert pipeline.semaphore is shared_state.semaphore
    assert pipeline._output_lock is shared_state.output_lock
    assert pipeline._reserved_output_targets is shared_state.reserved_output_targets


@pytest.mark.asyncio
async def test_get_cached_video_returns_none_on_sqlalchemy_error(
    temp_output_dir, mock_llm_provider
):
    """Cache read failures should degrade gracefully instead of aborting the run."""
    p = _make_pipeline(temp_output_dir, mock_llm_provider, force=False)
    p.db.get_video = MagicMock(side_effect=SQLAlchemyError("db down"))

    assert await p._get_cached_video("vid-cache-fail") is None


@pytest.mark.asyncio
async def test_persist_video_cache_swallows_sqlalchemy_error(
    temp_output_dir, mock_llm_provider
):
    """Cache write failures should be logged and ignored."""
    p = _make_pipeline(temp_output_dir, mock_llm_provider, force=False)
    p.db.upsert_video_cache = MagicMock(side_effect=SQLAlchemyError("db down"))
    p.generator.count_tokens.return_value = 12

    await p._persist_video_cache(
        video_id="vid-cache-fail",
        title="Video",
        duration=123,
        transcript_text="hello world",
        transcript_language="en",
    )

    p.db.upsert_video_cache.assert_called_once()


def test_usage_coercion_helpers_cover_bool_float_and_passthrough(
    temp_output_dir, mock_llm_provider
):
    """Usage coercion should handle bools, negatives, bad strings, and passthrough."""
    p = _make_pipeline(temp_output_dir, mock_llm_provider, force=False)
    totals = UsageTotals(
        prompt_tokens=1,
        completion_tokens=2,
        total_tokens=3,
        cost_usd=0.1,
    )

    assert p._coerce_usage_int(True) == 1
    assert p._coerce_usage_int(-2) == 0
    assert p._coerce_usage_float(True) == 1.0
    assert p._coerce_usage_float(-2) == 0.0
    assert p._coerce_usage_float("not-a-number") == 0.0
    assert p._coerce_usage_totals(totals) is totals


def test_estimate_tokens_used_falls_back_when_counter_raises(
    temp_output_dir, mock_llm_provider
):
    """Token estimation should fall back to a char-count heuristic on failure."""
    p = _make_pipeline(temp_output_dir, mock_llm_provider, force=False)
    p.generator.count_tokens.side_effect = RuntimeError("count failed")

    assert p._estimate_tokens_used("") == 1
    assert p._estimate_tokens_used("abcd" * 5) == 5


def test_emit_event_swallows_event_handler_errors(temp_output_dir, mock_llm_provider):
    """UI callback errors should not break the pipeline core."""
    p = _make_pipeline(temp_output_dir, mock_llm_provider, force=False)
    on_event = MagicMock(side_effect=RuntimeError("ui boom"))
    emit = p._emit_event(on_event)

    with patch("yt_study.core.pipeline.logger.warning") as mock_warning:
        emit(EventType.PIPELINE_START, "vid", title="Video")

    on_event.assert_called_once()
    mock_warning.assert_called_once()


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
        "yt_study.core.pipeline.CorePipeline",
        return_value=pipeline_instance,
    ) as mock_pipeline_cls:
        result = await run_pipeline(
            ["vid1"],
            output_dir=temp_output_dir,
            model="demo-model",
            on_event=None,
        )

    assert result is expected
    mock_pipeline_cls.assert_called_once_with(
        model="demo-model",
        output_dir=temp_output_dir,
    )
    pipeline_instance.run.assert_awaited_once_with(["vid1"], on_event=None)


@pytest.mark.asyncio
async def test_checkpoint_skips_existing_single_file(
    temp_output_dir, mock_llm_provider
):
    """VIDEO_SKIPPED is emitted when video is already present in SQLite cache."""
    _seed_cached_video("vid1", title="Test Video")

    events: list[PipelineEvent] = []
    p = _make_pipeline(temp_output_dir, mock_llm_provider, force=False)

    with (
        patch(_COMMON_PATCHES["title"], return_value="Test Video") as mock_title,
        patch(_COMMON_PATCHES["duration"], return_value=100) as mock_duration,
        patch(_COMMON_PATCHES["chapters"], return_value=[]) as mock_chapters,
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=None),
    ):
        result = await p.run(["vid1"], on_event=events.append)

    assert result.success_count == 1
    assert EventType.VIDEO_SKIPPED in [e.event_type for e in events]
    # No metadata or transcript calls should run for skipped videos.
    mock_title.assert_not_called()
    mock_duration.assert_not_called()
    mock_chapters.assert_not_called()
    mock_fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkpoint_force_reprocesses_existing(
    temp_output_dir, mock_llm_provider
):
    """With force=True a cached video is ignored and reprocessed."""
    _seed_cached_video("vid1", title="Test Video")

    p = _make_pipeline(temp_output_dir, mock_llm_provider, force=True)

    with (
        patch(_COMMON_PATCHES["title"], return_value="Test Video"),
        patch(_COMMON_PATCHES["duration"], return_value=100),
        patch(_COMMON_PATCHES["chapters"], return_value=[]),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=None),
    ):
        mock_transcript = MagicMock()
        mock_transcript.to_text.return_value = "new content"
        mock_fetch.return_value = mock_transcript

        result = await p.run(["vid1"])

    assert result.success_count == 1
    # File must now contain the regenerated content
    output_file = temp_output_dir / "Test Video.md"
    assert output_file.read_text(encoding="utf-8") == "# Notes"


@pytest.mark.asyncio
async def test_checkpoint_processes_new_video(temp_output_dir, mock_llm_provider):
    """When no prior output exists the video is processed normally."""
    p = _make_pipeline(temp_output_dir, mock_llm_provider, force=False)

    with (
        patch(_COMMON_PATCHES["title"], return_value="Brand New Video"),
        patch(_COMMON_PATCHES["duration"], return_value=100),
        patch(_COMMON_PATCHES["chapters"], return_value=[]),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=None),
    ):
        mock_transcript = MagicMock()
        mock_transcript.to_text.return_value = "transcript"
        mock_fetch.return_value = mock_transcript

        result = await p.run(["newvid"])

    assert result.success_count == 1
    assert (temp_output_dir / "Brand New Video.md").exists()


@pytest.mark.asyncio
async def test_quiz_flag_creates_quiz_file(temp_output_dir, mock_llm_provider):
    """With quiz=True a *_quiz.md file is written alongside the study notes."""
    p = _make_pipeline(temp_output_dir, mock_llm_provider, quiz=True)

    with (
        patch(_COMMON_PATCHES["title"], return_value="Study Subject"),
        patch(_COMMON_PATCHES["duration"], return_value=100),
        patch(_COMMON_PATCHES["chapters"], return_value=[]),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=None),
    ):
        mock_transcript = MagicMock()
        mock_transcript.to_text.return_value = "full transcript"
        mock_fetch.return_value = mock_transcript

        result = await p.run(["vid1"])

    assert result.success_count == 1
    assert (temp_output_dir / "Study Subject.md").exists()
    assert (temp_output_dir / "Study Subject_quiz.md").exists()
    assert (temp_output_dir / "Study Subject_quiz.md").read_text(encoding="utf-8") == (
        "# Quiz"
    )
    p.generator.generate_quiz.assert_awaited_once()
    assert p.generator.generate_quiz.await_args.args == ("full transcript",)


@pytest.mark.asyncio
async def test_run_emits_internal_generation_and_quiz_events(
    temp_output_dir, mock_llm_provider
):
    """Chunked notes and quiz generation should emit internal progress events."""
    events: list[PipelineEvent] = []
    p = _make_pipeline(temp_output_dir, mock_llm_provider, quiz=True)

    async def _generate_notes(
        transcript,
        video_title="Video",
        on_chunk=None,
        on_combine=None,  # noqa: ANN001
    ):
        assert transcript == "full transcript"
        assert video_title == "Study Subject"
        if on_chunk:
            on_chunk(1, 2)
            on_chunk(2, 2)
        if on_combine:
            on_combine(2)
        return "# Notes"

    async def _generate_quiz(
        transcript,
        on_chunk=None,
        on_combine=None,  # noqa: ANN001
    ):
        assert transcript == "full transcript"
        if on_chunk:
            on_chunk(1, 2)
            on_chunk(2, 2)
        if on_combine:
            on_combine(2)
        return "# Quiz"

    p.generator.generate_study_notes.side_effect = _generate_notes
    p.generator.generate_quiz.side_effect = _generate_quiz

    with (
        patch(_COMMON_PATCHES["title"], return_value="Study Subject"),
        patch(_COMMON_PATCHES["duration"], return_value=100),
        patch(_COMMON_PATCHES["chapters"], return_value=[]),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=None),
    ):
        mock_transcript = MagicMock()
        mock_transcript.to_text.return_value = "full transcript"
        mock_transcript.language_code = "en"
        mock_fetch.return_value = mock_transcript

        result = await p.run(["vid-internal-events"], on_event=events.append)

    assert result.success_count == 1
    event_types = [event.event_type for event in events]
    expected_sequence = [
        EventType.METADATA_START,
        EventType.METADATA_FETCHED,
        EventType.TRANSCRIPT_FETCHING,
        EventType.TRANSCRIPT_FETCHED,
        EventType.GENERATION_START,
        EventType.CHUNK_GENERATING,
        EventType.CHUNK_GENERATING,
        EventType.GENERATION_COMBINING,
        EventType.QUIZ_GENERATING,
        EventType.QUIZ_CHUNK_GENERATING,
        EventType.QUIZ_CHUNK_GENERATING,
        EventType.QUIZ_COMBINING,
        EventType.QUIZ_COMPLETE,
        EventType.GENERATION_COMPLETE,
        EventType.VIDEO_SUCCESS,
        EventType.PIPELINE_COMPLETE,
    ]
    positions = [event_types.index(event_type) for event_type in expected_sequence]
    assert positions == sorted(positions)

    generation_combine = next(
        e for e in events if e.event_type == EventType.GENERATION_COMBINING
    )
    assert generation_combine.total_chunks == 2

    quiz_combine = next(e for e in events if e.event_type == EventType.QUIZ_COMBINING)
    assert quiz_combine.total_chunks == 2


@pytest.mark.asyncio
async def test_checkpoint_different_video_same_title_not_skipped(
    temp_output_dir, mock_llm_provider
):
    """Two videos sharing a title must not collide — cache is keyed by video ID."""
    _seed_cached_video("vid1", title="Shared Title")

    events: list[PipelineEvent] = []
    p = _make_pipeline(temp_output_dir, mock_llm_provider, force=False)

    with (
        patch(_COMMON_PATCHES["title"], return_value="Shared Title"),
        patch(_COMMON_PATCHES["duration"], return_value=100),
        patch(_COMMON_PATCHES["chapters"], return_value=[]),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=None),
    ):
        mock_transcript = MagicMock()
        mock_transcript.to_text.return_value = "transcript for vid2"
        mock_fetch.return_value = mock_transcript

        result = await p.run(["vid2"], on_event=events.append)

    assert result.success_count == 1
    # vid2 must NOT have been skipped — cache key is the video ID, not title.
    assert EventType.VIDEO_SKIPPED not in [e.event_type for e in events]
    mock_fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_duplicate_video_titles_get_unique_note_and_quiz_files(
    temp_output_dir, mock_llm_provider
):
    """Same-title videos should not overwrite each other's note or quiz files."""
    p = _make_pipeline(temp_output_dir, mock_llm_provider, quiz=True)
    p.semaphore = asyncio.Semaphore(1)

    with (
        patch(_COMMON_PATCHES["title"], side_effect=["Shared Title", "Shared Title"]),
        patch(_COMMON_PATCHES["duration"], side_effect=[100, 100]),
        patch(_COMMON_PATCHES["chapters"], side_effect=[[], []]),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=None),
    ):
        first_transcript = MagicMock()
        first_transcript.to_text.return_value = "first transcript"
        first_transcript.language_code = "en"

        second_transcript = MagicMock()
        second_transcript.to_text.return_value = "second transcript"
        second_transcript.language_code = "en"

        mock_fetch.side_effect = [first_transcript, second_transcript]

        result = await p.run(["vid1", "vid2"])

    assert result.success_count == 2
    assert (temp_output_dir / "Shared Title.md").exists()
    assert (temp_output_dir / "Shared Title_quiz.md").exists()
    assert (temp_output_dir / "Shared Title (vid2).md").exists()
    assert (temp_output_dir / "Shared Title (vid2)_quiz.md").exists()


@pytest.mark.asyncio
async def test_run_deduplicates_duplicate_video_ids(temp_output_dir, mock_llm_provider):
    """One pipeline run should only process each video ID once."""
    p = _make_pipeline(temp_output_dir, mock_llm_provider, quiz=False)
    p.semaphore = asyncio.Semaphore(1)

    with (
        patch(_COMMON_PATCHES["title"], return_value="Unique Once"),
        patch(_COMMON_PATCHES["duration"], return_value=100),
        patch(_COMMON_PATCHES["chapters"], return_value=[]),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=None),
    ):
        transcript = MagicMock()
        transcript.to_text.return_value = "transcript"
        transcript.language_code = "en"
        mock_fetch.return_value = transcript

        result = await p.run(["dup-id", "dup-id"])

    assert result.total_count == 1
    assert result.success_count == 1
    mock_fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_duplicate_chapter_video_titles_get_unique_folders(
    temp_output_dir, mock_llm_provider
):
    """Same-title long videos should get separate chapter folders and quiz files."""
    p = _make_pipeline(temp_output_dir, mock_llm_provider, quiz=True)
    p.semaphore = asyncio.Semaphore(1)

    with (
        patch(_COMMON_PATCHES["title"], side_effect=["Shared Long", "Shared Long"]),
        patch(_COMMON_PATCHES["duration"], side_effect=[7200, 7200]),
        patch(
            _COMMON_PATCHES["chapters"],
            side_effect=[
                [{"title": "Intro", "start_seconds": 0}],
                [{"title": "Intro", "start_seconds": 0}],
            ],
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(
            "yt_study.core.pipeline.split_transcript_by_chapters",
            side_effect=[
                {"Intro": "first chapter"},
                {"Intro": "second chapter"},
            ],
        ),
        patch(_COMMON_PATCHES["api_key"], return_value=None),
    ):
        first_transcript = MagicMock()
        first_transcript.to_text.return_value = "first long transcript"
        first_transcript.language_code = "en"

        second_transcript = MagicMock()
        second_transcript.to_text.return_value = "second long transcript"
        second_transcript.language_code = "en"

        mock_fetch.side_effect = [first_transcript, second_transcript]

        result = await p.run(["vid1", "vid2"])

    assert result.success_count == 2
    first_dir = temp_output_dir / "Shared Long"
    second_dir = temp_output_dir / "Shared Long (vid2)"
    assert (first_dir / "01_Intro.md").exists()
    assert (first_dir / "Shared Long_quiz.md").exists()
    assert (second_dir / "01_Intro.md").exists()
    assert (second_dir / "Shared Long (vid2)_quiz.md").exists()


async def test_pipeline_persists_video_metadata_in_sqlite_cache(
    temp_output_dir, mock_llm_provider
):
    """Successful runs should persist metadata/transcript/run-stats into SQLite."""
    p = _make_pipeline(temp_output_dir, mock_llm_provider, force=False)

    with (
        patch(_COMMON_PATCHES["title"], return_value="DB Cached Video"),
        patch(_COMMON_PATCHES["duration"], return_value=321),
        patch(_COMMON_PATCHES["chapters"], return_value=[]),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=None),
    ):
        mock_transcript = MagicMock()
        mock_transcript.to_text.return_value = "persisted transcript text"
        mock_transcript.language_code = "en"
        mock_fetch.return_value = mock_transcript

        result = await p.run(["vid-db"])

    assert result.success_count == 1
    db = DatabaseManager.get_instance(build_cache_db_path())
    cached_video = db.get_video("vid-db")
    cached_transcript = db.get_transcript("vid-db")
    stats = db.get_run_stats("vid-db")

    assert cached_video is not None
    assert cached_video.title == "DB Cached Video"
    assert cached_video.duration == 321
    assert cached_transcript is not None
    assert cached_transcript.content == "persisted transcript text"
    assert cached_transcript.language == "en"
    assert len(stats) >= 1
    assert stats[0].model == "mock-model"


@pytest.mark.asyncio
async def test_pipeline_collects_litellm_usage_and_step_timings(
    temp_output_dir, mock_llm_provider
):
    """Run result and DB stats should include prompt/completion + timing metrics."""
    p = _make_pipeline(temp_output_dir, mock_llm_provider, force=False)

    @contextmanager
    def _collect_usage():
        yield UsageTotals(
            prompt_tokens=40,
            completion_tokens=15,
            total_tokens=55,
            cost_usd=0.0055,
        )

    p.provider.collect_usage = _collect_usage

    with (
        patch(_COMMON_PATCHES["title"], return_value="Metrics Video"),
        patch(_COMMON_PATCHES["duration"], return_value=222),
        patch(_COMMON_PATCHES["chapters"], return_value=[]),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=None),
    ):
        mock_transcript = MagicMock()
        mock_transcript.to_text.return_value = "metrics transcript text"
        mock_transcript.language_code = "en"
        mock_fetch.return_value = mock_transcript
        result = await p.run(["vid-metrics"])

    assert result.success_count == 1
    assert result.metrics.prompt_tokens == 40
    assert result.metrics.completion_tokens == 15
    assert result.metrics.total_tokens == 55
    assert result.metrics.cost_usd == 0.0055
    assert result.metrics.transcript_seconds >= 0
    assert result.metrics.generation_seconds >= 0

    db = DatabaseManager.get_instance(build_cache_db_path())
    stats = db.get_run_stats("vid-metrics")
    latest = stats[-1]
    assert latest.prompt_tokens == 40
    assert latest.completion_tokens == 15
    assert latest.cost_usd == 0.0055
    assert latest.transcript_seconds >= 0
    assert latest.generation_seconds >= 0


@pytest.mark.asyncio
async def test_pipeline_reuses_sqlite_cache_across_runs(
    temp_output_dir, mock_llm_provider
):
    """Second run should skip when first run already persisted SQLite cache."""
    p_first = _make_pipeline(temp_output_dir, mock_llm_provider, force=False)
    first_events: list[PipelineEvent] = []

    with (
        patch(_COMMON_PATCHES["title"], return_value="Cached Video"),
        patch(_COMMON_PATCHES["duration"], return_value=123),
        patch(_COMMON_PATCHES["chapters"], return_value=[]),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch_first,
        patch(_COMMON_PATCHES["api_key"], return_value=None),
    ):
        first_transcript = MagicMock()
        first_transcript.to_text.return_value = "cached transcript text"
        first_transcript.language_code = "en"
        mock_fetch_first.return_value = first_transcript
        first_result = await p_first.run(
            ["cached-video-id"], on_event=first_events.append
        )

    assert first_result.success_count == 1
    assert EventType.VIDEO_SKIPPED not in [e.event_type for e in first_events]
    mock_fetch_first.assert_awaited_once()

    p_second = _make_pipeline(temp_output_dir, mock_llm_provider, force=False)
    second_events: list[PipelineEvent] = []

    with (
        patch(_COMMON_PATCHES["title"]) as mock_title_second,
        patch(_COMMON_PATCHES["duration"]) as mock_duration_second,
        patch(_COMMON_PATCHES["chapters"]) as mock_chapters_second,
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch_second,
        patch(_COMMON_PATCHES["api_key"], return_value=None),
    ):
        second_result = await p_second.run(
            ["cached-video-id"], on_event=second_events.append
        )

    assert second_result.success_count == 1
    assert EventType.VIDEO_SKIPPED in [e.event_type for e in second_events]
    mock_title_second.assert_not_called()
    mock_duration_second.assert_not_called()
    mock_chapters_second.assert_not_called()
    mock_fetch_second.assert_not_awaited()
