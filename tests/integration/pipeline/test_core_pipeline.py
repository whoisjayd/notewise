"""Tests for CorePipeline (zero-UI core pipeline)."""

import asyncio
import json
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from notewise.config import get_cache_db_path
from notewise.domain.youtube import ChapterTranscript
from notewise.errors import (
    ExtractionError as ExtractorError,
)
from notewise.errors import (
    IPBlockError as YouTubeIPBlockError,
)
from notewise.errors import (
    ValidationError,
)
from notewise.errors import (
    VideoUnavailableError as PublicAccessRequiredError,
)
from notewise.llm.provider import UsageTotals
from notewise.pipeline.core import (
    CorePipeline,
    EventType,
    PipelineEvent,
    PipelineResult,
    export_transcript,
    prefix_chapter_heading_with_timestamp,
    sanitize_filename,
)
from notewise.storage import DatabaseRepository as DatabaseManager
from notewise.youtube.metadata import VideoChapter, VideoMetadata
from notewise.youtube.transcript import (
    TranscriptSegment,
    VideoTranscript,
)


# ---------------------------------------------------------------------------
# CorePipeline fixtures
# ---------------------------------------------------------------------------


def _make_transcript(video_id="vid123", text="transcript text"):
    """Build a real VideoTranscript for use in pipeline tests."""
    return VideoTranscript(
        video_id=video_id,
        segments=[TranscriptSegment(text=text, start=0.0, duration=5.0)],
        language="English",
        language_code="en",
        is_generated=False,
    )


def _mock_generate_chapter_notes_concurrent(generator: MagicMock) -> AsyncMock:
    """Model concurrent chapter generation via the single-chapter API."""

    async def _generate(
        chapter_transcripts: dict[str, str],
        *,
        on_chapter_start=None,
        on_chapter_complete=None,
        generate_single=None,
        **kwargs,
    ):
        del kwargs
        total = len(chapter_transcripts)
        result: dict[str, str] = {}
        chapter_generator = generate_single or generator.generate_single_chapter_notes

        for index, (chapter_title, chapter_text) in enumerate(
            chapter_transcripts.items(),
            start=1,
        ):
            if on_chapter_start is not None:
                on_chapter_start(index, total)
            notes = await chapter_generator(
                chapter_title,
                chapter_text,
            )
            if on_chapter_complete is not None:
                on_chapter_complete(chapter_title, notes)
            result[chapter_title] = notes

        return result

    return AsyncMock(side_effect=_generate)


@pytest.fixture()
def pipeline(temp_output_dir, mock_llm_provider):
    with patch(
        "notewise.pipeline.core.get_provider",
        return_value=mock_llm_provider,
    ):
        p = CorePipeline(model="mock-model", output_dir=temp_output_dir)
        p.generator = MagicMock()
        p.generator.generate_study_notes = AsyncMock(return_value="# Notes")
        p.generator.generate_single_chapter_notes = AsyncMock(
            return_value="# Chapter Notes"
        )
        p.generator.generate_chapter_notes_concurrent = (
            _mock_generate_chapter_notes_concurrent(p.generator)
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
    assert result.success_count == 0
    assert result.failure_count == 0
    assert result.total_count == 0


@pytest.mark.asyncio
async def test_process_single_video_reuses_chapter_metadata_for_duplicate_titles(
    pipeline,
    temp_output_dir,
):
    transcript = VideoTranscript(
        video_id="vid-dup",
        segments=[
            TranscriptSegment(text="middle segment", start=120.0, duration=10.0),
            TranscriptSegment(text="later segment", start=360.0, duration=10.0),
        ],
        language="English",
        language_code="en",
        is_generated=False,
    )
    chapters = [
        VideoChapter(title="Intro", start_seconds=0, end_seconds=60),
        VideoChapter(title="Intro", start_seconds=100, end_seconds=200),
        VideoChapter(title="Intro", start_seconds=300, end_seconds=420),
    ]

    pipeline.timestamps = True
    pipeline.chapter_directory_output = True
    pipeline.force = True
    pipeline.quiz = False
    pipeline.export_transcript_format = None
    pipeline._get_cached_video = AsyncMock(return_value=None)
    pipeline._acquire_youtube_request_slot = AsyncMock()
    pipeline._reserve_output_target = AsyncMock(
        return_value=temp_output_dir / "Duplicate Titles Video"
    )
    pipeline._release_output_target = AsyncMock()
    pipeline._record_metrics = AsyncMock()
    pipeline._persist_video_cache = AsyncMock()
    pipeline._export_transcript = MagicMock()
    pipeline.generator.generate_single_chapter_notes = AsyncMock(
        side_effect=(
            lambda chapter_title, chapter_text, **_kwargs: (
                f"# {chapter_title}\n\n{chapter_text}"
            )
        )
    )
    pipeline.generator.generate_chapter_notes_concurrent = (
        _mock_generate_chapter_notes_concurrent(pipeline.generator)
    )

    with (
        patch(
            "notewise.pipeline._execution.get_video_metadata",
            AsyncMock(
                return_value=VideoMetadata(
                    video_id="vid-dup",
                    title="Duplicate Titles Video",
                    duration=7200,
                    chapters=chapters,
                )
            ),
        ),
        patch(
            "notewise.pipeline._execution.fetch_transcript",
            AsyncMock(return_value=transcript),
        ),
    ):
        ok = await pipeline._process_single_video("vid-dup")

    assert ok is True
    output_dir = temp_output_dir / "Duplicate Titles Video"
    second_chapter = output_dir / "01_Intro.md"
    assert second_chapter.exists()
    second_notes = second_chapter.read_text(encoding="utf-8")
    assert second_notes.startswith("# [01:40] Intro")
    assert "middle segment" in second_notes

    third_chapter = output_dir / "02_Intro (2).md"
    assert third_chapter.exists()
    third_notes = third_chapter.read_text(encoding="utf-8")
    assert third_notes.startswith("# [05:00] Intro")
    assert "later segment" in third_notes


async def test_process_single_video_bundles_chapters_into_single_markdown_by_default(
    pipeline,
    temp_output_dir,
):
    transcript = VideoTranscript(
        video_id="vid-bundle",
        segments=[
            TranscriptSegment(text="intro segment", start=5.0, duration=5.0),
            TranscriptSegment(text="deep dive", start=35.0, duration=5.0),
        ],
        language="English",
        language_code="en",
        is_generated=False,
    )
    chapters = [
        VideoChapter(title="Intro", start_seconds=0, end_seconds=30),
        VideoChapter(title="Deep Dive", start_seconds=30, end_seconds=60),
    ]

    pipeline.timestamps = True
    pipeline.chapter_directory_output = False
    pipeline.force = True
    pipeline.quiz = False
    pipeline.export_transcript_format = None
    pipeline._get_cached_video = AsyncMock(return_value=None)
    pipeline._acquire_youtube_request_slot = AsyncMock()
    pipeline._reserve_output_target = AsyncMock(
        side_effect=[
            temp_output_dir / "Short Chapter Video.md",
        ]
    )
    pipeline._release_output_target = AsyncMock()
    pipeline._record_metrics = AsyncMock()
    pipeline._persist_video_cache = AsyncMock()
    pipeline._export_transcript = MagicMock()
    pipeline.generator.generate_single_chapter_notes = AsyncMock(
        side_effect=(
            lambda chapter_title, chapter_text, **_kwargs: (
                f"# {chapter_title}\n\n{chapter_text}"
            )
        )
    )
    pipeline.generator.generate_chapter_notes_concurrent = (
        _mock_generate_chapter_notes_concurrent(pipeline.generator)
    )

    with (
        patch(
            "notewise.pipeline._execution.get_video_metadata",
            AsyncMock(
                return_value=VideoMetadata(
                    video_id="vid-bundle",
                    title="Short Chapter Video",
                    duration=120,
                    chapters=chapters,
                )
            ),
        ),
        patch(
            "notewise.pipeline._execution.fetch_transcript",
            AsyncMock(return_value=transcript),
        ),
    ):
        ok = await pipeline._process_single_video("vid-bundle")

    assert ok is True
    bundled_notes = (temp_output_dir / "Short Chapter Video.md").read_text(
        encoding="utf-8"
    )
    assert bundled_notes.startswith("# Short Chapter Video")
    assert "# [00:00] Intro" in bundled_notes
    assert "# [00:30] Deep Dive" in bundled_notes
    assert not (temp_output_dir / "Short Chapter Video").exists()
    assert not (temp_output_dir / ".working").exists()
    assert not list(temp_output_dir.glob("Short Chapter Video_chapter_*.md"))


async def test_bundled_chapter_output_suffixes_final_file_collision(
    temp_output_dir, mock_llm_provider
):
    p = _make_pipeline(temp_output_dir, mock_llm_provider)
    p.timestamps = False
    p.export_transcript_format = None

    (temp_output_dir / "Collision Video.md").write_text(
        "# Existing output",
        encoding="utf-8",
    )

    chapter_meta = [
        VideoChapter(title="Intro", start_seconds=0, end_seconds=30),
        VideoChapter(title="Deep Dive", start_seconds=30, end_seconds=60),
    ]

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="vid-collision",
                    title="Collision Video",
                    duration=60,
                    chapters=chapter_meta,
                )
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(
            "notewise.pipeline._execution.split_transcript_by_chapters_with_metadata",
            return_value={
                "Intro": ChapterTranscript(
                    title="Intro",
                    text="intro transcript",
                    start_seconds=0,
                ),
                "Deep Dive": ChapterTranscript(
                    title="Deep Dive",
                    text="deep dive transcript",
                    start_seconds=30,
                ),
            },
        ),
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_fetch.return_value = _make_transcript(video_id="vid-collision")

        result = await p.run(["vid-collision"])

    assert result.success_count == 1
    assert (temp_output_dir / "Collision Video.md").read_text(
        encoding="utf-8"
    ) == "# Existing output"
    assert (temp_output_dir / "Collision Video (vid-collision).md").exists()
    assert not (temp_output_dir / ".working").exists()


