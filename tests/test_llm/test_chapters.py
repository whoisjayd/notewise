"""Tests for synthetic chapter engine."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from yt_study.llm.chapters import SyntheticChapterEngine
from yt_study.youtube.transcript import TranscriptSegment, VideoTranscript


class TestSyntheticChapterEngine:
    """Test synthetic chapter generation and parsing."""

    @pytest.fixture
    def mock_provider(self):
        return MagicMock()

    @pytest.fixture
    def engine(self, mock_provider):
        return SyntheticChapterEngine(mock_provider)

    @pytest.fixture
    def transcript(self):
        segments = [
            TranscriptSegment(text="Hello world", start=0, duration=5),
            TranscriptSegment(text="Second part", start=60, duration=5),
        ]
        return VideoTranscript(
            video_id="vid123",
            segments=segments,
            language="English",
            language_code="en",
            is_generated=False,
        )

    @pytest.mark.asyncio
    async def test_generate_chapters_success(self, engine, mock_provider, transcript):
        """Test successful chapter generation and parsing."""
        mock_response = json.dumps([
            {"timestamp": "00:00", "title": "Intro"},
            {"timestamp": "01:00", "title": "Main Topic"}
        ])
        mock_provider.generate = AsyncMock(return_value=mock_response)

        chapters = await engine.generate_chapters(transcript)

        assert len(chapters) == 2
        assert chapters[0].title == "Intro"
        assert chapters[0].start_seconds == 0
        assert chapters[0].end_seconds == 60
        assert chapters[1].title == "Main Topic"
        assert chapters[1].start_seconds == 60
        assert chapters[1].end_seconds is None

    @pytest.mark.asyncio
    async def test_generate_chapters_with_markdown(self, engine, mock_provider, transcript):
        """Test parsing when LLM wraps JSON in markdown blocks."""
        mock_response = "Here is the JSON:\n```json\n[\n  {\"timestamp\": \"00:00\", \"title\": \"Intro\"}\n]\n```"
        mock_provider.generate = AsyncMock(return_value=mock_response)

        chapters = await engine.generate_chapters(transcript)

        assert len(chapters) == 1
        assert chapters[0].title == "Intro"
        assert chapters[0].start_seconds == 0

    @pytest.mark.asyncio
    async def test_generate_chapters_missing_start(self, engine, mock_provider, transcript):
        """Test that an 'Introduction' is added if first chapter doesn't start at 0."""
        mock_response = json.dumps([
            {"timestamp": "02:00", "title": "Late Start"}
        ])
        mock_provider.generate = AsyncMock(return_value=mock_response)

        chapters = await engine.generate_chapters(transcript)

        assert len(chapters) == 2
        assert chapters[0].title == "Introduction"
        assert chapters[0].start_seconds == 0
        assert chapters[1].title == "Late Start"
        assert chapters[1].start_seconds == 120

    @pytest.mark.asyncio
    async def test_generate_chapters_failure(self, engine, mock_provider, transcript):
        """Test handling of invalid LLM output."""
        mock_provider.generate = AsyncMock(return_value="Not JSON")

        chapters = await engine.generate_chapters(transcript)

        assert chapters == []
