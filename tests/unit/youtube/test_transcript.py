"""Tests for transcript fetching and processing."""

from unittest.mock import AsyncMock

import pytest

from notewise.errors import ExtractionError as ExtractorError
from notewise.errors import (
    IPBlockError as YouTubeIPBlockError,
)
from notewise.errors import (
    TranscriptUnavailableError as TranscriptError,
)
from notewise.errors import VideoUnavailableError as PublicAccessRequiredError
from notewise.errors import (
    raise_if_video_unavailable as _raise_if_public_access_required,
)
from notewise.youtube.metadata import VideoChapter
from notewise.youtube.transcript import (
    TranscriptSegment,
    VideoTranscript,
    _extract_error_reason,
    _fetch_async,
    fetch_transcript,
    split_transcript_by_chapters,
)


class TestTranscriptHelpers:
    """Helper-level coverage for transcript utilities."""

    def test_video_transcript_to_text_joins_segment_text(self):
        """VideoTranscript.to_text should join segment text with spaces."""
        transcript = VideoTranscript(
            video_id="vid",
            segments=[
                TranscriptSegment(text="Hello", start=0.0, duration=1.0),
                TranscriptSegment(text="world", start=1.0, duration=1.0),
            ],
            language="English",
            language_code="en",
            is_generated=False,
        )

        assert transcript.to_text() == "Hello world"

    @pytest.mark.parametrize(
        ("error", "expected_message"),
        [
            (
                Exception("This video is members only"),
                "cookie-file",
            ),
            (
                Exception("This video is age restricted"),
                "cookie-file",
            ),
            (
                Exception("Please sign in to continue"),
                "cookie-file",
            ),
        ],
    )
    def test_raise_if_public_access_required_detects_restricted_access(
        self,
        error,
        expected_message,
    ):
        """Known sign-in-only restrictions should map to one clean user error."""
        with pytest.raises(PublicAccessRequiredError, match=expected_message):
            _raise_if_public_access_required(str(error))

    def test_raise_if_public_access_required_ignores_public_errors(self):
        """Non-access errors should be left untouched for normal handling."""
        _raise_if_public_access_required(str(Exception("captions missing")))

    def test_extract_error_reason_prefers_message_and_fallback(self):
        assert _extract_error_reason(Exception("boom")) == "boom"
        assert _extract_error_reason(Exception("   ")) == "video is unavailable"


class TestFetchTranscript:
    """Test fetch_transcript function."""

    @pytest.mark.asyncio
    async def test_fetch_transcript_success(self, mock_extractor_client):
        """Successful native transcript payload should map to VideoTranscript."""
        client = mock_extractor_client["transcript"].return_value
        client.transcript.return_value = {
            "language_code": "en",
            "is_generated": False,
            "track": {"name": "English"},
            "segments": [
                {"text": "Hello", "start": 0.0, "duration": 1.0},
                {"text": "World", "start": 1.0, "duration": 1.0},
            ],
        }

        result = await fetch_transcript("video123", ["en"])

        assert isinstance(result, VideoTranscript)
        assert result.video_id == "video123"
        assert len(result.segments) == 2
        assert result.segments[0].text == "Hello"
        assert result.language == "English"
        assert not result.is_generated

    @pytest.mark.asyncio
    async def test_fetch_transcript_calls_on_request_callback(
        self, mock_extractor_client
    ):
        """on_request callback should be awaited before the network attempt."""
        client = mock_extractor_client["transcript"].return_value
        client.transcript.return_value = {
            "language_code": "en",
            "is_generated": False,
            "track": {"name": "English"},
            "segments": [{"text": "Hello", "start": 0.0, "duration": 1.0}],
        }

        on_request = AsyncMock()

        await fetch_transcript("video123", ["en"], on_request=on_request)

        on_request.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_transcript_private_video_fails_without_retry(
        self, mock_extractor_client
    ):
        """Private videos should surface a clean fatal error on first attempt."""
        client = mock_extractor_client["transcript"].return_value
        client.transcript.side_effect = ExtractorError("This video is private")

        with pytest.raises(
            PublicAccessRequiredError,
            match="cookie-file",
        ):
            await fetch_transcript("video123")

        assert client.transcript.call_count == 1

    @pytest.mark.asyncio
    async def test_fetch_transcript_retry_logic(self, mock_extractor_client):
        """Transient errors should be retried up to success."""
        client = mock_extractor_client["transcript"].return_value
        client.transcript.side_effect = [
            ExtractorError("Connection reset"),
            ExtractorError("Timeout"),
            {
                "language_code": "en",
                "is_generated": False,
                "track": {"name": "English"},
                "segments": [{"text": "ok", "start": 0.0, "duration": 0.1}],
            },
        ]

        result = await fetch_transcript("video123")
        assert isinstance(result, VideoTranscript)
        assert client.transcript.call_count == 3
        mock_extractor_client["transcript"].assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_transcript_ip_block(self, mock_extractor_client):
        """IP block messages should map to YouTubeIPBlockError."""
        client = mock_extractor_client["transcript"].return_value
        client.transcript.side_effect = ExtractorError(
            "YouTube is blocking requests from your IP"
        )

        with pytest.raises(YouTubeIPBlockError):
            await fetch_transcript("video123")

    @pytest.mark.asyncio
    async def test_fetch_transcript_handles_object_style_segments(
        self, mock_extractor_client
    ):
        """Object-like segment items should be normalized via attribute access."""
        client = mock_extractor_client["transcript"].return_value

        class Segment:
            text = "obj"
            start = 1.25
            duration = 2.0

        client.transcript.return_value = {
            "language_code": "en",
            "is_generated": False,
            "track": {"name": "English"},
            "segments": [Segment()],
        }

        result = await fetch_transcript("video123")

        assert result.segments[0].text == "obj"
        assert result.segments[0].start == 1.25

    @pytest.mark.asyncio
    async def test_fetch_transcript_raises_transcript_error_after_retries(
        self, mock_extractor_client, monkeypatch
    ):
        """Unknown repeated failures should end as TranscriptError."""
        client = mock_extractor_client["transcript"].return_value
        client.transcript.side_effect = ExtractorError("network down")
        monkeypatch.setattr("notewise.youtube.transcript.asyncio.sleep", AsyncMock())

        with pytest.raises(TranscriptError, match="Could not fetch transcript"):
            await fetch_transcript("video123")

        assert client.transcript.call_count == 3

    @pytest.mark.asyncio
    async def test_fetch_async_wraps_not_found(self, mock_extractor_client):
        """No-track native errors should map to TranscriptError."""
        client = mock_extractor_client["transcript"].return_value
        client.transcript.side_effect = ExtractorError(
            "No transcript/subtitle track found"
        )

        with pytest.raises(TranscriptError, match="No usable transcript found"):
            await _fetch_async(client, "video123", ["en"])

    @pytest.mark.asyncio
    async def test_fetch_async_success_with_unknown_track_name(
        self, mock_extractor_client
    ):
        client = mock_extractor_client["transcript"].return_value
        client.transcript.return_value = {
            "segments": [{"text": "ok", "start": 0.0, "duration": 1.0}],
            "language_code": "en",
            "track": {},
            "is_generated": True,
        }

        raw, meta, message = await _fetch_async(client, "video123", ["en"])

        assert raw[0]["text"] == "ok"
        assert meta.language == "en"
        assert meta.is_generated is True
        assert "Using native transcript" in message


