"""Study material generator with chunking and combining logic."""

import logging

from litellm import token_counter
from rich.console import Console
from rich.progress import Progress, TaskID

from ..config import config
from ..prompts.chapter_notes import (
    get_chapter_prompt,
    get_combine_chapters_prompt,
)
from ..prompts.study_notes import (
    SYSTEM_PROMPT,
    get_chunk_prompt,
    get_combine_prompt,
    get_single_pass_prompt,
)
from .providers import LLMProvider


# Re-use system prompt for now
CHAPTER_SYSTEM_PROMPT = SYSTEM_PROMPT

console = Console()
logger = logging.getLogger(__name__)


class StudyMaterialGenerator:
    """
    Generate study materials from transcripts using LLM.

    Handles token counting, text chunking, and recursive summarization/generation.
    """

    def __init__(self, provider: LLMProvider):
        """
        Initialize generator.

        Args:
            provider: LLM provider instance.
        """
        self.provider = provider

    def _count_tokens(self, text: str) -> int:
        """Count tokens in text using model-specific tokenizer."""
        # Note: token_counter might do network calls for some models or use
        # local libraries (tiktoken). For efficiency, we assume it's fast.
        try:
            count = token_counter(model=self.provider.model, text=text)
            return int(count) if count is not None else len(text) // 4
        except Exception:
            # Fallback estimation if tokenizer fails (approx 4 chars per token)
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

            # Re-add delimiter for estimation (approximate)
            # We assume '. ' was the delimiter for simplicity, logic holds
            # for others mostly as we care about token count
            term = sentence + ". "
            term_tokens = self._count_tokens(term)

            # Handle edge case: Single sentence/segment is larger than chunk_size
            if term_tokens > config.chunk_size:
                # 1. Flush current buffer
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = []
                    current_tokens = 0

                # 2. Hard split the massive segment
                # Estimate char limit based on token size (conservative 3 chars/token)
                char_limit = config.chunk_size * 3
                for i in range(0, len(sentence), char_limit):
                    sub_part = sentence[i : i + char_limit]
                    chunks.append(sub_part)
                continue

            # Standard accumulation
            if current_tokens + term_tokens > config.chunk_size:
                # Chunk is full. Commit it.
                if current_chunk:
                    chunks.append(" ".join(current_chunk))

                    # Create overlap for next chunk
                    overlap_chunk: list[str] = []
                    overlap_tokens = 0

                    # Take sentences from the end of current_chunk until overlap limit
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

    def _update_status(
        self,
        progress: Progress | None,
        task_id: TaskID | None,
        video_title: str,
        message: str,
    ) -> None:
        """Safe helper to update progress bar or log message."""
        if progress and task_id is not None:
            short_title = (
                (video_title[:20] + "...") if len(video_title) > 20 else video_title
            )
            # We assume the layout uses 'description' for the status text
            progress.update(
                task_id, description=f"[yellow]{short_title}[/yellow]: {message}"
            )
        else:
            logger.info(f"{video_title}: {message}")

    async def generate_study_notes(
        self,
        transcript: str,
        video_title: str = "Video",
        progress: Progress | None = None,
        task_id: TaskID | None = None,
    ) -> str:
        """
        Generate study notes from transcript.

        Args:
            transcript: Full video transcript text.
            video_title: Video title for progress display.
            progress: Optional existing progress bar instance.
            task_id: Optional task ID for updating progress.

        Returns:
            Complete study notes in Markdown format.
        """
        chunks = self._chunk_transcript(transcript)

        # Single chunk - generate directly
        if len(chunks) == 1:
            self._update_status(progress, task_id, video_title, "Generating notes...")

            notes = await self.provider.generate(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=get_single_pass_prompt(transcript),
            )

            if not progress:
                logger.info(f"Generated notes for {video_title}")
            return notes

        # Multiple chunks - generate for each, then combine
        self._update_status(
            progress,
            task_id,
            video_title,
            f"Generating notes for {len(chunks)} chunks...",
        )

        chunk_notes = []

        for i, chunk in enumerate(chunks, 1):
            msg = f"Chunk {i}/{len(chunks)} (Generating)"
            self._update_status(progress, task_id, video_title, msg)

            note = await self.provider.generate(
                system_prompt=SYSTEM_PROMPT, user_prompt=get_chunk_prompt(chunk)
            )
            chunk_notes.append(note)

        self._update_status(
            progress,
            task_id,
            video_title,
            f"Combining {len(chunk_notes)} chunk notes...",
        )

        final_notes = await self.provider.generate(
            system_prompt=SYSTEM_PROMPT, user_prompt=get_combine_prompt(chunk_notes)
        )

        if not progress:
            logger.info(f"Completed notes for {video_title}")

        return final_notes

    async def generate_chapter_based_notes(
        self,
        chapter_transcripts: dict[str, str],
        video_title: str = "Video",
        progress: Progress | None = None,
        task_id: TaskID | None = None,
    ) -> str:
        """
        Generate study notes using chapter-based approach.

        Args:
            chapter_transcripts: Dictionary mapping chapter titles to transcript text.
            video_title: Video title for display.
            progress: Optional existing progress bar instance.
            task_id: Optional task ID for updating progress.

        Returns:
            Complete study notes organized by chapters.
        """
        # Imports are already at top-level or can be moved up, but let's
        # fix the specific issue. Previously we did lazy import inside
        # function which caused issues

        self._update_status(
            progress,
            task_id,
            video_title,
            f"Generating notes for {len(chapter_transcripts)} chapters...",
        )

        chapter_notes = {}
        total_chapters = len(chapter_transcripts)

        for i, (chapter_title, chapter_text) in enumerate(
            chapter_transcripts.items(), 1
        ):
            msg = f"Chapter {i}/{total_chapters}: {chapter_title[:20]}..."
            self._update_status(progress, task_id, video_title, msg)

            # If a chapter is huge, we might need recursive chunking here too.
            # For now, we assume chapters are reasonably sized or the model
            # can handle ~100k context. Future improvement: Check token
            # count of chapter_text and recurse if needed.

            notes = await self.provider.generate(
                system_prompt=CHAPTER_SYSTEM_PROMPT,
                user_prompt=get_chapter_prompt(chapter_title, chapter_text),
            )
            chapter_notes[chapter_title] = notes

        self._update_status(
            progress, task_id, video_title, "Combining chapter notes..."
        )

        final_notes = await self.provider.generate(
            system_prompt=CHAPTER_SYSTEM_PROMPT,
            user_prompt=get_combine_chapters_prompt(chapter_notes),
        )

        if not progress:
            logger.info(f"Completed chapter-based notes for {video_title}")

        return final_notes
