"""Study material generator with chunking and combining logic."""

import asyncio
import re
from collections.abc import Callable

import structlog
from litellm import token_counter

from yt_study._constants import DEFAULT_MAX_CONCURRENT_CHAPTERS, DEFAULT_TEMPERATURE
from yt_study.config import settings as config
from yt_study.llm.prompts.chapter_notes import (
    get_chapter_prompt,
    get_combine_chapters_prompt,
)
from yt_study.llm.prompts.quiz import (
    QUIZ_SYSTEM_PROMPT,
    get_quiz_combine_prompt,
    get_quiz_prompt,
)
from yt_study.llm.prompts.study_notes import (
    SYSTEM_PROMPT,
    get_chunk_prompt,
    get_combine_prompt,
    get_single_pass_prompt,
)
from yt_study.llm.provider import LLMProvider


# Re-use system prompt for chapter generation
CHAPTER_SYSTEM_PROMPT = SYSTEM_PROMPT

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")


class StudyMaterialGenerator:
    """
    Generate study materials from transcripts using LLM.

    Handles token counting, text chunking, and recursive summarization/generation.
    """

    def __init__(
        self,
        provider: LLMProvider,
        temperature: float = DEFAULT_TEMPERATURE,
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

    def count_tokens(self, text: str) -> int:
        """Public token-counting API used by pipeline stats and tests."""
        return self._count_tokens(text)

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

        # Strategy 1: Split by sentences without dropping punctuation
        sentences = _SENTENCE_SPLIT_PATTERN.split(transcript)

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

            # Count the segment as-is; sentence punctuation stays attached.
            term = sentence
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
        on_combine: Callable[[int], None] | None = None,
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
        if on_combine:
            on_combine(len(chunk_notes))
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
        on_chunk: Callable[[int, int], None] | None = None,
        on_combine: Callable[[int], None] | None = None,
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
            if on_chunk:
                on_chunk(i, len(chunks))
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
        if on_combine:
            on_combine(len(chunk_notes))
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
            notes = await self.generate_single_chapter_notes(
                chapter_title=chapter_title,
                chapter_text=chapter_text,
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

    async def generate_chapter_notes_concurrent(
        self,
        chapter_transcripts: dict[str, str],
        *,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT_CHAPTERS,
        video_title: str = "Video",
        on_chapter_start: Callable[[int, int], None] | None = None,
    ) -> dict[str, str]:
        """Generate notes for all chapters concurrently, bounded by a semaphore.

        Args:
            chapter_transcripts: Mapping of chapter title to transcript text.
            max_concurrent: Maximum simultaneous LLM calls (default 3).
            video_title: Video title for logging.
            on_chapter_start: Optional callback(chapter_num, total_chapters).

        Returns:
            Mapping of chapter title to generated notes, in input order.
        """
        total = len(chapter_transcripts)
        sem = asyncio.Semaphore(max_concurrent)

        async def _generate_one(
            idx: int, ch_title: str, ch_text: str
        ) -> tuple[str, str]:
            async with sem:
                if on_chapter_start:
                    on_chapter_start(idx, total)
                logger.info(
                    "chapter.generating",
                    video_title=video_title,
                    chapter=idx,
                    total_chapters=total,
                )
                notes = await self.generate_single_chapter_notes(ch_title, ch_text)
                return ch_title, notes

        tasks = [
            asyncio.create_task(_generate_one(i, title, text))
            for i, (title, text) in enumerate(chapter_transcripts.items(), 1)
        ]
        raw = await asyncio.gather(*tasks, return_exceptions=True)
        result: dict[str, str] = {}
        for item in raw:
            if isinstance(item, BaseException):
                raise item
            ch_title, notes = item
            result[ch_title] = notes
        return result

    async def generate_quiz(
        self,
        transcript: str,
        on_chunk: Callable[[int, int], None] | None = None,
        on_combine: Callable[[int], None] | None = None,
    ) -> str:
        """Generate a multiple-choice quiz from a transcript.

        If the transcript fits within the configured chunk size, a single
        LLM call is made (fast path).  For longer transcripts the text is
        split into chunks, a partial quiz is generated for each chunk, and
        the results are combined into one final quiz.
        """
        token_count = self._count_tokens(transcript)

        # Fast path: transcript fits in a single context window.
        if token_count <= config.chunk_size:
            return await self.provider.generate(
                system_prompt=QUIZ_SYSTEM_PROMPT,
                user_prompt=get_quiz_prompt(transcript),
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

        # Chunked path: generate a partial quiz per chunk then combine.
        logger.info(
            f"Quiz transcript is large ({token_count:,} tokens)"
            " — chunking before generation."
        )
        chunks = self._chunk_transcript(transcript)
        partial_quizzes: list[str] = []
        for i, chunk in enumerate(chunks, 1):
            logger.info(f"Quiz: generating part {i}/{len(chunks)}")
            if on_chunk:
                on_chunk(i, len(chunks))
            partial = await self.provider.generate(
                system_prompt=QUIZ_SYSTEM_PROMPT,
                user_prompt=get_quiz_prompt(chunk),
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            partial_quizzes.append(partial)

        if len(partial_quizzes) == 1:
            return partial_quizzes[0]

        logger.info(f"Quiz: combining {len(partial_quizzes)} partial quizzes.")
        if on_combine:
            on_combine(len(partial_quizzes))
        return await self.provider.generate(
            system_prompt=QUIZ_SYSTEM_PROMPT,
            user_prompt=get_quiz_combine_prompt(partial_quizzes),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
