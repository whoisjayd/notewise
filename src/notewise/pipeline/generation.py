"""Study material generator with chunking and stitching logic."""

from __future__ import annotations

import asyncio
import bisect
import re
from collections.abc import Callable

import structlog
from litellm import token_counter

from notewise._constants import (
    DEFAULT_MAX_CONCURRENT_CHAPTERS,
    DEFAULT_STITCH_CHAR_BOUNDARY,
    DEFAULT_STITCH_SECTION_BOUNDARY_COUNT,
    DEFAULT_TEMPERATURE,
    DEFAULT_USE_COMBINE_CHUNK,
)
from notewise.config import settings as config
from notewise.llm.prompts.chapter_notes import (
    get_chapter_prompt,
)
from notewise.llm.prompts.quiz import (
    QUIZ_SYSTEM_PROMPT,
    get_quiz_combine_prompt,
    get_quiz_prompt,
)
from notewise.llm.prompts.study_notes import (
    SYSTEM_PROMPT,
    get_chunk_prompt,
    get_combine_prompt,
    get_single_pass_prompt,
    get_stitch_prompt,
)
from notewise.llm.provider import LLMProvider


# Re-use system prompt for chapter generation
CHAPTER_SYSTEM_PROMPT = SYSTEM_PROMPT

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
_MARKDOWN_HEADING_PATTERN = re.compile(r"(?m)^#{1,6}\s+")
_MARKDOWN_HEADING_LINE_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_MARKDOWN_FENCE_PATTERN = re.compile(r"^\s*(```+|~~~+)")
_PART_HEADING_SUFFIX_PATTERN = re.compile(
    r"^(#{1,6}\s+.+?)(?:\s*[:\-]\s*(?:Part|Chunk)\s+\d+"
    r"|\s*\((?:Part|Chunk)\s+\d+\))\s*$",
    re.IGNORECASE,
)
_CHAPTER_HEADING_PREFIX_PATTERN = re.compile(
    r"^chapter(?:\s+\d+)?\s*:\s*", re.IGNORECASE
)


def _join_markdown_fragments(*parts: str) -> str:
    """Join Markdown fragments without introducing excessive blank lines."""
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


def _collect_markdown_boundaries(document: str) -> tuple[list[int], list[int]]:
    """Collect heading positions and line-safe split boundaries outside fences."""
    heading_positions: list[int] = []
    safe_boundaries = [0]
    offset = 0
    in_fence = False
    fence_marker: str | None = None

    for line in document.splitlines(keepends=True):
        if not in_fence and _MARKDOWN_HEADING_PATTERN.match(line):
            heading_positions.append(offset)

        fence_match = _MARKDOWN_FENCE_PATTERN.match(line)
        if fence_match:
            marker = fence_match.group(1)[0]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = None

        offset += len(line)
        if not in_fence:
            safe_boundaries.append(offset)

    if safe_boundaries[-1] != len(document):
        safe_boundaries.append(len(document))

    return heading_positions, safe_boundaries


def _select_safe_boundary_before(
    preferred_offset: int,
    safe_boundaries: list[int],
) -> int:
    """Select the nearest safe boundary at or before the preferred offset."""
    index = bisect.bisect_right(safe_boundaries, preferred_offset) - 1
    return safe_boundaries[max(index, 0)]


def _select_safe_boundary_after(
    preferred_offset: int,
    safe_boundaries: list[int],
    document_length: int,
) -> int:
    """Select the nearest safe boundary at or after the preferred offset."""
    index = bisect.bisect_left(safe_boundaries, preferred_offset)
    if index < len(safe_boundaries):
        return safe_boundaries[index]
    return document_length


def _split_tail_for_stitching(document: str) -> tuple[str, str]:
    """Split a document into prefix + tail fragment for boundary stitching."""
    heading_positions, safe_boundaries = _collect_markdown_boundaries(document)
    char_limited_start = max(0, len(document) - DEFAULT_STITCH_CHAR_BOUNDARY)
    if len(heading_positions) > DEFAULT_STITCH_SECTION_BOUNDARY_COUNT:
        preferred_start = max(
            heading_positions[-DEFAULT_STITCH_SECTION_BOUNDARY_COUNT],
            char_limited_start,
        )
    else:
        preferred_start = char_limited_start
    start = _select_safe_boundary_before(preferred_start, safe_boundaries)
    return document[:start].rstrip(), document[start:].lstrip()


def _split_head_for_stitching(document: str) -> tuple[str, str]:
    """Split a document into head fragment + suffix for boundary stitching."""
    heading_positions, safe_boundaries = _collect_markdown_boundaries(document)
    char_limited_end = min(len(document), DEFAULT_STITCH_CHAR_BOUNDARY)
    if len(heading_positions) > DEFAULT_STITCH_SECTION_BOUNDARY_COUNT:
        preferred_end = min(
            heading_positions[DEFAULT_STITCH_SECTION_BOUNDARY_COUNT],
            char_limited_end,
        )
    else:
        preferred_end = char_limited_end
    end = _select_safe_boundary_after(preferred_end, safe_boundaries, len(document))
    return document[:end].rstrip(), document[end:].lstrip()