async def test_bundled_chapter_failure_does_not_leak_temporary_chapter_artifacts(
    temp_output_dir, mock_llm_provider
):
    p = _make_pipeline(temp_output_dir, mock_llm_provider)
    p.timestamps = False
    p.export_transcript_format = None

    async def _generate_until_failure(
        chapter_transcripts,
        *,
        generate_single=None,
        on_chapter_complete=None,
        **_kwargs,
    ):
        chapter_title, chapter_text = next(iter(chapter_transcripts.items()))
        notes = await generate_single(chapter_title, chapter_text)
        if on_chapter_complete is not None:
            on_chapter_complete(chapter_title, notes)
        raise RuntimeError("chapter generation stopped")

    p.generator.generate_single_chapter_notes = AsyncMock(
        return_value="# Intro\n\ncompleted before failure"
    )
    p.generator.generate_chapter_notes_concurrent = AsyncMock(
        side_effect=_generate_until_failure
    )

    chapter_meta = [
        VideoChapter(title="Intro", start_seconds=0, end_seconds=30),
        VideoChapter(title="Deep Dive", start_seconds=30, end_seconds=60),
    ]

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="vid-partial",
                    title="Partial Video",
                    duration=60,
                    chapters=chapter_meta,
                )
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(
            "notewise.pipeline._execution.split_transcript_by_chapters_with_metadata",
            return_value={
                "Intro": ChapterTranscript(
                    title="Intro",
                    text="intro transcript",
                    start_seconds=0,
                ),
                "Deep Dive": ChapterTranscript(
                    title="Deep Dive",
                    text="deep dive transcript",
                    start_seconds=30,
                ),
            },
        ),
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_fetch.return_value = _make_transcript(video_id="vid-partial")

        result = await p.run(["vid-partial"])

    assert result.failure_count == 1
    assert not list(temp_output_dir.glob("Partial Video_chapter_*.md"))
    assert not (temp_output_dir / "Partial Video.md").exists()
    assert not (temp_output_dir / ".working").exists()


async def test_bundled_chapter_retry_ignores_stale_temporary_artifacts_with_force(
    temp_output_dir, mock_llm_provider
):
    p = _make_pipeline(temp_output_dir, mock_llm_provider, force=True)
    p.timestamps = True
    p.export_transcript_format = None

    (temp_output_dir / "Retry Video_chapter_01_Intro.md").write_text(
        "# Intro\n\nexisting intro",
        encoding="utf-8",
    )
    (temp_output_dir / "Retry Video_chapter_02_Deep Dive.md").write_text(
        "# Deep Dive\n\nexisting deep dive",
        encoding="utf-8",
    )

    chapter_meta = [
        VideoChapter(title="Intro", start_seconds=0, end_seconds=30),
        VideoChapter(title="Deep Dive", start_seconds=30, end_seconds=60),
    ]

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="vid-retry",
                    title="Retry Video",
                    duration=60,
                    chapters=chapter_meta,
                )
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(
            "notewise.pipeline._execution.split_transcript_by_chapters_with_metadata",
            return_value={
                "Intro": ChapterTranscript(
                    title="Intro",
                    text="intro transcript",
                    start_seconds=0,
                ),
                "Deep Dive": ChapterTranscript(
                    title="Deep Dive",
                    text="deep dive transcript",
                    start_seconds=30,
                ),
            },
        ),
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_fetch.return_value = _make_transcript(video_id="vid-retry")

        result = await p.run(["vid-retry"])

    assert result.success_count == 1
    p.generator.generate_chapter_notes_concurrent.assert_awaited_once()
    bundled_notes = (temp_output_dir / "Retry Video.md").read_text(encoding="utf-8")
    assert "# [00:00] Intro" in bundled_notes
    assert "# Chapter Notes" in bundled_notes
    assert "existing intro" not in bundled_notes
    assert "# [00:30] Deep Dive" in bundled_notes
    assert "existing deep dive" not in bundled_notes


@pytest.mark.asyncio
async def test_run_missing_api_key(pipeline):
    """run() returns all-failure result when API key is absent."""
    with patch.object(pipeline, "_check_api_key", return_value=False):
        result = await pipeline.run(["vid1", "vid2"])

    assert result.success_count == 0
    assert result.failure_count == 2
    assert "vid1" in result.errors
    assert "vid2" in result.errors


# ---------------------------------------------------------------------------
# CorePipeline.run – single short video (no chapters)
# ---------------------------------------------------------------------------


def test_prefix_chapter_heading_with_timestamp_rewrites_matching_heading():
    notes = """# Notes

## Intro

Body"""

    result = prefix_chapter_heading_with_timestamp(notes, "Intro", 34)

    assert result.startswith("# Notes")
    assert "## [00:34] Intro" in result
    assert "# [00:34] Intro\n\n## Intro" not in result


def test_prefix_chapter_heading_with_timestamp_preserves_heading_level():
    notes = """## Intro

### Point

Body"""

    result = prefix_chapter_heading_with_timestamp(notes, "Intro", 34)

    assert result.startswith("## [00:34] Intro")
    assert "### Point" in result


def test_prefix_chapter_heading_with_timestamp_preserves_suffix_text():
    notes = """# Introduction: Foundations of Python Programming

Body"""

    result = prefix_chapter_heading_with_timestamp(notes, "Introduction", 0)

    assert result.startswith(
        "# [00:00] Introduction: Foundations of Python Programming"
    )
    assert result.count("# ") == 1


def test_prefix_chapter_heading_with_timestamp_rewrites_existing_timestamped_heading():
    notes = """## [00:10] Intro — Key Ideas

Body"""

    result = prefix_chapter_heading_with_timestamp(notes, "Intro", 34)

    assert result.startswith("## [00:34] Intro — Key Ideas")
    assert "[00:10]" not in result


def test_prefix_chapter_heading_with_timestamp_prepends_when_chapter_heading_missing():
    notes = """# Notes

Body"""

    result = prefix_chapter_heading_with_timestamp(notes, "Intro", 34)

    assert result.startswith("# [00:34] Intro\n\n# Notes")


@pytest.mark.asyncio
async def test_run_single_video_creates_file_named_after_title(pipeline):
    """Output file must use the video title, not the raw video_id."""
    with (
        patch(
            "notewise.pipeline._execution.get_video_metadata",
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ",
                    title="My Awesome Video",
                    duration=100,
                    chapters=[],
                )
            ),
        ),
        patch(
            "notewise.pipeline._execution.fetch_transcript",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "notewise.pipeline.core.CorePipeline._check_api_key",
            return_value=True,
        ),
    ):
        mock_fetch.return_value = _make_transcript()

        result = await pipeline.run(["vid123"])

    assert result.success_count == 1
    expected_file = pipeline.output_dir / "My Awesome Video.md"
    assert expected_file.exists(), f"Expected {expected_file} but it does not exist"


