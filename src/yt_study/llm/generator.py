"""Study material generator with chunking and combining logic."""

import logging
from typing import List, Optional

from litellm import token_counter
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TaskID

from ..config import config
from ..prompts.study_notes import (
    SYSTEM_PROMPT,
    get_chunk_prompt,
    get_combine_prompt,
    get_single_pass_prompt,
)
from .providers import LLMProvider

console = Console()
logger = logging.getLogger(__name__)


class StudyMaterialGenerator:
    """Generate study materials from transcripts using LLM."""
    
    def __init__(self, provider: LLMProvider):
        """
        Initialize generator.
        
        Args:
            provider: LLM provider instance
        """
        self.provider = provider
        
    def _count_tokens(self, text: str) -> int:
        """Count tokens in text using model-specific tokenizer."""
        return token_counter(model=self.provider.model, text=text)
    
    def _chunk_transcript(self, transcript: str) -> List[str]:
        """
        Split transcript into chunks with overlap.
        
        Uses recursive chunking strategy:
        - Target size: ~4000 tokens
        - Overlap: 200 tokens
        - Respects sentence boundaries when possible, but forces split if needed
        """
        token_count = self._count_tokens(transcript)
        
        # If small enough, return as single chunk
        if token_count <= config.chunk_size:
            return [transcript]
        
        logger.info(f"Transcript: {token_count:,} tokens, chunking...")
        
        chunks = []
        
        # Try splitting by sentence first
        sentences = transcript.split('. ')
        
        # Check if we failed to split effectively (e.g., no periods)
        if len(sentences) < 2 and token_count > config.chunk_size:
             # Try splitting by newlines
             sentences = transcript.split('\n')
             
             # If still no luck, force split by token count is hard
             # So we'll iterate through words instead
             if len(sentences) < 2:
                 sentences = transcript.split(' ')
        
        current_chunk = []
        current_tokens = 0
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            sentence_tokens = self._count_tokens(sentence)
            
            # Special case: If a single "sentence" is huge (> chunk_size),
            # we must process what we have so far, then process this huge sentence separately
            if sentence_tokens > config.chunk_size:
                # 1. Save current accumulated chunk if any
                if current_chunk:
                    chunk_text = '. '.join(current_chunk) + '.'
                    chunks.append(chunk_text)
                    current_chunk = []
                    current_tokens = 0
                
                # 2. Force split the huge sentence
                # This is a fallback for extremely long segments without delimiters
                # We'll rely on the existing logic to pick it up in correct chunks if we treat words/parts
                # But for simplicity, let's just add it as is and warn (or better, split it)
                
                # Let's split this huge sentence into smaller parts by words
                words = sentence.split(' ')
                # Re-feed these words back into the logic (simple approach: extend sentences list? No, modify loop)
                # Better: nested processing for this huge sentence
                
                # Simple robust approach: split huge text by fixed character count approx
                # Assuming 1 token ~ 4 chars
                char_limit = config.chunk_size * 4
                parts = [sentence[i:i+char_limit] for i in range(0, len(sentence), char_limit)]
                
                for part in parts:
                    chunks.append(part)
                    
                # Re-initialize overlap for next time? 
                # For simplicity, we just continue. 
                # This rare case usually means bad transcript quality.
                continue

            # Standard Logic
            if current_tokens + sentence_tokens > config.chunk_size:
                # Chunk is full
                if current_chunk:
                    chunk_text = '. '.join(current_chunk) + '.'
                    chunks.append(chunk_text)
                    
                    # Start new chunk with overlap
                    overlap_chunk = []
                    overlap_tokens = 0
                    for sent in reversed(current_chunk):
                        sent_tokens = self._count_tokens(sent)
                        if overlap_tokens + sent_tokens <= config.chunk_overlap:
                            overlap_chunk.insert(0, sent)
                            overlap_tokens += sent_tokens
                        else:
                            break
                    
                    current_chunk = overlap_chunk + [sentence]
                    current_tokens = self._count_tokens('. '.join(current_chunk))
                else:
                    # Current chunk is empty but sentence fits (checked above)
                    current_chunk.append(sentence)
                    current_tokens += sentence_tokens
            else:
                current_chunk.append(sentence)
                current_tokens += sentence_tokens
        
        # Add remaining chunk
        if current_chunk:
            chunk_text = '. '.join(current_chunk) + '.'
            chunks.append(chunk_text)
        
        logger.info(f"Created {len(chunks)} chunks")
        return chunks
    
    async def generate_study_notes(
        self,
        transcript: str,
        video_title: str = "Video",
        progress: Optional[Progress] = None,
        task_id: Optional[TaskID] = None
    ) -> str:
        """
        Generate study notes from transcript.
        
        Handles long transcripts by:
        1. Chunking into manageable pieces
        2. Generating notes for each chunk
        3. Using AI to combine chunks coherently
        
        Args:
            transcript: Full video transcript text
            video_title: Video title for progress display
            progress: Optional existing progress bar instance
            task_id: Optional task ID for updating progress
            
        Returns:
            Complete study notes in Markdown format
        """
        chunks = self._chunk_transcript(transcript)
        
        # Helper to update progress or print to console
        def update_status(description: str):
            if progress and task_id is not None:
                # Update the worker status text directly. 
                # Note: This relies on the worker_progress using the "{task.description}" column for status.
                # In PipelineDashboard, we map description updates to the status column area.
                short_title = (video_title[:20] + "...") if len(video_title) > 20 else video_title
                progress.update(task_id, description=f"[yellow]{short_title}[/yellow]: {description}")
            else:
                # Fallback for CLI mode without dashboard
                logger.info(f"{video_title}: {description}")

        # Single chunk - generate directly
        if len(chunks) == 1:
            update_status(f"Generating notes...")
            
            # If no progress passed, use local spinner
            if not progress:
                # Just use logger, don't create new Progress to avoid interference
                pass 
            
            notes = await self.provider.generate(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=get_single_pass_prompt(transcript)
            )
            
            if not progress:
                logger.info(f"Generated notes for {video_title}")
            return notes
        
        # Multiple chunks - generate for each, then combine
        update_status(f"Generating notes for {len(chunks)} chunks...")
        
        chunk_notes = []
        
        # Prepare iteration logic
        if not progress:
            # Use local logging instead of Progress bar to be safe
            for i, chunk in enumerate(chunks, 1):
                logger.info(f"Processing chunk {i}/{len(chunks)} for {video_title}...")
                note = await self.provider.generate(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=get_chunk_prompt(chunk)
                )
                chunk_notes.append(note)
        else:
            # Use existing progress
            for i, chunk in enumerate(chunks, 1):
                if task_id is not None:
                    short_title = (video_title[:20] + "...") if len(video_title) > 20 else video_title
                    progress.update(task_id, description=f"[yellow]{short_title}[/yellow]: Chunk {i}/{len(chunks)} (Generating)")
                
                note = await self.provider.generate(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=get_chunk_prompt(chunk)
                )
                chunk_notes.append(note)
        
        update_status(f"Combining {len(chunk_notes)} chunk notes...")
        
        final_notes = await self.provider.generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=get_combine_prompt(chunk_notes)
        )
        
        if not progress:
            logger.info(f"Completed notes for {video_title}")
            
        return final_notes
    
    async def generate_chapter_based_notes(
        self,
        chapter_transcripts: dict[str, str],
        video_title: str = "Video",
        progress: Optional[Progress] = None,
        task_id: Optional[TaskID] = None
    ) -> str:
        """
        Generate study notes using chapter-based approach.
        
        Args:
            chapter_transcripts: Dictionary mapping chapter titles to transcript text
            video_title: Video title for display
            progress: Optional existing progress bar instance
            task_id: Optional task ID for updating progress
            
        Returns:
            Complete study notes organized by chapters
        """
        from ..prompts.chapter_notes import (
            SYSTEM_PROMPT as CHAPTER_SYSTEM_PROMPT,
            get_chapter_prompt,
            get_combine_chapters_prompt,
        )
        
        # Helper to update progress or print to console
        def update_status(description: str):
            if progress and task_id is not None:
                short_title = (video_title[:20] + "...") if len(video_title) > 20 else video_title
                progress.update(task_id, description=f"[yellow]{short_title}[/yellow]: {description}")
            else:
                logger.info(f"{video_title}: {description}")

        update_status(f"Generating notes for {len(chapter_transcripts)} chapters...")
        
        chapter_notes = {}
        
        if not progress:
            # Local logging
            for i, (chapter_title, chapter_text) in enumerate(chapter_transcripts.items(), 1):
                logger.info(f"Processing chapter {i}/{len(chapter_transcripts)}: {chapter_title}...")
                notes = await self.provider.generate(
                    system_prompt=CHAPTER_SYSTEM_PROMPT,
                    user_prompt=get_chapter_prompt(chapter_title, chapter_text)
                )
                chapter_notes[chapter_title] = notes
        else:
             for i, (chapter_title, chapter_text) in enumerate(chapter_transcripts.items(), 1):
                if task_id is not None:
                    short_title = (video_title[:20] + "...") if len(video_title) > 20 else video_title
                    progress.update(task_id, description=f"[yellow]{short_title}[/yellow]: Chapter {i}/{len(chapter_transcripts)} (Generating)")
                
                notes = await self.provider.generate(
                    system_prompt=CHAPTER_SYSTEM_PROMPT,
                    user_prompt=get_chapter_prompt(chapter_title, chapter_text)
                )
                
                chapter_notes[chapter_title] = notes

        update_status(f"Combining chapter notes...")
        
        final_notes = await self.provider.generate(
            system_prompt=CHAPTER_SYSTEM_PROMPT,
            user_prompt=get_combine_chapters_prompt(chapter_notes)
        )
        
        if not progress:
            logger.info(f"Completed chapter-based notes for {video_title}")
            
        return final_notes
