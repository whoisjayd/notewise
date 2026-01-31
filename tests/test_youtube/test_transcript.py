"""Tests for transcript fetching and processing."""

from unittest.mock import MagicMock

import pytest
from youtube_transcript_api._errors import NoTranscriptFound, VideoUnavailable

from yt_study.youtube.metadata import VideoChapter
from yt_study.youtube.transcript import (
    TranscriptError,
    VideoTranscript,
    fetch_transcript,
    split_transcript_by_chapters,
)


class TestFetchTranscript:
    """Test fetch_transcript function."""

    @pytest.fixture
    def mock_transcript_api_instance(self, mocker):
        """Mock the YouTubeTranscriptApi class and its instance."""
        # Patch the class
        mock_cls = mocker.patch("yt_study.youtube.transcript.YouTubeTranscriptApi")
        # The instance returned by constructor
        mock_instance = mock_cls.return_value
        return mock_instance

    @pytest.mark.asyncio
    async def test_fetch_transcript_success_manual(self, mock_transcript_api_instance):
        """Test successful fetch of manual transcript."""
        # Setup mock for instance method .list()
        mock_list = MagicMock()
        mock_transcript_api_instance.list.return_value = mock_list

        mock_transcript_obj = MagicMock()
        mock_transcript_obj.language = "English"
        mock_transcript_obj.language_code = "en"
        mock_transcript_obj.is_generated = False
        mock_transcript_obj.fetch.return_value = [
            {"text": "Hello", "start": 0.0, "duration": 1.0},
            {"text": "World", "start": 1.0, "duration": 1.0},
        ]

        mock_list.find_manually_created_transcript.return_value = mock_transcript_obj

        # Execute
        result = await fetch_transcript("video123", ["en"])

        # Verify
        assert isinstance(result, VideoTranscript)
        assert result.video_id == "video123"
        assert len(result.segments) == 2
        assert result.segments[0].text == "Hello"
        assert result.language == "English"
        assert not result.is_generated

        # Verify instance call
        mock_transcript_api_instance.list.assert_called_once_with("video123")

    @pytest.mark.asyncio
    async def test_fetch_transcript_fallback_auto(self, mock_transcript_api_instance):
        """Test fallback to auto-generated transcript."""
        mock_list = MagicMock()
        mock_transcript_api_instance.list.return_value = mock_list

        # Manual raises error
        mock_list.find_manually_created_transcript.side_effect = NoTranscriptFound(
            "id", [], []
        )

        # Auto succeeds
        mock_auto = MagicMock()
        mock_auto.language = "English (Auto)"
        mock_auto.language_code = "en"
        mock_auto.is_generated = True
        mock_auto.fetch.return_value = [{"text": "Hi", "start": 0.0, "duration": 1.0}]

        mock_list.find_generated_transcript.return_value = mock_auto

        result = await fetch_transcript("video123")
        assert result.is_generated is True
        assert result.segments[0].text == "Hi"

    @pytest.mark.asyncio
    async def test_fetch_transcript_fallback_translation(
        self, mock_transcript_api_instance
    ):
        """Test fallback to translation."""
        mock_list = MagicMock()
        mock_transcript_api_instance.list.return_value = mock_list

        # All finds fail
        mock_list.find_manually_created_transcript.side_effect = NoTranscriptFound(
            "id", [], []
        )
        mock_list.find_generated_transcript.side_effect = NoTranscriptFound(
            "id", [], []
        )

        # Iterator returns foreign transcript
        mock_foreign = MagicMock()
        mock_foreign.language_code = "fr"
        mock_foreign.is_translatable = True

        mock_translated = MagicMock()
        mock_translated.language = "English"
        mock_translated.language_code = "en"
        mock_translated.is_generated = False
        mock_translated.fetch.return_value = [
            {"text": "Hello", "start": 0.0, "duration": 1.0}
        ]

        mock_foreign.translate.return_value = mock_translated

        # Mock __iter__ to return list
        mock_list.__iter__.return_value = [mock_foreign]

        result = await fetch_transcript("video123", ["en"])

        mock_foreign.translate.assert_called_with("en")
        assert result.segments[0].text == "Hello"

    @pytest.mark.asyncio
    async def test_fetch_transcript_unavailable(self, mock_transcript_api_instance):
        """Test fatal error when video is unavailable."""
        # Mock the instance method to raise error
        mock_transcript_api_instance.list.side_effect = VideoUnavailable("video123")

        with pytest.raises(TranscriptError, match="video is unavailable"):
            await fetch_transcript("video123")

    @pytest.mark.asyncio
    async def test_fetch_transcript_retry_logic(self, mock_transcript_api_instance):
        """Test retry logic on transient errors."""
        # Setup Success Mock
        mock_list = MagicMock()
        mock_t = MagicMock()
        mock_t.fetch.return_value = []
        mock_t.language = "en"
        mock_t.language_code = "en"
        mock_t.is_generated = False

        mock_list.find_manually_created_transcript.return_value = mock_t

        # Configure side effect for list()
        mock_transcript_api_instance.list.side_effect = [
            Exception("Connection reset"),
            Exception("Timeout"),
            mock_list,
        ]

        result = await fetch_transcript("video123")
        assert isinstance(result, VideoTranscript)
        # Check call count
        assert mock_transcript_api_instance.list.call_count == 3


class TestSplitTranscript:
    """Test splitting transcript by chapters."""

    def test_split_transcript_simple(self):
        """Test basic split logic."""
        # Create mock transcript
        # 0-60s, 60-120s
        segments = [
            MagicMock(text="Part 1", start=10, duration=10),
            MagicMock(text="Part 1 End", start=50, duration=5),
            MagicMock(text="Part 2", start=70, duration=10),
            MagicMock(text="Part 2 End", start=110, duration=5),
        ]

        transcript = VideoTranscript(
            video_id="id",
            segments=segments,
            language="en",
            language_code="en",
            is_generated=False,
        )

        chapters = [
            VideoChapter(title="Chapter 1", start_seconds=0, end_seconds=60),
            VideoChapter(title="Chapter 2", start_seconds=60, end_seconds=None),
        ]

        result = split_transcript_by_chapters(transcript, chapters)

        assert len(result) == 2
        assert "Part 1" in result["Chapter 1"]
        assert "Part 1 End" in result["Chapter 1"]
        assert "Part 2" not in result["Chapter 1"]

        assert "Part 2" in result["Chapter 2"]
        assert "Part 2 End" in result["Chapter 2"]