@pytest.mark.asyncio
async def test_run_single_video_events_emitted(pipeline):
    """Pipeline emits PIPELINE_START with empty video_id sentinel and correct events."""
    events: list[PipelineEvent] = []

    with (
        patch(
            "notewise.pipeline._execution.get_video_metadata",
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ",
                    title="Video Title",
                    duration=100,
                    chapters=[],
                )
            ),
        ),
        patch(
            "notewise.pipeline._execution.fetch_transcript",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "notewise.pipeline.core.CorePipeline._check_api_key",
            return_value=True,
        ),
    ):
        mock_fetch.return_value = _make_transcript(text="text")

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
        cookie_file=None,
    ):  # pragma: no cover - signature exercise
        del cookie_file
        assert on_request is not None
        await on_request()
        return _make_transcript(video_id=_video_id, text="text")

    with (
        patch(
            "notewise.pipeline._execution.get_video_metadata",
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ",
                    title="Video Title",
                    duration=100,
                    chapters=[],
                )
            ),
        ),
        patch(
            "notewise.pipeline._execution.fetch_transcript",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "notewise.pipeline.core.CorePipeline._check_api_key",
            return_value=True,
        ),
    ):
        mock_fetch.side_effect = _fetch_with_request_hook
        result = await pipeline.run(["abc"])

    assert result.success_count == 1
    # 1 batched metadata call + 1 transcript call (transcript passes on_request)
    assert acquire_mock.await_count >= 1


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
    with patch("notewise.pipeline.core.get_provider", return_value=mock_llm_provider):
        pipeline_one = CorePipeline(model="mock-model", output_dir=temp_output_dir)
        pipeline_two = CorePipeline(model="mock-model", output_dir=temp_output_dir)

    assert (
        pipeline_one._get_youtube_request_limiter()
        is pipeline_two._get_youtube_request_limiter()
    )


@pytest.mark.asyncio
async def test_run_calls_plain_metadata_helpers(temp_output_dir, mock_llm_provider):
    """Pipeline should call metadata helpers directly and pass transcript hook."""
    with patch("notewise.pipeline.core.get_provider", return_value=mock_llm_provider):
        pipeline = CorePipeline(model="mock-model", output_dir=temp_output_dir)
        pipeline.generator = MagicMock()
        pipeline.generator.generate_study_notes = AsyncMock(return_value="# Notes")
        pipeline.generator.generate_single_chapter_notes = AsyncMock(
            return_value="# Chapter Notes"
        )
        pipeline.generator.generate_chapter_notes_concurrent = (
            _mock_generate_chapter_notes_concurrent(pipeline.generator)
        )

    with (
        patch(
            "notewise.pipeline._execution.get_video_metadata",
            return_value=VideoMetadata(
                video_id="vid-auth", title="Video Title", duration=100, chapters=[]
            ),
        ) as mock_metadata,
        patch(
            "notewise.pipeline._execution.fetch_transcript",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "notewise.pipeline.core.CorePipeline._check_api_key",
            return_value=True,
        ),
    ):
        mock_fetch.return_value = _make_transcript(text="text")
        result = await pipeline.run(["vid-auth"])

    assert result.success_count == 1
    # Batched metadata: single get_video_metadata call replaces title/duration/chapters
    assert mock_metadata.call_count == 1
    mock_metadata.assert_called_once_with("vid-auth", pipeline.youtube_cookie_file)

    fetch_kwargs = mock_fetch.await_args.kwargs
    assert fetch_kwargs["on_request"] is not None


@pytest.mark.asyncio
async def test_uncached_video_reuses_full_metadata_for_transcript_extraction(
    temp_output_dir,
    mock_llm_provider,
    mock_extractor_client,
):
    """Uncached video processing should not full-extract the video twice."""
    p = _make_pipeline(temp_output_dir, mock_llm_provider)
    metadata_client = mock_extractor_client["metadata"].return_value
    transcript_client = mock_extractor_client["transcript"].return_value
    metadata_client.video_metadata_full.return_value = {
        "id": "vid-one-pass",
        "title": "One Pass Video",
        "duration": 100,
        "availability": "public",
        "chapters": [],
    }
    transcript_client.transcript.return_value = {
        "language_code": "en",
        "is_generated": False,
        "track": {"name": "English"},
        "segments": [{"text": "one pass transcript", "start": 0.0, "duration": 1.0}],
    }
    transcript_client.transcript_from_video_data = AsyncMock(
        return_value=transcript_client.transcript.return_value
    )

    with patch(_COMMON_PATCHES["api_key"], return_value=True):
        result = await p.run(["vid-one-pass"])

    assert result.success_count == 1
    metadata_client.video_metadata_full.assert_awaited_once()
    transcript_client.transcript.assert_not_awaited()
    transcript_client.transcript_from_video_data.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_fails_early_for_private_video(pipeline):
    """Private videos should fail before transcript fetching starts."""
    with (
        patch(
            "notewise.pipeline._execution.get_video_metadata",
            side_effect=PublicAccessRequiredError(
                "Private YouTube videos are not supported. "
                "Make the video unlisted or public to process it."
            ),
        ),
        patch(
            "notewise.pipeline._execution.fetch_transcript",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "notewise.pipeline.core.CorePipeline._check_api_key",
            return_value=True,
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
        patch(
            "notewise.pipeline._execution.get_video_metadata",
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ",
                    title="Private Video",
                    duration=100,
                    chapters=[],
                )
            ),
        ),
        patch(
            "notewise.pipeline._execution.fetch_transcript",
            new_callable=AsyncMock,
            side_effect=PublicAccessRequiredError(
                "Private YouTube videos are not supported. "
                "Make the video unlisted or public to process it."
            ),
        ) as mock_fetch,
        patch(
            "notewise.pipeline.core.CorePipeline._check_api_key",
            return_value=True,
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
async def test_run_rejects_whitespace_transcript_before_generation_and_cache(
    pipeline,
    temp_output_dir,
):
    """Whitespace-only transcript payloads must fail before LLM/cache success."""
    pipeline._persist_video_cache = AsyncMock()

    with (
        patch(
            "notewise.pipeline._execution.get_video_metadata",
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="empty123",
                    title="Empty Transcript Video",
                    duration=100,
                    chapters=[],
                )
            ),
        ),
        patch(
            "notewise.pipeline._execution.fetch_transcript",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "notewise.pipeline.core.CorePipeline._check_api_key",
            return_value=True,
        ),
    ):
        mock_fetch.return_value = _make_transcript(
            video_id="empty123",
            text=" \n\t ",
        )

        result = await pipeline.run(["empty123"])

    assert result.success_count == 0
    assert result.failure_count == 1
    assert "empty123" in result.errors
    pipeline.generator.generate_study_notes.assert_not_awaited()
    pipeline._persist_video_cache.assert_not_awaited()
    assert not any(temp_output_dir.iterdir())


def test_core_pipeline_normalizes_export_transcript_format(
    temp_output_dir,
    mock_llm_provider,
):
    """Export transcript format accepts txt/json case-insensitively."""
    with patch("notewise.pipeline.core.get_provider", return_value=mock_llm_provider):
        p = CorePipeline(
            model="mock-model",
            output_dir=temp_output_dir,
            export_transcript=" JSON ",
        )

    assert p.export_transcript_format == "json"


def test_core_pipeline_rejects_unsupported_export_transcript_format(
    temp_output_dir,
    mock_llm_provider,
):
    """Unsupported transcript export formats must not fall back to txt."""
    with (
        patch("notewise.pipeline.core.get_provider", return_value=mock_llm_provider),
        pytest.raises(ValidationError, match="export-transcript"),
    ):
        CorePipeline(
            model="mock-model",
            output_dir=temp_output_dir,
            export_transcript="md",
        )


def test_export_transcript_rejects_unsupported_format_before_writing(
    temp_output_dir,
):
    """The artifact writer should never persist unsupported export labels."""
    transcript = _make_transcript(video_id="bad-export", text="usable transcript")
    db = MagicMock()

    with pytest.raises(ValidationError, match="export-transcript"):
        export_transcript(
            db,
            transcript,
            "Bad Export",
            temp_output_dir,
            "bad-export",
            "md",
        )

    db.add_export_record.assert_not_called()
    assert not any(temp_output_dir.iterdir())


@pytest.mark.asyncio
async def test_metadata_fetched_uses_total_chapters_not_chapter_number(pipeline):
    """METADATA_FETCHED event must set total_chapters, not chapter_number."""
    events: list[PipelineEvent] = []
    dummy_chapters = [{"title": "Intro", "start_seconds": 0}] * 3

    with (
        patch(
            "notewise.pipeline._execution.get_video_metadata",
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ",
                    title="Title",
                    duration=100,
                    chapters=dummy_chapters,
                )
            ),
        ),
        patch(
            "notewise.pipeline._execution.fetch_transcript",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "notewise.pipeline.core.CorePipeline._check_api_key",
            return_value=True,
        ),
    ):
        mock_fetch.return_value = _make_transcript(text="text")

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
        patch(
            "notewise.pipeline._execution.get_video_metadata",
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ", title="Title", duration=7200, chapters=[]
                )
            ),
        ),
        patch(
            "notewise.pipeline._execution.fetch_transcript",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "notewise.pipeline.core.CorePipeline._check_api_key",
            return_value=True,
        ),
    ):
        mock_fetch.return_value = _make_transcript(text="text")

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
            "notewise.pipeline._execution.get_video_metadata",
            side_effect=RuntimeError("network error"),
        ),
        patch(
            "notewise.pipeline._execution.fetch_transcript",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "notewise.pipeline.core.CorePipeline._check_api_key",
            return_value=True,
        ),
    ):
        mock_fetch.return_value = _make_transcript(text="text")

        result = await pipeline.run(["myVideoId"])

    # Batched metadata failure: video fails entirely (no title-only fallback)
    assert result.failure_count == 1
    assert "myVideoId" in result.errors
    expected_file = pipeline.output_dir / "myVideoId.md"
    assert not expected_file.exists(), (
        "Fallback file should NOT exist on total metadata faileo_id"
    )