def _normalize_stitched_document(document: str) -> str:
    """Clean chunk-local framing from a stitched Markdown document."""
    lines = document.splitlines()
    normalized_lines: list[str] = []
    first_h1_key: str | None = None
    in_fence = False
    fence_marker: str | None = None

    for line in lines:
        fence_match = _MARKDOWN_FENCE_PATTERN.match(line)
        if fence_match:
            marker = fence_match.group(1)[0]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = None
            normalized_lines.append(line)
            continue

        if in_fence:
            normalized_lines.append(line)
            continue

        cleaned_line = _PART_HEADING_SUFFIX_PATTERN.sub(r"\1", line).rstrip()
        heading_match = _MARKDOWN_HEADING_LINE_PATTERN.match(cleaned_line)
        if not heading_match:
            normalized_lines.append(cleaned_line)
            continue

        hashes, heading_text = heading_match.groups()
        heading_key = _canonicalize_root_heading(heading_text)
        if hashes == "#":
            if first_h1_key is None:
                first_h1_key = heading_key
            elif heading_key == first_h1_key:
                continue
            else:
                cleaned_line = f"## {heading_text}"

        normalized_lines.append(cleaned_line)

    normalized_document = "\n".join(normalized_lines)
    return re.sub(r"\n{3,}", "\n\n", normalized_document).strip()


def _canonicalize_root_heading(heading_text: str) -> str:
    """Normalize root headings so restarts of the same chapter can be detected."""
    canonical = heading_text.strip()
    canonical = _CHAPTER_HEADING_PREFIX_PATTERN.sub("", canonical)
    canonical = re.sub(r"\s+", " ", canonical)
    return canonical.casefold()


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
        use_combine_chunk: bool = DEFAULT_USE_COMBINE_CHUNK,
    ):
        """
        Initialize generator.

        Args:
            provider: LLM provider instance.
            temperature: LLM response temperature.
            max_tokens: Maximum tokens for LLM responses.
            use_combine_chunk: Whether to use the deprecated legacy combine flow.
        """
        self.provider = provider
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.use_combine_chunk = use_combine_chunk

    async def _combine_chunk_notes(
        self,
        chunk_notes: list[str],
        *,
        system_prompt: str,
    ) -> str:
        """Run the deprecated legacy combine-all-chunks flow."""
        return await self.provider.generate(
            system_prompt=system_prompt,
            user_prompt=get_combine_prompt(chunk_notes),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

    async def _stitch_chunk_notes(
        self,
        chunk_notes: list[str],
        *,
        system_prompt: str,
    ) -> str:
        """Stitch adjacent chunk outputs into one continuous Markdown document."""
        stitched_document = chunk_notes[0]

        for next_chunk_notes in chunk_notes[1:]:
            prefix, previous_tail = _split_tail_for_stitching(stitched_document)
            next_head, suffix = _split_head_for_stitching(next_chunk_notes)
            stitched_boundary = await self.provider.generate(
                system_prompt=system_prompt,
                user_prompt=get_stitch_prompt(previous_tail, next_head),
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            stitched_document = _join_markdown_fragments(
                prefix,
                stitched_boundary,
                suffix,
            )

        return _normalize_stitched_document(stitched_document)

    async def _finalize_chunk_notes(
        self,
        chunk_notes: list[str],
        *,
        system_prompt: str,
        on_combine: Callable[[int], None] | None = None,
    ) -> str:
        """Finalize chunk notes with default stitching or legacy combine."""
        if len(chunk_notes) == 1:
            return chunk_notes[0]

        if on_combine:
            on_combine(len(chunk_notes))

        if self.use_combine_chunk:
            logger.warning(
                "Using deprecated legacy combine-chunk flow instead of stitching."
            )
            return await self._combine_chunk_notes(
                chunk_notes,
                system_prompt=system_prompt,
            )

        return await self._stitch_chunk_notes(
            chunk_notes,
            system_prompt=system_prompt,
        )

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

        logger.info(
            f"{video_title}: Finalizing {len(chunk_notes)} chunks via "
            f"{'legacy combine' if self.use_combine_chunk else 'stitching'}..."
        )
        final_notes = await self._finalize_chunk_notes(
            chunk_notes,
            system_prompt=SYSTEM_PROMPT,
            on_combine=on_combine,
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
            f"Chapter '{chapter_title[:40]}': finalizing {len(chunk_notes)} parts "
            f"via {'legacy combine' if self.use_combine_chunk else 'stitching'}..."
        )
        return await self._finalize_chunk_notes(
            chunk_notes,
            system_prompt=CHAPTER_SYSTEM_PROMPT,
            on_combine=on_combine,
        )

    async def generate_chapter_notes_concurrent(
        self,
        chapter_transcripts: dict[str, str],
        *,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT_CHAPTERS,
        semaphore: asyncio.Semaphore | None = None,
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
        sem = semaphore or asyncio.Semaphore(max(1, max_concurrent))

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
