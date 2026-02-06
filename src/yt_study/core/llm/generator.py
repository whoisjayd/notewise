"""Study material generator with chunking and combining logic."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles
import structlog
from litellm import token_counter

from ..telemetry import telemetry
from ...config import config

if TYPE_CHECKING:
    from ..events import EventEmitter
    from ..youtube.metadata import VideoChapter
    from ..youtube.transcript import VideoTranscript

from ...prompts.chapter_notes import (
    get_chapter_prompt,
    get_combine_chapters_prompt,
)
from ...prompts.study_notes import (
    SYSTEM_PROMPT,
    get_chunk_prompt,
    get_combine_prompt,
    get_single_pass_prompt,
)
from .providers import LLMProvider


# Re-use system prompt for now
CHAPTER_SYSTEM_PROMPT = SYSTEM_PROMPT

logger = structlog.get_logger(__name__)


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
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        event_emitter: EventEmitter | None = None,
    ):
        """
        Initialize generator.

        Args:
            provider: LLM provider instance.
            temperature: LLM response temperature.
            max_tokens: Maximum tokens for LLM responses.
            chunk_size: Optional token chunk size override.
            chunk_overlap: Optional token chunk overlap override.
            event_emitter: Optional event emitter for progress reporting.
        """
        self.provider = provider
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.chunk_size = chunk_size or config.chunk_size
        self.chunk_overlap = chunk_overlap or config.chunk_overlap
        self.event_emitter = event_emitter

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

    def _chunk_transcript(
        self,
        transcript: str,
        chapters: list[VideoChapter] | None = None,
        transcript_obj: VideoTranscript | None = None,
    ) -> list[str]:
        """
        Split transcript into chunks with overlap.

        Uses recursive chunking strategy:
        - If chapters are provided, chunks are aligned with chapter boundaries.
        - Target size: Defined in config (default 4000 tokens)
        - Overlap: Defined in config (default 200 tokens)
        - Priority: Chapters > Sentence boundaries > Newlines > Words > Hard char limit

        Args:
            transcript: The full transcript text.
            chapters: Optional list of video chapters.
            transcript_obj: Optional VideoTranscript object for chapter splitting.

        Returns:
            List of text chunks.
        """
        # Chapter-aware chunking
        if chapters and transcript_obj:
            from ..youtube.transcript import split_transcript_by_chapters

            logger.info(
                f"Performing chapter-aware chunking with {len(chapters)} chapters"
            )

            # Check if input transcript has timestamps to preserve them
            include_timestamps = (
                "[" in transcript and ":" in transcript and "]" in transcript
            )

            chapter_data = split_transcript_by_chapters(
                transcript_obj, chapters, include_timestamps=include_timestamps
            )

            all_chunks = []
            for _chap_title, chap_text in chapter_data.items():
                if not chap_text.strip():
                    continue

                # For each chapter, if it's too big, chunk it using standard logic
                # Pass chapters=None to avoid recursion
                chap_chunks = self._chunk_transcript(chap_text)
                all_chunks.extend(chap_chunks)

            if all_chunks:
                return all_chunks

        token_count = self._count_tokens(transcript)

        # Fast path: Return single chunk if within limits
        if token_count <= self.chunk_size:
            return [transcript]

        logger.info(
            f"Transcript too long ({token_count:,} tokens), performing chunking..."
        )

        chunks: list[str] = []

        # Strategy 1: Split by sentences
        sentences = transcript.split(". ")

        # Strategy 2: Split by newlines if sentences fail
        if len(sentences) < 2 and token_count > self.chunk_size:
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
            if term_tokens > self.chunk_size:
                # 1. Flush current buffer
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = []
                    current_tokens = 0

                # 2. Hard split the massive segment
                # Estimate char limit based on token size (conservative 3 chars/token)
                char_limit = self.chunk_size * 3
                for i in range(0, len(sentence), char_limit):
                    sub_part = sentence[i : i + char_limit]
                    chunks.append(sub_part)
                continue

            # Standard accumulation
            if current_tokens + term_tokens > self.chunk_size:
                # Chunk is full. Commit it.
                if current_chunk:
                    chunks.append(" ".join(current_chunk))

                    # Create overlap for next chunk
                    overlap_chunk: list[str] = []
                    overlap_tokens = 0

                    # Take sentences from the end of current_chunk until overlap limit
                    for prev_sent in reversed(current_chunk):
                        prev_tokens = self._count_tokens(prev_sent)
                        if overlap_tokens + prev_tokens <= self.chunk_overlap:
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
        video_title: str,
        message: str,
        video_id: str | None = None,
    ) -> None:
        """Safe helper to emit progress event or log message."""
        if self.event_emitter:
            self.event_emitter.emit_progress(video_id, message, video_title=video_title)
        else:
            logger.info(f"{video_title}: {message}")

    async def generate_study_notes(
        self,
        transcript: str,
        video_title: str = "Video",
        video_id: str | None = None,
        output_dir: Path | None = None,
        chapters: list[VideoChapter] | None = None,
        transcript_obj: VideoTranscript | None = None,
    ) -> str:
        """
        Generate study notes from transcript.

        Args:
            transcript: Full video transcript text.
            video_title: Video title for progress display.
            video_id: YouTube video ID for generating timestamp links.
            output_dir: Optional directory to save intermediate chunks.
            chapters: Optional list of video chapters for better chunking.
            transcript_obj: Optional VideoTranscript object for chapter splitting.

        Returns:
            Complete study notes in Markdown format.
        """
        trace_id = str(uuid.uuid4())
        telemetry.capture_event(
            "ai_study_notes_generation_start",
            {
                "video_id": video_id,
                "has_chapters": chapters is not None,
                "transcript_length": len(transcript),
                "$ai_trace_id": trace_id,
            },
        )
        try:
            chunks = self._chunk_transcript(
                transcript, chapters=chapters, transcript_obj=transcript_obj
            )

            # Single chunk - generate directly
            if len(chunks) == 1:
                self._update_status(video_title, "Generating notes...", video_id=video_id)

                notes = await self.provider.generate(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=get_single_pass_prompt(transcript),
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    trace_id=trace_id,
                )

                if video_id:
                    notes = self._post_process_timestamps(notes, video_id)

                telemetry.capture_event(
                    "ai_study_notes_generation_success",
                    {"video_id": video_id, "chunks": 1, "$ai_trace_id": trace_id},
                )
                return notes

            # Multiple chunks - generate for each, then combine
            self._update_status(
                video_title,
                f"Generating notes for {len(chunks)} chunks...",
                video_id=video_id,
            )

            chunk_notes = []
            chunks_folder = None
            if output_dir:
                chunks_folder = output_dir / "chunks"
                chunks_folder.mkdir(parents=True, exist_ok=True)

            for i, chunk in enumerate(chunks, 1):
                msg = f"Chunk {i}/{len(chunks)} (Generating)"
                self._update_status(video_title, msg, video_id=video_id)

                note = await self.provider.generate(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=get_chunk_prompt(chunk),
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    trace_id=trace_id,
                )

                if video_id:
                    note = self._post_process_timestamps(note, video_id)

                # Save individual chunk note if output_dir provided
                if chunks_folder:
                    chunk_file = chunks_folder / f"{i:02d}_chunk.md"
                    metadata = {
                        "video_id": video_id,
                        "chunk_index": i,
                        "total_chunks": len(chunks),
                        "video_title": video_title,
                    }
                    frontmatter = "---\n"
                    frontmatter += json.dumps(metadata, indent=2) + "\n"
                    frontmatter += "---\n\n"

                    async with aiofiles.open(chunk_file, "w", encoding="utf-8") as f:
                        await f.write(frontmatter + note)

                chunk_notes.append(note)

            self._update_status(
                video_title,
                f"Combining {len(chunk_notes)} chunk notes...",
                video_id=video_id,
            )

            final_notes = await self.provider.generate(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=get_combine_prompt(chunk_notes),
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                trace_id=trace_id,
            )

            if video_id:
                final_notes = self._post_process_timestamps(final_notes, video_id)

            telemetry.capture_event(
                "ai_study_notes_generation_success",
                {"video_id": video_id, "chunks": len(chunks), "$ai_trace_id": trace_id},
            )
            return final_notes
        except Exception as e:
            telemetry.capture_exception(e, {"video_id": video_id, "task": "study_notes"})
            raise

    def _post_process_timestamps(self, text: str, video_id: str) -> str:
        """
        Convert [MM:SS] strings in the text into clickable YouTube links.
        """
        import re

        def replace_timestamp(match: re.Match[str]) -> str:
            ts_str = match.group(1)
            parts = ts_str.split(":")
            if len(parts) == 2:
                minutes, seconds = map(int, parts)
                total_seconds = minutes * 60 + seconds
            elif len(parts) == 3:
                hours, minutes, seconds = map(int, parts)
                total_seconds = hours * 3600 + minutes * 60 + seconds
            else:
                return match.group(0)

            return f"[{ts_str}](https://youtu.be/{video_id}?t={total_seconds})"

        # Match [MM:SS] or [HH:MM:SS]
        pattern = r"\[(\d{1,2}:\d{2}(?::\d{2})?)\]"
        return re.sub(pattern, replace_timestamp, text)

    async def generate_single_chapter_notes(
        self,
        chapter_title: str,
        chapter_text: str,
        video_id: str | None = None,
    ) -> str:
        """
        Generate study notes for a single chapter.

        Args:
            chapter_title: Title of the chapter.
            chapter_text: Transcript text for the chapter.
            video_id: Optional video ID for timestamps.

        Returns:
            Study notes for the chapter.
        """
        notes = await self.provider.generate(
            system_prompt=CHAPTER_SYSTEM_PROMPT,
            user_prompt=get_chapter_prompt(chapter_title, chapter_text),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        if video_id:
            notes = self._post_process_timestamps(notes, video_id)

        return notes

    async def generate_chapter_based_notes(
        self,
        chapter_transcripts: dict[str, str],
        video_title: str = "Video",
        video_id: str | None = None,
    ) -> str:
        """
        Generate study notes using chapter-based approach.

        Args:
            chapter_transcripts: Dictionary mapping chapter titles to transcript text.
            video_title: Video title for display.
            video_id: YouTube video ID for generating timestamp links.

        Returns:
            Complete study notes organized by chapters.
        """
        trace_id = str(uuid.uuid4())
        telemetry.capture_event(
            "ai_chapter_notes_generation_start",
            {
                "video_id": video_id,
                "chapter_count": len(chapter_transcripts),
                "$ai_trace_id": trace_id,
            },
        )
        try:
            self._update_status(
                video_title,
                f"Generating notes for {len(chapter_transcripts)} chapters...",
                video_id=video_id,
            )

            chapter_notes = {}
            total_chapters = len(chapter_transcripts)

            for i, (chapter_title, chapter_text) in enumerate(
                chapter_transcripts.items(), 1
            ):
                msg = f"Chapter {i}/{total_chapters}: {chapter_title[:20]}..."
                self._update_status(video_title, msg, video_id=video_id)

                # If a chapter is huge, perform recursive chunking
                token_count = self._count_tokens(chapter_text)
                if token_count > self.chunk_size:
                    logger.info(
                        f"Chapter '{chapter_title}' too long "
                        f"({token_count:,} tokens), chunking..."
                    )
                    chunks = self._chunk_transcript(chapter_text)
                    chunk_notes = []

                    for j, chunk in enumerate(chunks, 1):
                        chunk_msg = f"Chapter {i}/{total_chapters} (Part {j}/{len(chunks)})"
                        self._update_status(video_title, chunk_msg, video_id=video_id)

                        note = await self.provider.generate(
                            system_prompt=CHAPTER_SYSTEM_PROMPT,
                            user_prompt=get_chapter_prompt(chapter_title, chunk),
                            temperature=self.temperature,
                            max_tokens=self.max_tokens,
                            trace_id=trace_id,
                        )
                        chunk_notes.append(note)

                    # Combine chunks of this specific chapter
                    self._update_status(
                        video_title,
                        f"Combining chunks for chapter: {chapter_title[:20]}...",
                        video_id=video_id,
                    )
                    notes = await self.provider.generate(
                        system_prompt=CHAPTER_SYSTEM_PROMPT,
                        user_prompt=get_combine_prompt(chunk_notes),
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                        trace_id=trace_id,
                    )
                else:
                    notes = await self.provider.generate(
                        system_prompt=CHAPTER_SYSTEM_PROMPT,
                        user_prompt=get_chapter_prompt(chapter_title, chapter_text),
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                        trace_id=trace_id,
                    )

                if video_id:
                    notes = self._post_process_timestamps(notes, video_id)

                chapter_notes[chapter_title] = notes

            self._update_status(
                video_title, "Combining chapter notes...", video_id=video_id
            )

            final_notes = await self.provider.generate(
                system_prompt=CHAPTER_SYSTEM_PROMPT,
                user_prompt=get_combine_chapters_prompt(chapter_notes),
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                trace_id=trace_id,
            )

            if video_id:
                final_notes = self._post_process_timestamps(final_notes, video_id)

            telemetry.capture_event(
                "ai_chapter_notes_generation_success",
                {"video_id": video_id, "chapters": total_chapters, "$ai_trace_id": trace_id},
            )
            return final_notes
        except Exception as e:
            telemetry.capture_exception(e, {"video_id": video_id, "task": "chapter_notes"})
            raise