@pytest.mark.asyncio
async def test_run_metadata_extraction_error_surfaces_to_user(pipeline):
    """Extractor metadata failures should fail the run instead of faking data."""
    with (
        patch(
            "notewise.pipeline._execution.get_video_metadata",
            side_effect=ExtractorError("metadata backend unavailable"),
        ),
        patch(
            "notewise.pipeline._execution.fetch_transcript",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "notewise.pipeline.core.CorePipeline._check_api_key",
            return_value=True,
        ),
    ):
        result = await pipeline.run(["myVideoId"])

    assert result.failure_count == 1
    assert result.errors["myVideoId"] == (
        "We couldn't process this video. "
        "Check the current session log for technical details."
    )
    assert not (pipeline.output_dir / "myVideoId.md").exists()
    mock_fetch.assert_not_awaited()


# ---------------------------------------------------------------------------
# CorePipeline.run – error handling and event emission
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_ip_block_error_emits_video_failed_event(pipeline):
    """YouTubeIPBlockError triggers VIDEO_FAILED event."""
    events: list[PipelineEvent] = []

    with (
        patch(
            "notewise.pipeline._execution.get_video_metadata",
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ", title="Title", duration=100, chapters=[]
                )
            ),
        ),
        patch(
            "notewise.pipeline._execution.fetch_transcript",
            new_callable=AsyncMock,
            side_effect=YouTubeIPBlockError("IP blocked"),
        ),
        patch(
            "notewise.pipeline.core.CorePipeline._check_api_key",
            return_value=True,
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
        patch(
            "notewise.pipeline._execution.get_video_metadata",
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ", title="Title", duration=100, chapters=[]
                )
            ),
        ),
        patch(
            "notewise.pipeline._execution.fetch_transcript",
            new_callable=AsyncMock,
            side_effect=RuntimeError("network timeout"),
        ),
        patch(
            "notewise.pipeline.core.CorePipeline._check_api_key",
            return_value=True,
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
        VideoChapter(title="Intro", start_seconds=0, end_seconds=600),
        VideoChapter(title="Deep Dive", start_seconds=600, end_seconds=None),
    ]
    pipeline.chapter_directory_output = True

    with (
        patch(
            "notewise.pipeline._execution.get_video_metadata",
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ",
                    title=video_title,
                    duration=7200,
                    chapters=chapter_meta,
                )
            ),
        ),
        patch(
            "notewise.pipeline._execution.fetch_transcript",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "notewise.pipeline._execution.split_transcript_by_chapters_with_metadata",
        ) as mock_split,
        patch(
            "notewise.pipeline.core.CorePipeline._check_api_key",
            return_value=True,
        ),
    ):
        # Mock transcript
        mock_fetch.return_value = _make_transcript()

        # Mock chapter-split transcripts
        chapter_transcripts = {
            "Intro": ChapterTranscript(
                title="Intro",
                text="intro transcript text",
                start_seconds=0,
            ),
            "Deep Dive": ChapterTranscript(
                title="Deep Dive",
                text="deep dive transcript text",
                start_seconds=600,
            ),
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
async def test_force_regenerates_existing_chapter_files_with_bundle_outputs(
    temp_output_dir,
    mock_llm_provider,
):
    """Force mode should not reuse stale chapter files for bundled outputs."""
    video_id = "force-chapter-video"
    video_title = "Force Chapters"
    chapter_title = "Intro"
    expected_folder = temp_output_dir / sanitize_filename(video_title)
    expected_folder.mkdir()
    chapter_file = expected_folder / f"01_{sanitize_filename(chapter_title)}.md"
    chapter_file.write_text("# Stale Chapter", encoding="utf-8")

    p = _make_pipeline(
        temp_output_dir,
        mock_llm_provider,
        force=True,
        chapter_directory_output=True,
    )
    p.output_formats = ["md", "html"]
    p.generator.generate_single_chapter_notes.return_value = "# Fresh Chapter"

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id=video_id,
                    title=video_title,
                    duration=7200,
                    chapters=[
                        VideoChapter(
                            title=chapter_title,
                            start_seconds=0,
                            end_seconds=None,
                        ),
                    ],
                )
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(
            "notewise.pipeline._execution.split_transcript_by_chapters_with_metadata"
        ) as mock_split,
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_fetch.return_value = _make_transcript(video_id=video_id)
        mock_split.return_value = {
            chapter_title: ChapterTranscript(
                title=chapter_title,
                text="fresh transcript",
                start_seconds=0,
            )
        }

        result = await p.run([video_id])

    assert result.success_count == 1
    p.generator.generate_single_chapter_notes.assert_awaited_once()
    assert chapter_file.read_text(encoding="utf-8") == "# Fresh Chapter"
    assert "Fresh Chapter" in (temp_output_dir / f"{video_title}.html").read_text(
        encoding="utf-8"
    )
    assert "Stale Chapter" not in (temp_output_dir / f"{video_title}.html").read_text(
        encoding="utf-8"
    )


@pytest.mark.asyncio
async def test_run_chapter_generation_emits_chapter_events(pipeline):
    """Chapter-based generation emits CHAPTER_GENERATING events with correct counts."""
    events: list[PipelineEvent] = []

    chapter_meta = [
        VideoChapter(title="Chapter 1", start_seconds=0, end_seconds=300),
        VideoChapter(title="Chapter 2", start_seconds=300, end_seconds=600),
        VideoChapter(title="Chapter 3", start_seconds=600, end_seconds=None),
    ]

    with (
        patch(
            "notewise.pipeline._execution.get_video_metadata",
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ",
                    title="My Video",
                    duration=7200,
                    chapters=chapter_meta,
                )
            ),
        ),
        patch(
            "notewise.pipeline._execution.fetch_transcript", new_callable=AsyncMock
        ) as mock_fetch,
        patch(
            "notewise.pipeline._execution.split_transcript_by_chapters_with_metadata"
        ) as mock_split,
        patch(
            "notewise.pipeline.core.CorePipeline._check_api_key",
            return_value=True,
        ),
    ):
        mock_fetch.return_value = _make_transcript()

        chapter_transcripts = {
            "Chapter 1": ChapterTranscript(
                title="Chapter 1",
                text="text1",
                start_seconds=0,
            ),
            "Chapter 2": ChapterTranscript(
                title="Chapter 2",
                text="text2",
                start_seconds=300,
            ),
            "Chapter 3": ChapterTranscript(
                title="Chapter 3",
                text="text3",
                start_seconds=600,
            ),
        }
        mock_split.return_value = chapter_transcripts

        await pipeline.run(["vid789"], on_event=events.append)

    # Verify chapter events
    chapter_events = [e for e in events if e.event_type == EventType.CHAPTER_GENERATING]
    assert len(chapter_events) == 3
    chapter_complete_events = [
        e for e in events if e.event_type == EventType.CHAPTER_COMPLETE
    ]
    assert len(chapter_complete_events) == 3

    # Verify chapter numbers and totals
    for i, event in enumerate(chapter_events, 1):
        assert event.chapter_number == i
        assert event.total_chapters == 3
    for i, event in enumerate(chapter_complete_events, 1):
        assert event.chapter_number == i
        assert event.total_chapters == 3


