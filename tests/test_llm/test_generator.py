"""Tests for study material generator."""

from unittest.mock import patch

import pytest

from yt_study.config import config
from yt_study.llm.generator import StudyMaterialGenerator


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
        orig_size = config.chunk_size
        config.chunk_size = 5  # Allow room for a sentence + delimiter

        try:
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
        finally:
            config.chunk_size = orig_size

    def test_chunk_transcript_newlines(self, generator):
        """Test splitting by newlines when sentences fail."""
        orig_size = config.chunk_size
        config.chunk_size = 2

        try:
            with patch("yt_study.llm.generator.token_counter") as mock_tc:
                mock_tc.side_effect = lambda _model, text: len(text.split())  # noqa: ARG005

                # No periods, just newlines
                text = "Line one\nLine two\nLine three"
                chunks = generator._chunk_transcript(text)

                assert len(chunks) > 1
                assert "Line one" in chunks[0]
        finally:
            config.chunk_size = orig_size

    def test_chunk_transcript_hard_split(self, generator):
        """Test hard splitting when no delimiters exist."""
        orig_size = config.chunk_size
        config.chunk_size = 1  # Tiny

        try:
            with patch("yt_study.llm.generator.token_counter") as mock_tc:
                # Mock token counter to say everything is too big
                mock_tc.side_effect = lambda _model, text: len(text)  # noqa: ARG005

                # A single massive word without spaces/newlines
                text = "A" * 100

                chunks = generator._chunk_transcript(text)

                # Should be split by character limit logic
                assert len(chunks) > 1
                assert len(chunks[0]) > 0
        finally:
            config.chunk_size = orig_size

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

    @pytest.mark.asyncio
    async def test_generate_chapter_notes(self, generator):
        """Test generating chapter-based notes."""
        chapters = {"Intro": "Intro text", "Body": "Body text"}

        await generator.generate_chapter_based_notes(chapters)

        # Calls: 1 per chapter (2) + 1 combine = 3
        assert generator.provider.generate.call_count == 3
