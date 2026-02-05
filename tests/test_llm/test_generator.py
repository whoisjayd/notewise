"""Tests for study material generator."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yt_study.config import config
from yt_study.llm.generator import StudyMaterialGenerator
from yt_study.youtube.metadata import VideoChapter
from yt_study.youtube.transcript import TranscriptSegment, VideoTranscript


class TestStudyMaterialGenerator:
    """Test generation logic including chunking."""

    @pytest.fixture
    def generator(self, mock_llm_provider):
        return StudyMaterialGenerator(mock_llm_provider)

    def test_count_tokens_fallback(self, generator):
        """Test token counting fallback when library fails."""
        with patch(
            "yt_study.llm.generator.token_counter", side_effect=Exception("Error")
        ):
            count = generator._count_tokens("1234")
            assert count == 1  # 4 chars // 4 = 1

    def test_chunk_transcript_small(self, generator):
        """Test that small transcripts are not chunked."""
        with patch("yt_study.llm.generator.token_counter", return_value=100):
            chunks = generator._chunk_transcript("Small text")
            assert len(chunks) == 1
            assert chunks[0] == "Small text"

    def test_chunk_transcript_sentences(self, generator):
        """Test splitting by sentences."""
        generator.chunk_size = 5  # Allow room for a sentence + delimiter

        with patch("yt_study.llm.generator.token_counter") as mock_tc:
            # 1 token per word, with the delimiter ". " adding extra tokens
            def count_tokens(_model, text):  # noqa: ARG001
                return len(text.split())

            mock_tc.side_effect = count_tokens

            text = "Sentence one. Sentence two. Sentence three."
            chunks = generator._chunk_transcript(text)

            # Should split because total > 5 tokens
            assert len(chunks) > 1
            # Verify that splitting happened and first chunk contains content
            assert len(chunks[0]) > 0
            assert "Sentence" in chunks[0]

    def test_chunk_transcript_newlines(self, generator):
        """Test splitting by newlines when sentences fail."""
        generator.chunk_size = 2

        with patch("yt_study.llm.generator.token_counter") as mock_tc:
            mock_tc.side_effect = lambda _model, text: len(text.split())  # noqa: ARG005

            # No periods, just newlines
            text = "Line one\nLine two\nLine three"
            chunks = generator._chunk_transcript(text)

            assert len(chunks) > 1
            assert "Line one" in chunks[0]

    def test_chunk_transcript_hard_split(self, generator):
        """Test hard splitting when no delimiters exist."""
        generator.chunk_size = 1  # Tiny

        with patch("yt_study.llm.generator.token_counter") as mock_tc:
            # Mock token counter to say everything is too big
            mock_tc.side_effect = lambda _model, text: len(text)  # noqa: ARG005

            # A single massive word without spaces/newlines
            text = "A" * 100

            chunks = generator._chunk_transcript(text)

            # Should be split by character limit logic
            assert len(chunks) > 1
            assert len(chunks[0]) > 0

    @pytest.mark.asyncio
    async def test_generate_study_notes_single(self, generator):
        """Test generating notes for a single chunk."""
        with patch.object(generator, "_chunk_transcript", return_value=["Full text"]):
            notes = await generator.generate_study_notes("Full text")

            assert notes == "# Generated Notes\n\nTest content."
            assert generator.provider.generate.call_count == 1

    @pytest.mark.asyncio
    async def test_generate_study_notes_multiple(self, generator):
        """Test generating and combining multiple chunks."""
        chunks = ["Part 1", "Part 2"]
        with patch.object(generator, "_chunk_transcript", return_value=chunks):
            notes = await generator.generate_study_notes("Long text")

            assert notes == "# Generated Notes\n\nTest content."
            # 2 chunks + 1 combine = 3 calls
            assert generator.provider.generate.call_count == 3

    def test_post_process_timestamps(self, generator):
        """Test that [MM:SS] timestamps are converted to YouTube links."""
        text = "Check this point [01:23] and another [12:34:56]."
        video_id = "abc123"
        processed = generator._post_process_timestamps(text, video_id)

        assert "[01:23](https://youtu.be/abc123?t=83)" in processed
        assert "[12:34:56](https://youtu.be/abc123?t=45296)" in processed

    def test_chunk_transcript_chapter_aware(self, generator):
        """Test that chunking respects chapter boundaries."""
        segments = [
            TranscriptSegment(text="Intro", start=0, duration=10),
            TranscriptSegment(text="Middle", start=100, duration=10),
            TranscriptSegment(text="Outro", start=200, duration=10),
        ]
        transcript_obj = VideoTranscript(
            video_id="vid123",
            segments=segments,
            language="English",
            language_code="en",
            is_generated=False,
        )
        chapters = [
            VideoChapter(title="Chapter 1", start_seconds=0, end_seconds=50),
            VideoChapter(title="Chapter 2", start_seconds=50, end_seconds=150),
            VideoChapter(title="Chapter 3", start_seconds=150, end_seconds=300),
        ]

        with patch("yt_study.llm.generator.token_counter", return_value=10):
            chunks = generator._chunk_transcript(
                transcript_obj.to_text(),
                chapters=chapters,
                transcript_obj=transcript_obj
            )

            # Should have 3 chunks, one for each chapter
            assert len(chunks) == 3
            assert "Intro" in chunks[0]
            assert "Middle" in chunks[1]
            assert "Outro" in chunks[2]