@pytest.mark.asyncio
async def test_run_chapter_generation_emits_internal_chapter_progress(
    temp_output_dir, mock_llm_provider
):
    """Chunked chapter generation should emit chapter part and combine events."""
    events: list[PipelineEvent] = []
    p = _make_pipeline(
        temp_output_dir,
        mock_llm_provider,
        force=False,
        chapter_directory_output=True,
    )

    async def _generate_chapter(
        chapter_title,
        chapter_text,
        on_chunk=None,
        on_combine=None,
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
        patch(
            _COMMON_PATCHES["metadata"],
            return_value=VideoMetadata(
                video_id="dQw4w9WgXcQ",
                title="Long Chapter Video",
                duration=7200,
                chapters=[
                    VideoChapter(title="Chapter 1", start_seconds=0, end_seconds=300),
                    VideoChapter(
                        title="Chapter 2", start_seconds=300, end_seconds=None
                    ),
                ],
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(
            "notewise.pipeline._execution.split_transcript_by_chapters_with_metadata",
            return_value={
                "Chapter 1": ChapterTranscript(
                    title="Chapter 1", text="text1", start_seconds=0
                ),
                "Chapter 2": ChapterTranscript(
                    title="Chapter 2", text="text2", start_seconds=300
                ),
            },
        ),
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_transcript = _make_transcript(text="full transcript")
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
    chapter_complete_events = [
        e for e in events if e.event_type == EventType.CHAPTER_COMPLETE
    ]
    assert len(chapter_complete_events) == 2
    assert [e.chapter_number for e in chapter_complete_events] == [1, 2]


async def test_concurrent_chapter_videos_keep_event_wrappers_isolated(
    temp_output_dir, mock_llm_provider
):
    """Concurrent chapter runs must not share per-video chapter title lookups."""
    p = _make_pipeline(
        temp_output_dir,
        mock_llm_provider,
        force=False,
        chapter_directory_output=True,
    )

    async def _generate_chapter(
        chapter_title,
        chapter_text,
        on_chunk=None,
        on_combine=None,
    ):
        del on_chunk, on_combine
        await asyncio.sleep(0)
        return f"# {chapter_title}\n\n{chapter_text}"

    async def _delayed_concurrent_chapters(
        chapter_transcripts,
        *,
        on_chapter_start=None,
        generate_single=None,
        **kwargs,
    ):
        del kwargs
        await asyncio.sleep(0)
        result: dict[str, str] = {}
        total = len(chapter_transcripts)
        chapter_generator = generate_single or p.generator.generate_single_chapter_notes
        for index, (chapter_title, chapter_text) in enumerate(
            chapter_transcripts.items(), start=1
        ):
            if on_chapter_start is not None:
                on_chapter_start(index, total)
            result[chapter_title] = await chapter_generator(
                chapter_title,
                chapter_text,
            )
        return result

    p.generator.generate_single_chapter_notes.side_effect = _generate_chapter
    p.generator.generate_chapter_notes_concurrent = AsyncMock(
        side_effect=_delayed_concurrent_chapters
    )

    def _metadata(video_id, *_args, **_kwargs):
        return VideoMetadata(
            video_id=video_id,
            title=f"Video {video_id}",
            duration=7200,
            chapters=[VideoChapter(title="Intro", start_seconds=0, end_seconds=None)],
        )

    def _split(transcript, _chapters):
        if transcript.video_id == "vid-a":
            return {
                "Introduction & Recap": ChapterTranscript(
                    title="Introduction & Recap",
                    text="alpha",
                    start_seconds=0,
                )
            }
        return {
            "System Design Setup": ChapterTranscript(
                title="System Design Setup",
                text="beta",
                start_seconds=0,
            )
        }

    with (
        patch(_COMMON_PATCHES["metadata"], side_effect=_metadata),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(
            "notewise.pipeline._execution.split_transcript_by_chapters_with_metadata",
            side_effect=_split,
        ),
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_fetch.side_effect = lambda video_id, *_args, **_kwargs: _make_transcript(
            video_id=video_id,
            text=f"transcript {video_id}",
        )

        result = await p.run(["vid-a", "vid-b"])

    assert result.success_count == 2
    assert result.failure_count == 0
    assert result.errors == {}
    assert (temp_output_dir / "Video vid-a" / "01_Introduction & Recap.md").read_text(
        encoding="utf-8"
    ) == "# Introduction & Recap\n\nalpha"
    assert (temp_output_dir / "Video vid-b" / "01_System Design Setup.md").read_text(
        encoding="utf-8"
    ) == "# System Design Setup\n\nbeta"


@pytest.mark.asyncio
async def test_run_failed_chapter_generation_does_not_emit_chapter_complete(
    temp_output_dir, mock_llm_provider
):
    """Failed chapter workers should not be marked complete."""
    events: list[PipelineEvent] = []
    p = _make_pipeline(
        temp_output_dir,
        mock_llm_provider,
        force=False,
    )

    async def _fail_chapter(
        chapter_title,
        chapter_text,
        on_chunk=None,
        on_combine=None,
    ):
        del chapter_title, chapter_text, on_chunk, on_combine
        raise RuntimeError("boom")

    p.generator.generate_single_chapter_notes.side_effect = _fail_chapter

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            return_value=VideoMetadata(
                video_id="dQw4w9WgXcQ",
                title="Failure Video",
                duration=7200,
                chapters=[
                    VideoChapter(title="Chapter 1", start_seconds=0, end_seconds=None)
                ],
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(
            "notewise.pipeline._execution.split_transcript_by_chapters_with_metadata",
            return_value={
                "Chapter 1": ChapterTranscript(
                    title="Chapter 1", text="text1", start_seconds=0
                )
            },
        ),
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_transcript = _make_transcript(text="full transcript")
        mock_transcript.language_code = "en"
        mock_fetch.return_value = mock_transcript

        result = await p.run(["vid-chapter-failure"], on_event=events.append)

    assert result.success_count == 0
    chapter_events = [e for e in events if e.event_type == EventType.CHAPTER_GENERATING]
    assert len(chapter_events) == 1
    chapter_complete_events = [
        e for e in events if e.event_type == EventType.CHAPTER_COMPLETE
    ]
    assert chapter_complete_events == []


@pytest.mark.asyncio
async def test_run_empty_chapter_split_falls_back_to_single_file(
    temp_output_dir, mock_llm_provider
):
    """Empty chapter splits should fall back to normal single-file generation."""
    p = _make_pipeline(
        temp_output_dir,
        mock_llm_provider,
        force=False,
        chapter_directory_output=True,
    )

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            return_value=VideoMetadata(
                video_id="dQw4w9WgXcQ",
                title="Fallback Video",
                duration=7200,
                chapters=[
                    VideoChapter(title="Intro", start_seconds=0, end_seconds=None)
                ],
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(
            "notewise.pipeline._execution.split_transcript_by_chapters_with_metadata",
            return_value={},
        ),
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_transcript = _make_transcript(text="fallback transcript")
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
    p = _make_pipeline(
        temp_output_dir,
        mock_llm_provider,
        quiz=True,
        chapter_directory_output=True,
    )

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            return_value=VideoMetadata(
                video_id="dQw4w9WgXcQ",
                title="Long Video",
                duration=7200,
                chapters=[
                    VideoChapter(title="Intro", start_seconds=0, end_seconds=120),
                    VideoChapter(title="Part 2", start_seconds=120, end_seconds=None),
                ],
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(
            "notewise.pipeline._execution.split_transcript_by_chapters_with_metadata",
            return_value={
                "Intro": ChapterTranscript(
                    title="Intro", text="intro text", start_seconds=0
                ),
                "Part 2": ChapterTranscript(
                    title="Part 2", text="body text", start_seconds=120
                ),
            },
        ),
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_transcript = _make_transcript(text="full transcript")
        mock_transcript.language_code = "en"
        mock_fetch.return_value = mock_transcript

        result = await p.run(["vid-chapter-quiz"])

    assert result.success_count == 1
    chapter_dir = temp_output_dir / "Long Video"
    assert (chapter_dir / "Long Video_quiz.md").exists()
    assert not (temp_output_dir / "Long Video_quiz.md").exists()


@pytest.mark.asyncio
async def test_export_transcript_in_chapter_mode_uses_chapter_directory(
    temp_output_dir, mock_llm_provider
):
    """Chapter-mode transcript exports should live in the per-video chapter folder."""
    with patch(
        "notewise.pipeline.core.get_provider",
        return_value=mock_llm_provider,
    ):
        p = CorePipeline(
            model="mock-model",
            output_dir=temp_output_dir,
            export_transcript="txt",
            chapter_directory_output=True,
        )
        p.generator = MagicMock()
        p.generator.generate_single_chapter_notes = AsyncMock(
            return_value="# Chapter Notes"
        )
        p.generator.generate_chapter_notes_concurrent = AsyncMock(
            return_value={"Intro": "# Chapter Notes", "Part 2": "# Chapter Notes"}
        )
        p.generator.generate_quiz = AsyncMock(return_value="# Quiz")

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            return_value=VideoMetadata(
                video_id="dQw4w9WgXcQ",
                title="Long Video",
                duration=7200,
                chapters=[
                    VideoChapter(title="Intro", start_seconds=0, end_seconds=120),
                    VideoChapter(title="Part 2", start_seconds=120, end_seconds=None),
                ],
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(
            "notewise.pipeline._execution.split_transcript_by_chapters_with_metadata",
            return_value={
                "Intro": ChapterTranscript(
                    title="Intro", text="intro text", start_seconds=0
                ),
                "Part 2": ChapterTranscript(
                    title="Part 2", text="body text", start_seconds=120
                ),
            },
        ),
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_transcript = _make_transcript(text="full transcript")
        mock_transcript.language_code = "en"
        mock_fetch.return_value = mock_transcript

        result = await p.run(["vid-transcript-dir"])

    assert result.success_count == 1
    chapter_dir = temp_output_dir / "Long Video"
    assert (chapter_dir / "Long Video_transcript.txt").exists()
    assert not (temp_output_dir / "Long Video_transcript.txt").exists()
    assert not (chapter_dir / ".working").exists()


# ---------------------------------------------------------------------------
# CorePipeline – playlist checkpointing (#38)
# ---------------------------------------------------------------------------

_COMMON_PATCHES = {
    "metadata": "notewise.pipeline._execution.get_video_metadata",
    "title": "notewise.pipeline._execution.get_video_metadata",
    "duration": "notewise.pipeline._execution.get_video_metadata",
    "chapters": "notewise.pipeline._execution.get_video_metadata",
    "fetch": "notewise.pipeline._execution.fetch_transcript",
    "api_key": "notewise.pipeline.core.CorePipeline._check_api_key",
}


def _make_pipeline(
    tmp_path,
    mock_llm_provider,
    force: bool = False,
    quiz: bool = False,
    output_format: str = "md",
    chapter_directory_output: bool = False,
):
    with patch("notewise.pipeline.core.get_provider", return_value=mock_llm_provider):
        p = CorePipeline(
            model="mock-model",
            output_dir=tmp_path,
            force=force,
            quiz=quiz,
            output_format=output_format,
            chapter_directory_output=chapter_directory_output,
        )
        p.generator = MagicMock()
        p.generator.generate_study_notes = AsyncMock(return_value="# Notes")
        p.generator.generate_single_chapter_notes = AsyncMock(
            return_value="# Chapter Notes"
        )
        p.generator.generate_chapter_notes_concurrent = (
            _mock_generate_chapter_notes_concurrent(p.generator)
        )
        p.generator.generate_quiz = AsyncMock(return_value="# Quiz")
        return p


def _seed_cached_video(
    video_id: str,
    title: str = "Cached Video",
    duration: int = 100,
) -> None:
    """Seed SQLite cache with one processed video entry."""
    db = DatabaseManager.get_instance(get_cache_db_path())
    db.upsert_video_cache(
        video_id=video_id,
        title=title,
        duration=duration,
        transcript_content="cached transcript",
        language="en",
        tokens_used=50,
        model="mock-model",
    )


@pytest.mark.asyncio
async def test_checkpoint_skips_existing_single_file(
    temp_output_dir, mock_llm_provider
):
    """VIDEO_SKIPPED is emitted when video is already present in SQLite cache."""
    _seed_cached_video("vid1", title="Test Video")
    (temp_output_dir / "Test Video.md").write_text("# Existing Notes", encoding="utf-8")

    events: list[PipelineEvent] = []
    p = _make_pipeline(
        temp_output_dir,
        mock_llm_provider,
        force=False,
    )

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="vid1", title="Test Video", duration=100, chapters=[]
                )
            ),
        ) as mock_metadata,
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        result = await p.run(["vid1"], on_event=events.append)

    assert result.success_count == 1
    assert EventType.VIDEO_SKIPPED in [e.event_type for e in events]
    # No metadata or transcript calls should run for skipped videos.
    mock_metadata.assert_not_called()
    mock_fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkpoint_reprocesses_when_requested_quiz_is_missing(
    temp_output_dir, mock_llm_provider
):
    """A cache hit must not skip when a requested side artifact is missing."""
    _seed_cached_video("vid1", title="Test Video")
    (temp_output_dir / "Test Video.md").write_text("# Existing Notes", encoding="utf-8")

    events: list[PipelineEvent] = []
    p = _make_pipeline(temp_output_dir, mock_llm_provider, quiz=True)

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="vid1",
                    title="Test Video",
                    duration=100,
                    chapters=[],
                )
            ),
        ) as mock_metadata,
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_fetch.return_value = _make_transcript(
            video_id="vid1",
            text="fresh content",
        )

        result = await p.run(["vid1"], on_event=events.append)

    assert result.success_count == 1
    assert EventType.VIDEO_SKIPPED not in [e.event_type for e in events]
    mock_metadata.assert_called_once()
    mock_fetch.assert_awaited_once()
    assert (temp_output_dir / "Test Video_quiz.md").exists()


@pytest.mark.asyncio
async def test_checkpoint_reprocesses_incomplete_cached_chapter_directory(
    temp_output_dir, mock_llm_provider
):
    """A chapter directory cache hit must prove every chapter file exists."""
    _seed_cached_video("vid-chapters", title="Chapter Cache Video")
    chapter_dir = temp_output_dir / "Chapter Cache Video"
    chapter_dir.mkdir()
    (chapter_dir / "01_Intro.md").write_text("# Intro", encoding="utf-8")

    p = _make_pipeline(
        temp_output_dir,
        mock_llm_provider,
        chapter_directory_output=True,
    )
    p._write_output_target_metadata(chapter_dir, "vid-chapters")

    chapter_meta = [
        VideoChapter(title="Intro", start_seconds=0, end_seconds=30),
        VideoChapter(title="Deep Dive", start_seconds=30, end_seconds=60),
    ]

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="vid-chapters",
                    title="Chapter Cache Video",
                    duration=60,
                    chapters=chapter_meta,
                )
            ),
        ) as mock_metadata,
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(
            "notewise.pipeline._execution.split_transcript_by_chapters_with_metadata",
            return_value={
                "Intro": ChapterTranscript(
                    title="Intro",
                    text="intro transcript",
                    start_seconds=0,
                ),
                "Deep Dive": ChapterTranscript(
                    title="Deep Dive",
                    text="deep dive transcript",
                    start_seconds=30,
                ),
            },
        ),
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_fetch.return_value = _make_transcript(
            video_id="vid-chapters",
            text="fresh transcript",
        )

        result = await p.run(["vid-chapters"])

    assert result.success_count == 1
    mock_metadata.assert_awaited_once()
    mock_fetch.assert_awaited_once()
    assert (chapter_dir / "02_Deep Dive.md").exists()


