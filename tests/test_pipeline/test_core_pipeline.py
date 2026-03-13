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
from yt_study.core.youtube.transcript import YouTubeIPBlockError


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
        _video_id, _languages, on_request=None
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
    assert "IP blocked" in result.errors["vid123"]

    # Check events
    event_types = [e.event_type for e in events]
    assert EventType.VIDEO_FAILED in event_types

    failed_event = next(e for e in events if e.event_type == EventType.VIDEO_FAILED)
    assert failed_event.video_id == "vid123"
    assert "IP blocked" in failed_event.error or "VPN" in failed_event.error


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
    assert "RuntimeError" in result.errors["vid456"]

    # Check events
    event_types = [e.event_type for e in events]
    assert EventType.VIDEO_FAILED in event_types

    failed_event = next(e for e in events if e.event_type == EventType.VIDEO_FAILED)
    assert failed_event.video_id == "vid456"
    assert "RuntimeError" in failed_event.error


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


@pytest.mark.asyncio
async def test_checkpoint_skips_existing_single_file(
    temp_output_dir, mock_llm_provider
):
    """VIDEO_SKIPPED is emitted when the video ID is in the manifest and force=False."""
    import json

    # Write a manifest entry for "vid1" to simulate a previously processed video.
    (temp_output_dir / ".yt_study_processed.json").write_text(
        json.dumps({"vid1": True}), encoding="utf-8"
    )

    events: list[PipelineEvent] = []
    p = _make_pipeline(temp_output_dir, mock_llm_provider, force=False)

    with (
        patch(_COMMON_PATCHES["title"], return_value="Test Video"),
        patch(_COMMON_PATCHES["duration"], return_value=100),
        patch(_COMMON_PATCHES["chapters"], return_value=[]),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=None),
    ):
        result = await p.run(["vid1"], on_event=events.append)

    assert result.success_count == 1
    assert EventType.VIDEO_SKIPPED in [e.event_type for e in events]
    # Transcript should NOT have been fetched
    mock_fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkpoint_force_reprocesses_existing(
    temp_output_dir, mock_llm_provider
):
    """With force=True an existing manifest entry is ignored; video is reprocessed."""
    import json

    # Simulate a previously processed video in the manifest.
    (temp_output_dir / ".yt_study_processed.json").write_text(
        json.dumps({"vid1": True}), encoding="utf-8"
    )

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
    p.generator.generate_quiz.assert_awaited_once_with("full transcript")


@pytest.mark.asyncio
async def test_checkpoint_different_video_same_title_not_skipped(
    temp_output_dir, mock_llm_provider
):
    """Two videos sharing a title must not collide — checkpoint is keyed by video ID."""
    import json

    # vid1 was already processed; vid2 shares the same title but is a different video.
    (temp_output_dir / ".yt_study_processed.json").write_text(
        json.dumps({"vid1": True}), encoding="utf-8"
    )

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
    # vid2 must NOT have been skipped — the manifest key is the video ID, not the title.
    assert EventType.VIDEO_SKIPPED not in [e.event_type for e in events]
    mock_fetch.assert_awaited_once()