class TestSplitTranscriptByChapters:
    """Tests for chapter transcript splitting."""

    def test_split_transcript_by_chapters_success(self):
        """Segments should be grouped into their chapter windows."""
        transcript = VideoTranscript(
            video_id="vid",
            segments=[
                TranscriptSegment("Intro text", 10.0, 5.0),
                TranscriptSegment("Middle text", 70.0, 5.0),
            ],
            language="English",
            language_code="en",
            is_generated=False,
        )
        chapters = [
            VideoChapter(title="Intro", start_seconds=0, end_seconds=60),
            VideoChapter(title="Middle", start_seconds=60, end_seconds=120),
        ]

        chapter_map = split_transcript_by_chapters(transcript, chapters)

        assert chapter_map["Intro"] == "Intro text"
        assert chapter_map["Middle"] == "Middle text"

    def test_split_transcript_by_chapters_handles_duplicate_titles(self):
        """Duplicate chapter titles should be disambiguated."""
        transcript = VideoTranscript(
            video_id="vid",
            segments=[
                TranscriptSegment("One", 10.0, 5.0),
                TranscriptSegment("Two", 70.0, 5.0),
            ],
            language="English",
            language_code="en",
            is_generated=False,
        )
        chapters = [
            VideoChapter(title="Part", start_seconds=0, end_seconds=60),
            VideoChapter(title="Part", start_seconds=60, end_seconds=120),
        ]

        chapter_map = split_transcript_by_chapters(transcript, chapters)

        assert chapter_map["Part"] == "One"
        assert chapter_map["Part (2)"] == "Two"

    def test_split_transcript_by_chapters_skips_empty_windows(self):
        transcript = VideoTranscript(
            video_id="vid",
            segments=[TranscriptSegment("late", 300.0, 10.0)],
            language="English",
            language_code="en",
            is_generated=False,
        )
        chapters = [VideoChapter(title="Intro", start_seconds=0, end_seconds=60)]

        chapter_map = split_transcript_by_chapters(transcript, chapters)

        assert chapter_map == {}

    def test_split_transcript_by_chapters_open_ended_chapter_uses_overlap(self):
        transcript = VideoTranscript(
            video_id="vid",
            segments=[TranscriptSegment("tail", 61.0, 2.0)],
            language="English",
            language_code="en",
            is_generated=False,
        )
        chapters = [VideoChapter(title="Last", start_seconds=60, end_seconds=None)]

        chapter_map = split_transcript_by_chapters(transcript, chapters)

        assert chapter_map["Last"] == "tail"