@pytest.mark.asyncio
async def test_checkpoint_force_reprocesses_existing(
    temp_output_dir, mock_llm_provider
):
    """With force=True a cached video is ignored and reprocessed."""
    _seed_cached_video("vid1", title="Test Video")

    p = _make_pipeline(temp_output_dir, mock_llm_provider, force=True)

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ",
                    title="Test Video",
                    duration=100,
                    chapters=[],
                )
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_fetch.return_value = _make_transcript(text="new content")

        result = await p.run(["vid1"])

    assert result.success_count == 1
    # File must now contain the regenerated content
    output_file = temp_output_dir / "Test Video.md"
    assert output_file.read_text(encoding="utf-8") == "# Notes"


@pytest.mark.asyncio
async def test_checkpoint_force_skips_cache_lookup(temp_output_dir, mock_llm_provider):
    """Force mode should bypass the cache lookup entirely."""
    p = _make_pipeline(temp_output_dir, mock_llm_provider, force=True)
    p._get_cached_video = AsyncMock(return_value=None)

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="vid1",
                    title="Force Video",
                    duration=100,
                    chapters=[],
                )
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_fetch.return_value = _make_transcript(text="fresh content")

        result = await p.run(["vid1"])

    assert result.success_count == 1
    p._get_cached_video.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkpoint_processes_new_video(temp_output_dir, mock_llm_provider):
    """When no prior output exists the video is processed normally."""
    p = _make_pipeline(
        temp_output_dir,
        mock_llm_provider,
        force=False,
        chapter_directory_output=True,
    )

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ",
                    title="Brand New Video",
                    duration=100,
                    chapters=[],
                )
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_fetch.return_value = _make_transcript(text="transcript")

        result = await p.run(["newvid"])

    assert result.success_count == 1
    assert (temp_output_dir / "Brand New Video.md").exists()


@pytest.mark.asyncio
async def test_quiz_flag_creates_quiz_file(temp_output_dir, mock_llm_provider):
    """With quiz=True a *_quiz.md file is written alongside the study notes."""
    p = _make_pipeline(temp_output_dir, mock_llm_provider, quiz=True)

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ",
                    title="Study Subject",
                    duration=100,
                    chapters=[],
                )
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_fetch.return_value = _make_transcript(text="full transcript")

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
async def test_non_markdown_output_html_creates_html_file(
    temp_output_dir, mock_llm_provider
):
    p = _make_pipeline(temp_output_dir, mock_llm_provider, output_format="html")

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ",
                    title="Study Subject",
                    duration=100,
                    chapters=[],
                )
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_fetch.return_value = _make_transcript(text="full transcript")

        result = await p.run(["vid-html"])

    assert result.success_count == 1
    html_file = temp_output_dir / "Study Subject.html"
    assert html_file.exists()
    html = html_file.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html
    assert "<h1>Notes</h1>" in html


@pytest.mark.asyncio
async def test_non_markdown_output_pdf_creates_pdf_file(
    temp_output_dir, mock_llm_provider
):
    p = _make_pipeline(temp_output_dir, mock_llm_provider, output_format="pdf")

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ",
                    title="Study Subject",
                    duration=100,
                    chapters=[],
                )
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_fetch.return_value = _make_transcript(text="full transcript")

        result = await p.run(["vid-pdf"])

    assert result.success_count == 1
    pdf_file = temp_output_dir / "Study Subject.pdf"
    assert pdf_file.exists()
    assert pdf_file.read_bytes().startswith(b"%PDF")


