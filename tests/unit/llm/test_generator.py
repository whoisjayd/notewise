"""Tests for study material generator."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from notewise.config import settings as config
from notewise.llm.prompts.study_notes import get_combine_prompt, get_stitch_prompt
from notewise.pipeline.generation import (
    StudyMaterialGenerator,
    _normalize_stitched_document,
    _split_head_for_stitching,
    _split_tail_for_stitching,
)


class TestStudyMaterialGenerator:
    """Test generation logic including chunking."""

    @pytest.fixture
    def generator(self, mock_llm_provider):
        return StudyMaterialGenerator(mock_llm_provider)

    def test_count_tokens_fallback(self, generator):
        """Test token counting fallback when library fails."""
        with patch(
            "notewise.pipeline.generation.token_counter", side_effect=Exception("Error")
        ):
            count = generator._count_tokens("1234")
            assert count == 1  # 4 chars // 4 = 1

    def test_count_tokens_public_api(self, generator):
        """Public count_tokens API should use model token counter."""
        with patch("notewise.pipeline.generation.token_counter", return_value=123):
            assert generator.count_tokens("sample text") == 123

    def test_chunk_transcript_small(self, generator):
        """Test that small transcripts are not chunked."""
        with patch("notewise.pipeline.generation.token_counter", return_value=100):
            chunks = generator._chunk_transcript("Small text")
            assert len(chunks) == 1
            assert chunks[0] == "Small text"

    def test_chunk_transcript_sentences(self, generator):
        """Test splitting by sentences."""
        orig_size = config.chunk_size
        config.chunk_size = 5  # Allow room for a sentence + delimiter

        try:
            with patch("notewise.pipeline.generation.token_counter") as mock_tc:
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

    def test_chunk_transcript_preserves_sentence_punctuation(self, generator):
        """Sentence splitting should keep punctuation attached to each sentence."""
        orig_size = config.chunk_size
        config.chunk_size = 3

        try:
            with patch("notewise.pipeline.generation.token_counter") as mock_tc:
                mock_tc.side_effect = lambda _model, text: len(text.split())  # noqa: ARG005

                text = "Sentence one. Sentence two. Sentence three."
                chunks = generator._chunk_transcript(text)

                assert len(chunks) > 1
                assert all(chunk.endswith(".") for chunk in chunks)
        finally:
            config.chunk_size = orig_size

    def test_chunk_transcript_newlines(self, generator):
        """Test splitting by newlines when sentences fail."""
        orig_size = config.chunk_size
        config.chunk_size = 2

        try:
            with patch("notewise.pipeline.generation.token_counter") as mock_tc:
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
            with patch("notewise.pipeline.generation.token_counter") as mock_tc:
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
    async def test_generate_study_notes_on_chunk_callback(self, generator):
        """Ensure on_chunk is invoked with (i, total) for each chunk."""
        chunks = ["chunk1", "chunk2", "chunk3"]

        # Force the generator to produce exactly three chunks
        with patch.object(generator, "_chunk_transcript", return_value=chunks):
            on_chunk = MagicMock()

            # Run the generation with the callback
            await generator.generate_study_notes(
                transcript="dummy transcript",
                on_chunk=on_chunk,
            )

        # Verify that on_chunk was called once per chunk with (i, total)
        calls = [c.args for c in on_chunk.call_args_list]
        assert calls == [(1, 3), (2, 3), (3, 3)]

    @pytest.mark.asyncio
    async def test_generate_study_notes_single(self, generator):
        """Test generating notes for a single chunk."""
        with patch.object(generator, "_chunk_transcript", return_value=["Full text"]):
            notes = await generator.generate_study_notes("Full text")

            assert notes == "# Generated Notes\n\nTest content."
            assert generator.provider.generate.call_count == 1

    @pytest.mark.asyncio
    async def test_generate_study_notes_single_uses_target_language_prompts(
        self, mock_llm_provider
    ):
        """Single-pass notes should enforce the requested output language."""
        generator = StudyMaterialGenerator(mock_llm_provider, target_language="Hindi")

        with patch.object(generator, "_chunk_transcript", return_value=["Full text"]):
            await generator.generate_study_notes("Full text")

        call_kwargs = generator.provider.generate.await_args.kwargs
        assert (
            "Always write the entire output in Hindi." in call_kwargs["system_prompt"]
        )
        assert "Write everything in Hindi." in call_kwargs["user_prompt"]

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
    async def test_generate_study_notes_throttle_waits_between_repeated_calls(
        self, mock_llm_provider
    ):
        """Throttle should pause between repeated chunk generation requests."""
        generator = StudyMaterialGenerator(mock_llm_provider, throttle_seconds=2.0)

        with (
            patch.object(generator, "_chunk_transcript", return_value=["A", "B"]),
            patch(
                "notewise.pipeline.generation.asyncio.sleep", new=AsyncMock()
            ) as mock_sleep,
        ):
            await generator.generate_study_notes("Long text")

        assert mock_sleep.await_count == 2
        assert all(
            call.args[0] == pytest.approx(2.0, abs=0.01)
            for call in mock_sleep.await_args_list
        )

    @pytest.mark.asyncio
    async def test_generate_study_notes_throttle_skips_initial_delay(
        self, mock_llm_provider
    ):
        """Throttle should not add a startup pause before the first LLM request."""
        generator = StudyMaterialGenerator(mock_llm_provider, throttle_seconds=1.5)

        with patch(
            "notewise.pipeline.generation.asyncio.sleep", new=AsyncMock()
        ) as mock_sleep:
            await generator.generate_study_notes("Full text")

        mock_sleep.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_generate_study_notes_multiple_uses_stitch_prompt_by_default(
        self, mock_llm_provider
    ):
        """Chunked study notes should stitch adjacent outputs by default."""
        generator = StudyMaterialGenerator(mock_llm_provider)
        generator.provider.generate = AsyncMock(
            side_effect=[
                "# Section One\n\nChunk one detail",
                "# Section One\n\nChunk two detail",
                "# Stitched\n\nMerged detail",
            ]
        )

        with patch.object(generator, "_chunk_transcript", return_value=["A", "B"]):
            result = await generator.generate_study_notes("Long text")

        assert result == "# Stitched\n\nMerged detail"
        final_prompt = generator.provider.generate.await_args_list[-1].kwargs[
            "user_prompt"
        ]
        assert final_prompt == get_stitch_prompt(
            "# Section One\n\nChunk one detail",
            "# Section One\n\nChunk two detail",
        )

    @pytest.mark.asyncio
    async def test_generate_study_notes_multiple_passes_target_language_to_stitch(
        self, mock_llm_provider
    ):
        """Chunk stitching should preserve the requested output language."""
        generator = StudyMaterialGenerator(mock_llm_provider, target_language="Spanish")
        generator.provider.generate = AsyncMock(
            side_effect=[
                "# Section One\n\nChunk one detail",
                "# Section One\n\nChunk two detail",
                "# Stitched\n\nMerged detail",
            ]
        )

        with patch.object(generator, "_chunk_transcript", return_value=["A", "B"]):
            await generator.generate_study_notes("Long text")

        final_call = generator.provider.generate.await_args_list[-1].kwargs
        assert (
            "Always write the entire output in Spanish." in final_call["system_prompt"]
        )
        assert final_call["user_prompt"] == get_stitch_prompt(
            "# Section One\n\nChunk one detail",
            "# Section One\n\nChunk two detail",
            target_language="Spanish",
        )

    @pytest.mark.asyncio
    async def test_generate_study_notes_multiple_uses_legacy_combine_when_enabled(
        self, mock_llm_provider
    ):
        """Legacy combine mode should bypass stitching when explicitly enabled."""
        generator = StudyMaterialGenerator(mock_llm_provider, use_combine_chunk=True)
        generator.provider.generate = AsyncMock(
            side_effect=[
                "# Section One\n\nChunk one detail",
                "# Section One\n\nChunk two detail",
                "# Combined\n\nMerged detail",
            ]
        )

        with patch.object(generator, "_chunk_transcript", return_value=["A", "B"]):
            result = await generator.generate_study_notes("Long text")

        assert result == "# Combined\n\nMerged detail"
        final_prompt = generator.provider.generate.await_args_list[-1].kwargs[
            "user_prompt"
        ]
        assert final_prompt == get_combine_prompt(
            [
                "# Section One\n\nChunk one detail",
                "# Section One\n\nChunk two detail",
            ]
        )

    @pytest.mark.asyncio
    async def test_generate_study_notes_on_combine_callback(self, generator):
        """Chunked note generation should signal when combine begins."""
        chunks = ["Part 1", "Part 2"]

        with patch.object(generator, "_chunk_transcript", return_value=chunks):
            on_combine = MagicMock()
            await generator.generate_study_notes(
                transcript="Long text",
                on_combine=on_combine,
            )

        on_combine.assert_called_once_with(2)

    @pytest.mark.asyncio
    async def test_generate_single_chapter_small(self, generator):
        """Single-pass path used when chapter fits within chunk_size."""
        with patch("notewise.pipeline.generation.token_counter", return_value=50):
            await generator.generate_single_chapter_notes("Intro", "short text")
        # One call only (no chunking needed)
        assert generator.provider.generate.call_count == 1

    @pytest.mark.asyncio
    async def test_generate_single_chapter_oversized(self, generator):
        """Chunked path used when chapter text exceeds chunk_size."""
        two_chunks = ["chunk A", "chunk B"]
        with (
            patch.object(generator, "_chunk_transcript", return_value=two_chunks),
            patch("notewise.pipeline.generation.token_counter", return_value=9999),
        ):
            await generator.generate_single_chapter_notes("Ch1", "very long text")
        # 2 chunk calls + 1 combine call = 3
        assert generator.provider.generate.call_count == 3

    @pytest.mark.asyncio
    async def test_generate_single_chapter_uses_stitch_prompt_by_default(
        self, mock_llm_provider
    ):
        """Chunked chapter notes should stitch adjacent outputs by default."""
        generator = StudyMaterialGenerator(mock_llm_provider)
        generator.provider.generate = AsyncMock(
            side_effect=[
                "### Topic\n\nChunk one detail",
                "### Topic\n\nChunk two detail",
                "### Topic\n\nMerged detail",
            ]
        )

        with (
            patch.object(generator, "_chunk_transcript", return_value=["A", "B"]),
            patch("notewise.pipeline.generation.token_counter", return_value=9999),
        ):
            result = await generator.generate_single_chapter_notes("Ch1", "very long")

        assert result == "### Topic\n\nMerged detail"
        final_prompt = generator.provider.generate.await_args_list[-1].kwargs[
            "user_prompt"
        ]
        assert final_prompt == get_stitch_prompt(
            "### Topic\n\nChunk one detail",
            "### Topic\n\nChunk two detail",
        )

    @pytest.mark.asyncio
    async def test_generate_single_chapter_uses_target_language_prompts(
        self, mock_llm_provider
    ):
        """Chapter generation should honor the requested output language."""
        generator = StudyMaterialGenerator(mock_llm_provider, target_language="German")

        with patch("notewise.pipeline.generation.token_counter", return_value=50):
            await generator.generate_single_chapter_notes("Intro", "short text")

        call_kwargs = generator.provider.generate.await_args.kwargs
        assert (
            "Always write the entire output in German." in call_kwargs["system_prompt"]
        )
        assert "Write everything in German." in call_kwargs["user_prompt"]

    @pytest.mark.asyncio
    async def test_stitch_chunk_notes_handles_three_chunks(self, mock_llm_provider):
        """Three-chunk stitching should preserve cumulative content across passes."""
        generator = StudyMaterialGenerator(mock_llm_provider)
        generator.provider.generate = AsyncMock(
            side_effect=[
                "## Topic One\n\nA\n\n## Topic Two\n\nB merged",
                (
                    "## Topic One\n\nA\n\n## Topic Two\n\nB merged\n\n"
                    "## Topic Three\n\nC merged\n\n## Topic Four: Chunk 3\n\nD"
                ),
            ]
        )

        result = await generator._stitch_chunk_notes(
            [
                "## Topic One\n\nA",
                "## Topic Two\n\nB",
                "## Topic Three\n\nC\n\n## Topic Four: Chunk 3\n\nD",
            ],
            system_prompt="system",
        )

        assert "## Topic One" in result
        assert "## Topic Four\n\nD" in result
        assert "Chunk 3" not in result
        assert generator.provider.generate.await_count == 2

    @pytest.mark.asyncio
    async def test_generate_single_chapter_callbacks(self, generator):
        """Chunked chapter generation should signal part and combine callbacks."""
        two_chunks = ["chunk A", "chunk B"]

        with (
            patch.object(generator, "_chunk_transcript", return_value=two_chunks),
            patch("notewise.pipeline.generation.token_counter", return_value=9999),
        ):
            on_chunk = MagicMock()
            on_combine = MagicMock()
            await generator.generate_single_chapter_notes(
                "Ch1",
                "very long text",
                on_chunk=on_chunk,
                on_combine=on_combine,
            )

        assert [call.args for call in on_chunk.call_args_list] == [(1, 2), (2, 2)]
        on_combine.assert_called_once_with(2)

    @pytest.mark.asyncio
    async def test_generate_single_chapter_oversized_single_chunk(self, generator):
        """When chunker returns exactly 1 chunk, no combine call is made."""
        with (
            patch.object(generator, "_chunk_transcript", return_value=["one chunk"]),
            patch("notewise.pipeline.generation.token_counter", return_value=9999),
        ):
            await generator.generate_single_chapter_notes("Ch1", "big text")
        # 1 chunk call only — combine is skipped when there is a single chunk
        assert generator.provider.generate.call_count == 1

    @pytest.mark.asyncio
    async def test_generate_chapter_notes_concurrent_preserves_input_order(
        self, generator
    ):
        """Concurrent chapter generation should return results in the original order."""

        async def _generate_single(chapter_title, chapter_text, **kwargs):  # noqa: ANN001
            del chapter_text, kwargs
            return f"notes for {chapter_title}"

        generator.generate_single_chapter_notes = AsyncMock(
            side_effect=_generate_single
        )

        result = await generator.generate_chapter_notes_concurrent(
            {"Intro": "intro text", "Body": "body text", "Wrap": "wrap text"},
            max_concurrent=2,
        )

        assert list(result.keys()) == ["Intro", "Body", "Wrap"]
        assert result["Intro"] == "notes for Intro"
        assert result["Wrap"] == "notes for Wrap"

    @pytest.mark.asyncio
    async def test_generate_chapter_notes_concurrent_respects_max_concurrency(
        self, generator
    ):
        """The semaphore should cap simultaneous chapter generations."""
        state = {"active": 0, "peak": 0}

        async def _generate_single(chapter_title, chapter_text, **kwargs):  # noqa: ANN001
            del chapter_title, chapter_text, kwargs
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            state["active"] -= 1
            return "# Chapter"

        generator.generate_single_chapter_notes = AsyncMock(
            side_effect=_generate_single
        )

        await generator.generate_chapter_notes_concurrent(
            {
                "Chapter 1": "text1",
                "Chapter 2": "text2",
                "Chapter 3": "text3",
            },
            max_concurrent=2,
        )

        assert state["peak"] <= 2

    @pytest.mark.asyncio
    async def test_generate_chapter_notes_concurrent_can_share_external_semaphore(
        self, generator
    ):
        """A shared semaphore should cap chapter work across concurrent runs."""
        state = {"active": 0, "peak": 0}

        async def _generate_single(chapter_title, chapter_text, **kwargs):  # noqa: ANN001
            del chapter_title, chapter_text, kwargs
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            state["active"] -= 1
            return "# Chapter"

        generator.generate_single_chapter_notes = AsyncMock(
            side_effect=_generate_single
        )
        shared_semaphore = asyncio.Semaphore(2)

        await asyncio.gather(
            generator.generate_chapter_notes_concurrent(
                {"Chapter 1": "text1", "Chapter 2": "text2", "Chapter 3": "text3"},
                max_concurrent=3,
                semaphore=shared_semaphore,
            ),
            generator.generate_chapter_notes_concurrent(
                {"Chapter 4": "text4", "Chapter 5": "text5"},
                max_concurrent=3,
                semaphore=shared_semaphore,
            ),
        )

        assert state["peak"] <= 2

    @pytest.mark.asyncio
    async def test_generate_chapter_notes_concurrent_throttle_serializes_requests(
        self, mock_llm_provider
    ):
        """Throttle should also pace chapter requests started concurrently."""
        generator = StudyMaterialGenerator(mock_llm_provider, throttle_seconds=2.0)

        with (
            patch("notewise.pipeline.generation.token_counter", return_value=50),
            patch(
                "notewise.pipeline.generation.asyncio.sleep", new=AsyncMock()
            ) as mock_sleep,
        ):
            await generator.generate_chapter_notes_concurrent(
                {
                    "Chapter 1": "text1",
                    "Chapter 2": "text2",
                    "Chapter 3": "text3",
                },
                max_concurrent=3,
            )

        assert mock_sleep.await_count == 2
        assert all(
            call.args[0] == pytest.approx(2.0, abs=0.01)
            for call in mock_sleep.await_args_list
        )

    @pytest.mark.asyncio
    async def test_generate_quiz_calls_provider_once(self, generator):
        """generate_quiz() delegates to the provider in a single call."""
        result = await generator.generate_quiz("full transcript text")
        assert generator.provider.generate.call_count == 1
        assert result == "# Generated Notes\n\nTest content."

    @pytest.mark.asyncio
    async def test_generate_quiz_chunked_large_transcript(self, generator):
        """generate_quiz() chunks a large transcript and combines partial quizzes."""
        chunks = ["chunk A", "chunk B"]
        with (
            patch.object(generator, "_chunk_transcript", return_value=chunks),
            patch("notewise.pipeline.generation.token_counter", return_value=9999),
        ):
            result = await generator.generate_quiz("very long transcript")

        # 2 chunk calls + 1 combine call = 3
        assert generator.provider.generate.call_count == 3
        assert result == "# Generated Notes\n\nTest content."

    @pytest.mark.asyncio
    async def test_generate_quiz_callbacks_for_chunked_quiz(self, generator):
        """Chunked quiz generation should signal part and combine callbacks."""
        chunks = ["chunk A", "chunk B"]

        with (
            patch.object(generator, "_chunk_transcript", return_value=chunks),
            patch("notewise.pipeline.generation.token_counter", return_value=9999),
        ):
            on_chunk = MagicMock()
            on_combine = MagicMock()
            await generator.generate_quiz(
                "very long transcript",
                on_chunk=on_chunk,
                on_combine=on_combine,
            )

        assert [call.args for call in on_chunk.call_args_list] == [(1, 2), (2, 2)]
        on_combine.assert_called_once_with(2)

    @pytest.mark.asyncio
    async def test_generate_quiz_chunked_single_chunk_no_combine(self, generator):
        """When the chunker returns exactly one chunk no combine call is made."""
        with (
            patch.object(generator, "_chunk_transcript", return_value=["one chunk"]),
            patch("notewise.pipeline.generation.token_counter", return_value=9999),
        ):
            result = await generator.generate_quiz("big transcript")

        # 1 chunk call only — combine is skipped
        assert generator.provider.generate.call_count == 1
        assert result == "# Generated Notes\n\nTest content."


def test_split_tail_for_stitching_limits_boundary_to_recent_sections():
    """Tail splitting should keep older sections outside the stitched boundary."""
    document = (
        "# Intro\n\nA\n\n## Topic One\n\nB\n\n## Topic Two\n\nC\n\n## Topic Three\n\nD"
    )

    prefix, tail = _split_tail_for_stitching(document)

    assert "# Intro" in prefix
    assert "## Topic One" not in tail
    assert "## Topic Two" in tail
    assert "## Topic Three" in tail


def test_split_head_for_stitching_limits_boundary_to_early_sections():
    """Head splitting should keep later sections outside the stitched boundary."""
    document = (
        "# Intro\n\nA\n\n## Topic One\n\nB\n\n## Topic Two\n\nC\n\n## Topic Three\n\nD"
    )

    head, suffix = _split_head_for_stitching(document)

    assert "# Intro" in head
    assert "## Topic One" in head
    assert "## Topic Two" not in head
    assert "## Topic Two" in suffix


def test_split_tail_for_stitching_keeps_fenced_code_block_intact():
    """Tail splitting should not start in the middle of a fenced code block."""
    document = (
        "## Intro\n\nOverview\n\n```python\n# inside fence\nprint('hi')\n```\n\n"
        "## Next Topic\n\nBody"
    )

    with patch("notewise.pipeline.generation.DEFAULT_STITCH_CHAR_BOUNDARY", 35):
        _prefix, tail = _split_tail_for_stitching(document)

    assert tail.count("```") == 2
    assert "# inside fence" in tail
    assert "## Next Topic" in tail


def test_split_head_for_stitching_keeps_fenced_code_block_intact():
    """Head splitting should include a full fenced code block before splitting."""
    document = (
        "## Intro\n\nOverview\n\n```python\n# inside fence\nprint('hi')\n```\n\n"
        "## Next Topic\n\nBody"
    )

    with patch("notewise.pipeline.generation.DEFAULT_STITCH_CHAR_BOUNDARY", 35):
        head, suffix = _split_head_for_stitching(document)

    assert head.count("```") == 2
    assert "# inside fence" in head
    assert suffix.startswith("## Next Topic")


def test_split_tail_for_stitching_applies_char_cap_even_with_headings():
    """Tail splitting should keep boundary windows bounded even with many headings."""
    document = (
        "## Topic One\n\nA\n\n## Topic Two\n\nB\n\n"
        "## Topic Three\n\nC\n\n## Topic Four\n\nD"
    )

    with patch("notewise.pipeline.generation.DEFAULT_STITCH_CHAR_BOUNDARY", 25):
        prefix, tail = _split_tail_for_stitching(document)

    assert "## Topic One" in prefix
    assert "## Topic One" not in tail
    assert tail.startswith("## Topic Three") or tail.startswith("## Topic Four")


def test_normalize_stitched_document_removes_part_suffix_from_first_heading():
    """Stitched output should not keep chunk-local part labels in the first heading."""
    document = "## Python Programming Fundamentals: Part 1\n\nBody text"

    normalized = _normalize_stitched_document(document)

    assert normalized == "## Python Programming Fundamentals\n\nBody text"


def test_normalize_stitched_document_preserves_non_part_headings():
    """Normalization should leave unrelated headings untouched."""
    document = "## Part 1 Exercises\n\nBody text"

    normalized = _normalize_stitched_document(document)

    assert normalized == document


def test_normalize_stitched_document_cleans_all_matching_headings():
    """Normalization should strip chunk-local labels from every heading."""
    document = (
        "## Python Basics: Part 1\n\nIntro\n\n"
        "### Variables - Chunk 2\n\nDetails\n\n"
        "## Part 1 Exercises\n\nPractice"
    )

    normalized = _normalize_stitched_document(document)

    assert normalized == (
        "## Python Basics\n\nIntro\n\n"
        "### Variables\n\nDetails\n\n"
        "## Part 1 Exercises\n\nPractice"
    )


def test_normalize_stitched_document_removes_restarted_duplicate_chapter_h1s():
    """Repeated chapter-level H1 restarts should be removed from stitched output."""
    document = (
        "# Chapter: Your First Python Program\n\nIntro\n\n"
        "## Setup\n\nInstall Python\n\n"
        "# Your First Python Program\n\n"
        "## Running Code\n\nUse the IDE run action"
    )

    normalized = _normalize_stitched_document(document)

    assert normalized == (
        "# Chapter: Your First Python Program\n\nIntro\n\n"
        "## Setup\n\nInstall Python\n\n"
        "## Running Code\n\nUse the IDE run action"
    )


def test_normalize_stitched_document_demotes_distinct_followup_h1s():
    """Distinct follow-up H1s should become H2s under the preserved root title."""
    document = (
        "# Chapter: If Statements in Python\n\nIntro\n\n"
        "# Control Flow: Advanced Conditional Logic\n\nMore detail"
    )

    normalized = _normalize_stitched_document(document)

    assert normalized == (
        "# Chapter: If Statements in Python\n\nIntro\n\n"
        "## Control Flow: Advanced Conditional Logic\n\nMore detail"
    )
