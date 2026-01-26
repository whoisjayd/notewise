"""Study material generator with chunking and combining logic."""

import logging
import tiktoken
from typing import List

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

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
        self.tokenizer = tiktoken.get_encoding("cl100k_base")  # GPT-4 tokenizer
        
    def _count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return len(self.tokenizer.encode(text))
    
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
        
        console.print(f"[cyan]📊 Transcript: {token_count:,} tokens, chunking...[/cyan]")
        
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
        
        console.print(f"[green]✓ Created {len(chunks)} chunks[/green]")
        return chunks
    
    async def generate_study_notes(self, transcript: str, video_title: str = "Video") -> str:
        """
        Generate study notes from transcript.
        
        Handles long transcripts by:
        1. Chunking into manageable pieces
        2. Generating notes for each chunk
        3. Using AI to combine chunks coherently
        
        Args:
            transcript: Full video transcript text
            video_title: Video title for progress display
            
        Returns:
            Complete study notes in Markdown format
        """
        chunks = self._chunk_transcript(transcript)
        
        # Single chunk - generate directly
        if len(chunks) == 1:
            console.print(f"[cyan]Generating study notes for {video_title}...[/cyan]")
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                progress.add_task(description="Generating notes...", total=None)
                
                notes = await self.provider.generate(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=get_single_pass_prompt(transcript)
                )
            
            console.print(f"[green]✓ Generated study notes[/green]")
            return notes
        
        # Multiple chunks - generate for each, then combine
        console.print(f"[cyan]Generating notes for {len(chunks)} chunks...[/cyan]")
        
        chunk_notes = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(
                description=f"Processing chunks...",
                total=len(chunks)
            )
            
            for i, chunk in enumerate(chunks, 1):
                progress.update(task, description=f"Generating notes for chunk {i}/{len(chunks)}...")
                
                note = await self.provider.generate(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=get_chunk_prompt(chunk)
                )
                
                chunk_notes.append(note)
                progress.advance(task)
        
        console.print(f"[cyan]Combining {len(chunk_notes)} chunk notes...[/cyan]")
        
        # Combine all chunk notes using AI
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            progress.add_task(description="Combining into final document...", total=None)
            
            final_notes = await self.provider.generate(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=get_combine_prompt(chunk_notes)
            )
        
        console.print(f"[green]✓ Generated complete study notes[/green]")
        return final_notes
    
    async def generate_chapter_based_notes(
        self,
        chapter_transcripts: dict[str, str],
        video_title: str = "Video"
    ) -> str:
        """
        Generate study notes using chapter-based approach.
        
        Args:
            chapter_transcripts: Dictionary mapping chapter titles to transcript text
            video_title: Video title for display
            
        Returns:
            Complete study notes organized by chapters
        """
        from ..prompts.chapter_notes import (
            SYSTEM_PROMPT as CHAPTER_SYSTEM_PROMPT,
            get_chapter_prompt,
            get_combine_chapters_prompt,
        )
        
        console.print(f"[cyan]📚 Generating notes for {len(chapter_transcripts)} chapters...[/cyan]")
        
        chapter_notes = {}
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(
                description="Processing chapters...",
                total=len(chapter_transcripts)
            )
            
            for i, (chapter_title, chapter_text) in enumerate(chapter_transcripts.items(), 1):
                progress.update(task, description=f"Chapter {i}/{len(chapter_transcripts)}: {chapter_title[:30]}...")
                
                notes = await self.provider.generate(
                    system_prompt=CHAPTER_SYSTEM_PROMPT,
                    user_prompt=get_chapter_prompt(chapter_title, chapter_text)
                )
                
                chapter_notes[chapter_title] = notes
                progress.advance(task)
        
        console.print(f"[cyan]Combining chapter notes...[/cyan]")
        
        # Combine all chapter notes
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            progress.add_task(description="Creating final document...", total=None)
            
            final_notes = await self.provider.generate(
                system_prompt=CHAPTER_SYSTEM_PROMPT,
                user_prompt=get_combine_chapters_prompt(chapter_notes)
            )
        
        console.print(f"[green]✓ Generated chapter-based study notes[/green]")
        return final_notes