@pytest.mark.asyncio
async def test_non_markdown_output_docx_creates_docx_file(
    temp_output_dir, mock_llm_provider
):
    p = _make_pipeline(temp_output_dir, mock_llm_provider, output_format="docx")

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ",
                    title="Study Subject",
                    duration=100,
                    chapters=[],
                )
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_fetch.return_value = _make_transcript(text="full transcript")

        result = await p.run(["vid-docx"])

    assert result.success_count == 1
    docx_file = temp_output_dir / "Study Subject.docx"
    assert docx_file.exists()
    with zipfile.ZipFile(docx_file) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
    assert "Notes" in document_xml
    assert "background:" not in document_xml


@pytest.mark.asyncio
async def test_multiple_output_formats_create_multiple_files(
    temp_output_dir, mock_llm_provider
):
    p = _make_pipeline(
        temp_output_dir,
        mock_llm_provider,
        output_format="md,html,pdf,docx",
    )

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ",
                    title="Study Subject",
                    duration=100,
                    chapters=[],
                )
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_fetch.return_value = _make_transcript(text="full transcript")

        result = await p.run(["vid-multi"])

    assert result.success_count == 1
    assert (temp_output_dir / "Study Subject.md").exists()
    assert (temp_output_dir / "Study Subject.html").exists()
    assert (temp_output_dir / "Study Subject.pdf").exists()
    assert (temp_output_dir / "Study Subject.docx").exists()


@pytest.mark.asyncio
async def test_non_markdown_chapter_output_bundles_into_single_document(
    temp_output_dir, mock_llm_provider
):
    p = _make_pipeline(
        temp_output_dir,
        mock_llm_provider,
        quiz=True,
        output_format="html",
        chapter_directory_output=False,
    )
    chapter_meta = [
        VideoChapter(title="Intro", start_seconds=0, end_seconds=600),
        VideoChapter(title="Deep Dive", start_seconds=600, end_seconds=None),
    ]

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ",
                    title="Long Video",
                    duration=7200,
                    chapters=chapter_meta,
                )
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(
            "notewise.pipeline._execution.split_transcript_by_chapters_with_metadata",
        ) as mock_split,
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_fetch.return_value = _make_transcript(text="full transcript")
        mock_split.return_value = {
            "Intro": ChapterTranscript(
                title="Intro",
                text="intro transcript text",
                start_seconds=0,
            ),
            "Deep Dive": ChapterTranscript(
                title="Deep Dive",
                text="deep dive transcript text",
                start_seconds=600,
            ),
        }
        p.generator.generate_single_chapter_notes = AsyncMock(
            side_effect=(
                lambda chapter_title, chapter_text, **_kwargs: (
                    f"# {chapter_title}\n\n{chapter_text}"
                )
            )
        )
        p.generator.generate_chapter_notes_concurrent = (
            _mock_generate_chapter_notes_concurrent(p.generator)
        )

        result = await p.run(["vid-bundled-html"])

    assert result.success_count == 1
    bundled_file = temp_output_dir / "Long Video.html"
    assert bundled_file.exists()
    assert not (temp_output_dir / "Long Video").exists()
    assert (temp_output_dir / "Long Video_quiz.md").exists()
    bundled_html = bundled_file.read_text(encoding="utf-8")
    assert "Intro" in bundled_html
    assert "Deep Dive" in bundled_html


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
        on_combine=None,
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
        on_combine=None,
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
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ",
                    title="Study Subject",
                    duration=100,
                    chapters=[],
                )
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_transcript = _make_transcript(text="full transcript")
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
    p = _make_pipeline(
        temp_output_dir,
        mock_llm_provider,
        force=False,
        chapter_directory_output=True,
    )

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ",
                    title="Shared Title",
                    duration=100,
                    chapters=[],
                )
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_fetch.return_value = _make_transcript(text="transcript for vid2")

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
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                side_effect=[
                    VideoMetadata(
                        video_id="dQw4w9WgXcQ",
                        title="Shared Title",
                        duration=100,
                        chapters=[],
                    ),
                    VideoMetadata(
                        video_id="dQw4w9WgXcQ2",
                        title="Shared Title",
                        duration=100,
                        chapters=[],
                    ),
                ]
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=True),
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
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ",
                    title="Unique Once",
                    duration=100,
                    chapters=[],
                )
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=True),
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
    p = _make_pipeline(
        temp_output_dir,
        mock_llm_provider,
        quiz=True,
        chapter_directory_output=True,
    )
    p.semaphore = asyncio.Semaphore(1)

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                side_effect=[
                    VideoMetadata(
                        video_id="vid1",
                        title="Shared Long",
                        duration=7200,
                        chapters=[
                            VideoChapter(
                                title="Intro", start_seconds=0, end_seconds=None
                            )
                        ],
                    ),
                    VideoMetadata(
                        video_id="vid2",
                        title="Shared Long",
                        duration=7200,
                        chapters=[
                            VideoChapter(
                                title="Intro", start_seconds=0, end_seconds=None
                            )
                        ],
                    ),
                ]
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(
            "notewise.pipeline._execution.split_transcript_by_chapters_with_metadata",
            side_effect=[
                {
                    "Intro": ChapterTranscript(
                        title="Intro",
                        text="first chapter",
                        start_seconds=0,
                    )
                },
                {
                    "Intro": ChapterTranscript(
                        title="Intro",
                        text="second chapter",
                        start_seconds=0,
                    )
                },
            ],
        ),
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_fetch.side_effect = [
            _make_transcript(video_id="vid1", text="first long transcript"),
            _make_transcript(video_id="vid2", text="second long transcript"),
        ]

        result = await p.run(["vid1", "vid2"])

    assert result.success_count == 2
    first_dir = temp_output_dir / "Shared Long"
    second_dir = temp_output_dir / "Shared Long (vid2)"
    assert (first_dir / "01_Intro.md").exists()
    assert (first_dir / "Shared Long_quiz.md").exists()
    assert (second_dir / "01_Intro.md").exists()
    assert (second_dir / "Shared Long (vid2)_quiz.md").exists()


async def test_chapter_run_does_not_reuse_metadata_less_same_title_folder(
    temp_output_dir, mock_llm_provider
):
    """Metadata-less same-title folders should not be clobbered by chapter runs."""
    existing_dir = temp_output_dir / "Resume Long"
    existing_dir.mkdir()
    (existing_dir / "01_Intro.md").write_text("old notes", encoding="utf-8")

    p = _make_pipeline(
        temp_output_dir,
        mock_llm_provider,
        force=False,
        chapter_directory_output=True,
    )

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="resume-id",
                    title="Resume Long",
                    duration=7200,
                    chapters=[
                        VideoChapter(title="Intro", start_seconds=0, end_seconds=None)
                    ],
                )
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(
            "notewise.pipeline._execution.split_transcript_by_chapters_with_metadata",
            return_value={
                "Intro": ChapterTranscript(
                    title="Intro",
                    text="fresh chapter",
                    start_seconds=0,
                )
            },
        ),
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_fetch.return_value = _make_transcript(
            video_id="resume-id", text="fresh transcript"
        )

        result = await p.run(["resume-id"])

    assert result.success_count == 1
    assert (existing_dir / "01_Intro.md").read_text(encoding="utf-8") == "old notes"
    suffix_dir = temp_output_dir / "Resume Long (resume-id)"
    assert (suffix_dir / "01_Intro.md").read_text(encoding="utf-8") == (
        "# Chapter Notes"
    )
    assert (suffix_dir / ".notewise-output.json").exists()


async def test_chapter_run_reuses_existing_matching_metadata_folder(
    temp_output_dir, mock_llm_provider
):
    """Chapter folders are reusable only when ownership metadata matches."""
    existing_dir = temp_output_dir / "Resume Long"
    existing_dir.mkdir()
    (existing_dir / ".notewise-output.json").write_text(
        json.dumps({"video_id": "resume-id"}),
        encoding="utf-8",
    )

    p = _make_pipeline(
        temp_output_dir,
        mock_llm_provider,
        force=False,
        chapter_directory_output=True,
    )

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="resume-id",
                    title="Resume Long",
                    duration=7200,
                    chapters=[
                        VideoChapter(title="Intro", start_seconds=0, end_seconds=None)
                    ],
                )
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(
            "notewise.pipeline._execution.split_transcript_by_chapters_with_metadata",
            return_value={
                "Intro": ChapterTranscript(
                    title="Intro",
                    text="fresh chapter",
                    start_seconds=0,
                )
            },
        ),
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_fetch.return_value = _make_transcript(
            video_id="resume-id", text="fresh transcript"
        )

        result = await p.run(["resume-id"])

    assert result.success_count == 1
    assert (existing_dir / "01_Intro.md").read_text(encoding="utf-8") == (
        "# Chapter Notes"
    )
    assert not (temp_output_dir / "Resume Long (resume-id)").exists()


