"""Study material generator with chunking and combining logic."""

import logging
from collections.abc import Callable

from litellm import token_counter

from ..config import config
from ..prompts.chapter_notes import (
    get_chapter_prompt,
    get_combine_chapters_prompt,
)
from ..prompts.quiz import QUIZ_SYSTEM_PROMPT, get_quiz_prompt
from ..prompts.study_notes import (
    SYSTEM_PROMPT,
    get_chunk_prompt,
    get_combine_prompt,
    get_single_pass_prompt,
)
from .providers import LLMProvider


# Re-use system prompt for chapter generation
CHAPTER_SYSTEM_PROMPT = SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class StudyMaterialGenerator:
    """
    Generate study materials from transcripts using LLM.

    Handles token counting, text chunking, and recursive summarization/generation.
    """

    def __init__(
        self,
        provider: LLMProvider,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ):
        """
        Initialize generator.

        Args:
            provider: LLM provider instance.
            temperature: LLM response temperature.
            max_tokens: Maximum tokens for LLM responses.
        """
        self.provider = provider
        self.temperature = temperature
        self.max_tokens = max_tokens

    def _count_tokens(self, text: str) -> int:
        """Count tokens in text using model-specific tokenizer."""
        try:
            count = token_counter(model=self.provider.model, text=text)
            return int(count) if count is not None else len(text) // 4
        except Exception:
            # Fallback: ~4 chars per token
            return len(text) // 4

    def _chunk_transcript(self, transcript: str) -> list[str]:
        """
        Split transcript into chunks with overlap.

        Uses recursive chunking strategy:
        - Target size: Defined in config (default 4000 tokens)
        - Overlap: Defined in config (default 200 tokens)
        - Priority: Sentence boundaries > Newlines > Words > Hard char limit

        Args:
            transcript: The full transcript text.

        Returns:
            List of text chunks.
        """
        token_count = self._count_tokens(transcript)

        # Fast path: Return single chunk if within limits
        if token_count <= config.chunk_size:
            return [transcript]

        logger.info(
            f"Transcript too long ({token_count:,} tokens), performing chunking..."
        )

        chunks: list[str] = []

        # Strategy 1: Split by sentences
        sentences = transcript.split(". ")

        # Strategy 2: Split by newlines if sentences fail
        if len(sentences) < 2 and token_count > config.chunk_size:
            sentences = transcript.split("\n")

        # Strategy 3: Split by spaces if newlines fail
        if len(sentences) < 2:
            sentences = transcript.split(" ")

        current_chunk: list[str] = []
        current_tokens = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # Approximate token count including the '. ' delimiter
            term = sentence + ". "
            term_tokens = self._count_tokens(term)

            # Handle oversized single segment: flush buffer and hard-split
            if term_tokens > config.chunk_size:
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = []
                    current_tokens = 0

                # Hard split by character (conservative 3 chars/token)
                char_limit = config.chunk_size * 3
                for i in range(0, len(sentence), char_limit):
                    sub_part = sentence[i : i + char_limit]
                    chunks.append(sub_part)
                continue

            if current_tokens + term_tokens > config.chunk_size:
                if current_chunk:
                    chunks.append(" ".join(current_chunk))

                    # Build overlap from tail of current chunk
                    overlap_chunk: list[str] = []
                    overlap_tokens = 0

                    for prev_sent in reversed(current_chunk):
                        prev_tokens = self._count_tokens(prev_sent)
                        if overlap_tokens + prev_tokens <= config.chunk_overlap:
                            overlap_chunk.insert(0, prev_sent)
                            overlap_tokens += prev_tokens
                        else:
                            break

                    current_chunk = overlap_chunk + [sentence]
                    current_tokens = self._count_tokens(" ".join(current_chunk))
                else:
                    # Should be unreachable due to check above, but safe fallback
                    current_chunk.append(sentence)
                    current_tokens += term_tokens
            else:
                current_chunk.append(sentence)
                current_tokens += term_tokens

        # Add remaining chunk
        if current_chunk:
            chunks.append(" ".join(current_chunk))

        logger.info(f"Created {len(chunks)} chunks")
        return chunks

    async def generate_study_notes(
        self,
        transcript: str,
        video_title: str = "Video",
        on_chunk: Callable[[int, int], None] | None = None,
    ) -> str:
        """
        Generate study notes from transcript.

        Args:
            transcript: Full video transcript text.
            video_title: Video title for logging.

        Returns:
            Complete study notes in Markdown format.
        """
        chunks = self._chunk_transcript(transcript)

        if len(chunks) == 1:
            logger.info(f"{video_title}: Generating notes...")
            notes = await self.provider.generate(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=get_single_pass_prompt(transcript),
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            logger.info(f"Generated notes for {video_title}")
            return notes

        logger.info(f"{video_title}: Generating notes for {len(chunks)} chunks...")
        chunk_notes = []

        for i, chunk in enumerate(chunks, 1):
            if on_chunk:
                on_chunk(i, len(chunks))
            logger.info(f"{video_title}: Chunk {i}/{len(chunks)}")
            note = await self.provider.generate(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=get_chunk_prompt(chunk),
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            chunk_notes.append(note)

        logger.info(f"{video_title}: Combining {len(chunk_notes)} chunks...")
        final_notes = await self.provider.generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=get_combine_prompt(chunk_notes),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        logger.info(f"Completed notes for {video_title}")
        return final_notes

    async def generate_single_chapter_notes(
        self,
        chapter_title: str,
        chapter_text: str,
    ) -> str:
        """
        Generate study notes for a single chapter.

        If the chapter transcript exceeds the configured chunk_size the text is
        split into overlapping chunks first.  Each chunk is processed with the
        chapter-specific prompt and the results are merged with get_combine_prompt
        to produce a single coherent Markdown section.

        Args:
            chapter_title: Title of the chapter.
            chapter_text: Transcript text for the chapter.

        Returns:
            Study notes for the chapter in Markdown format.
        """
        token_count = self._count_tokens(chapter_text)

        # Fast path: chapter fits in one context window call
        if token_count <= config.chunk_size:
            return await self.provider.generate(
                system_prompt=CHAPTER_SYSTEM_PROMPT,
                user_prompt=get_chapter_prompt(chapter_title, chapter_text),
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

        # Chunked path: chapter is too long for a single call
        logger.info(
            f"Chapter '{chapter_title[:40]}' is large ({token_count:,} tokens),"
            " chunking before generation..."
        )
        chunks = self._chunk_transcript(chapter_text)
        chunk_notes: list[str] = []

        for i, chunk in enumerate(chunks, 1):
            logger.info(
                f"Chapter '{chapter_title[:40]}': generating part {i}/{len(chunks)}"
            )
            note = await self.provider.generate(
                system_prompt=CHAPTER_SYSTEM_PROMPT,
                user_prompt=get_chapter_prompt(chapter_title, chunk),
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            chunk_notes.append(note)

        logger.info(
            f"Chapter '{chapter_title[:40]}': combining {len(chunk_notes)} parts..."
        )
        if len(chunk_notes) == 1:
            return chunk_notes[0]
        return await self.provider.generate(
            system_prompt=CHAPTER_SYSTEM_PROMPT,
            user_prompt=get_combine_prompt(chunk_notes),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

    async def generate_chapter_based_notes(
        self,
        chapter_transcripts: dict[str, str],
        video_title: str = "Video",
    ) -> str:
        """
        Generate study notes using chapter-based approach.

        Args:
            chapter_transcripts: Dictionary mapping chapter titles to transcript text.
            video_title: Video title for logging.

        Returns:
            Complete study notes organized by chapters.
        """
        total_chapters = len(chapter_transcripts)
        logger.info(f"{video_title}: Generating {total_chapters} chapters...")

        chapter_notes = {}

        for i, (chapter_title, chapter_text) in enumerate(
            chapter_transcripts.items(), 1
        ):
            logger.info(
                f"{video_title}: Chapter {i}/{total_chapters}: {chapter_title[:30]}..."
            )
            notes = await self.provider.generate(
                system_prompt=CHAPTER_SYSTEM_PROMPT,
                user_prompt=get_chapter_prompt(chapter_title, chapter_text),
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            chapter_notes[chapter_title] = notes

        logger.info(f"{video_title}: Combining chapter notes...")
        final_notes = await self.provider.generate(
            system_prompt=CHAPTER_SYSTEM_PROMPT,
            user_prompt=get_combine_chapters_prompt(chapter_notes),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        logger.info(f"Completed chapter-based notes for {video_title}")
        return final_notes

    async def generate_quiz(self, transcript: str) -> str:
        """Generate a multiple-choice quiz from a transcript."""
        return await self.provider.generate(
            system_prompt=QUIZ_SYSTEM_PROMPT,
            user_prompt=get_quiz_prompt(transcript),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