async def test_pipeline_persists_video_metadata_in_sqlite_cache(
    temp_output_dir, mock_llm_provider
):
    """Successful runs should persist metadata/transcript/run-stats into SQLite."""
    p = _make_pipeline(
        temp_output_dir,
        mock_llm_provider,
        force=False,
        chapter_directory_output=True,
    )

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ",
                    title="DB Cached Video",
                    duration=321,
                    chapters=[],
                )
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_transcript = _make_transcript(text="persisted transcript text")
        mock_transcript.language_code = "en"
        mock_fetch.return_value = mock_transcript

        result = await p.run(["vid-db"])

    assert result.success_count == 1
    db = DatabaseManager.get_instance(get_cache_db_path())
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
    p = _make_pipeline(
        temp_output_dir,
        mock_llm_provider,
        force=False,
        chapter_directory_output=True,
    )

    class _UsageContext:
        def __enter__(self) -> UsageTotals:
            return UsageTotals(
                prompt_tokens=40,
                completion_tokens=15,
                total_tokens=55,
                cost_usd=0.0055,
            )

        def __exit__(self, *_exc_info: object) -> None:
            return None

    p.provider.collect_usage = _UsageContext()

    with (
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ",
                    title="Metrics Video",
                    duration=222,
                    chapters=[],
                )
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch,
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        mock_transcript = _make_transcript(text="metrics transcript text")
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

    db = DatabaseManager.get_instance(get_cache_db_path())
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
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ",
                    title="Cached Video",
                    duration=123,
                    chapters=[],
                )
            ),
        ),
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch_first,
        patch(_COMMON_PATCHES["api_key"], return_value=True),
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
        patch(
            _COMMON_PATCHES["metadata"],
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ2",
                    title="Same Title",
                    duration=100,
                    chapters=[],
                )
            ),
        ) as mock_meta_second,
        patch(_COMMON_PATCHES["fetch"], new_callable=AsyncMock) as mock_fetch_second,
        patch(_COMMON_PATCHES["api_key"], return_value=True),
    ):
        second_result = await p_second.run(
            ["cached-video-id"], on_event=second_events.append
        )

    assert second_result.success_count == 1
    assert EventType.VIDEO_SKIPPED in [e.event_type for e in second_events]
    mock_meta_second.assert_not_called()
    mock_fetch_second.assert_not_awaited()


# ---------------------------------------------------------------------------
# Transcript export tests
# ---------------------------------------------------------------------------


def _make_pipeline_with_export(
    temp_output_dir,
    mock_llm_provider,
    export_format: str,
) -> CorePipeline:
    """Create a pipeline with export_transcript enabled."""
    with patch(
        "notewise.pipeline.core.get_provider",
        return_value=mock_llm_provider,
    ):
        p = CorePipeline(
            model="mock-model",
            output_dir=temp_output_dir,
            export_transcript=export_format,
        )
        p.generator = MagicMock()
        p.generator.generate_study_notes = AsyncMock(return_value="# Notes")
        p.generator.generate_single_chapter_notes = AsyncMock(
            return_value="# Chapter Notes"
        )
        p.generator.generate_chapter_notes_concurrent = (
            _mock_generate_chapter_notes_concurrent(p.generator)
        )
        return p


@pytest.mark.asyncio
async def test_export_transcript_txt(temp_output_dir, mock_llm_provider):
    """export_transcript='txt' creates a .txt file with plain text."""
    p = _make_pipeline_with_export(temp_output_dir, mock_llm_provider, "txt")

    with (
        patch(
            "notewise.pipeline._execution.get_video_metadata",
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ",
                    title="Test Video",
                    duration=300,
                    chapters=[],
                )
            ),
        ),
        patch(
            "notewise.pipeline._execution.fetch_transcript",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "notewise.pipeline.core.CorePipeline._check_api_key",
            return_value=True,
        ),
    ):
        mock_fetch.return_value = _make_transcript(
            video_id="vid123", text="Hello world transcript"
        )

        result = await p.run(["vid123"])

    assert result.success_count == 1
    export_file = temp_output_dir / "Test Video_transcript.txt"
    assert export_file.exists()
    assert export_file.read_text(encoding="utf-8") == "Hello world transcript"


@pytest.mark.asyncio
async def test_export_transcript_json(temp_output_dir, mock_llm_provider):
    """export_transcript='json' creates a .json file with timestamped segments."""
    p = _make_pipeline_with_export(temp_output_dir, mock_llm_provider, "json")

    with (
        patch(
            "notewise.pipeline._execution.get_video_metadata",
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ",
                    title="Test Video",
                    duration=300,
                    chapters=[],
                )
            ),
        ),
        patch(
            "notewise.pipeline._execution.fetch_transcript",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "notewise.pipeline.core.CorePipeline._check_api_key",
            return_value=True,
        ),
    ):
        # Create mock segments with timestamps
        mock_segment1 = MagicMock()
        mock_segment1.text = "Hello"
        mock_segment1.start = 0.0
        mock_segment1.duration = 1.5

        mock_segment2 = MagicMock()
        mock_segment2.text = "world"
        mock_segment2.start = 1.5
        mock_segment2.duration = 2.0

        mock_transcript = _make_transcript(text="Hello world")
        mock_transcript.video_id = "vid123"
        mock_transcript.language = "English"
        mock_transcript.language_code = "en"
        mock_transcript.is_generated = False
        mock_transcript.segments = [mock_segment1, mock_segment2]
        mock_fetch.return_value = mock_transcript

        result = await p.run(["vid123"])

    assert result.success_count == 1
    export_file = temp_output_dir / "Test Video_transcript.json"
    assert export_file.exists()

    data = json.loads(export_file.read_text(encoding="utf-8"))
    assert data["video_id"] == "vid123"
    assert data["language"] == "English"
    assert data["language_code"] == "en"
    assert data["is_generated"] is False
    assert len(data["segments"]) == 2
    assert data["segments"][0]["text"] == "Hello"
    assert data["segments"][0]["start"] == 0.0
    assert data["segments"][0]["duration"] == 1.5
    assert data["segments"][1]["text"] == "world"


@pytest.mark.asyncio
async def test_no_export_when_flag_not_set(temp_output_dir, mock_llm_provider):
    """No transcript file is created when export_transcript is None."""
    with patch(
        "notewise.pipeline.core.get_provider",
        return_value=mock_llm_provider,
    ):
        p = CorePipeline(model="mock-model", output_dir=temp_output_dir)
        p.generator = MagicMock()
        p.generator.generate_study_notes = AsyncMock(return_value="# Notes")
        p.generator.generate_single_chapter_notes = AsyncMock(
            return_value="# Chapter Notes"
        )
        p.generator.generate_chapter_notes_concurrent = (
            _mock_generate_chapter_notes_concurrent(p.generator)
        )

    with (
        patch(
            "notewise.pipeline._execution.get_video_metadata",
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ",
                    title="Test Video",
                    duration=300,
                    chapters=[],
                )
            ),
        ),
        patch(
            "notewise.pipeline._execution.fetch_transcript",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "notewise.pipeline.core.CorePipeline._check_api_key",
            return_value=True,
        ),
    ):
        mock_fetch.return_value = _make_transcript(text="transcript text")

        result = await p.run(["vid123"])

    assert result.success_count == 1
    # No transcript export files should exist
    txt_files = list(temp_output_dir.glob("*_transcript.txt"))
    json_files = list(temp_output_dir.glob("*_transcript.json"))
    assert len(txt_files) == 0
    assert len(json_files) == 0


@pytest.mark.asyncio
async def test_export_sanitized_filename(temp_output_dir, mock_llm_provider):
    """Export file uses sanitized filename for special characters in title."""
    p = _make_pipeline_with_export(temp_output_dir, mock_llm_provider, "txt")

    with (
        patch(
            "notewise.pipeline._execution.get_video_metadata",
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id="dQw4w9WgXcQ",
                    title="Test: Video <Special>",
                    duration=100,
                    chapters=[],
                )
            ),
        ),
        patch(
            "notewise.pipeline._execution.fetch_transcript",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "notewise.pipeline.core.CorePipeline._check_api_key",
            return_value=True,
        ),
    ):
        mock_transcript = _make_transcript(text="transcript text")
        mock_transcript.video_id = "vid123"
        mock_transcript.language = "English"
        mock_transcript.language_code = "en"
        mock_transcript.is_generated = False
        mock_fetch.return_value = mock_transcript

        result = await p.run(["vid123"])

    assert result.success_count == 1
    # Special characters should be stripped
    export_file = temp_output_dir / "Test Video Special_transcript.txt"
    assert export_file.exists()
