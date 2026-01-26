"""Main pipeline orchestrator with concurrent processing."""

import asyncio
import logging
import re
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.progress import Progress, TaskID, TextColumn, BarColumn, TimeRemainingColumn

from ..config import config
from ..llm.generator import StudyMaterialGenerator
from ..llm.providers import get_provider
from ..youtube.parser import parse_youtube_url
from ..youtube.playlist import extract_playlist_videos
from ..youtube.transcript import fetch_transcript

console = Console()
logger = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """Sanitize a string to be used as a filename."""
    # Remove or replace invalid characters
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    # Replace multiple spaces with single space
    name = re.sub(r'\s+', ' ', name)
    # Trim and limit length
    name = name.strip()[:100]
    return name if name else "untitled"


class PipelineOrchestrator:
    """Orchestrates the end-to-end pipeline for video processing."""
    
    def __init__(
        self,
        model: str = "gemini/gemini-2.0-flash",
        output_dir: Optional[Path] = None,
        languages: Optional[List[str]] = None
    ):
        """
        Initialize orchestrator.
        
        Args:
            model: LLM model string
            output_dir: Output directory path
            languages: Preferred transcript languages
        """
        self.model = model
        self.output_dir = output_dir or config.default_output_dir
        self.languages = languages or config.default_languages
        self.provider = get_provider(model)
        self.generator = StudyMaterialGenerator(self.provider)
        self.semaphore = asyncio.Semaphore(config.max_concurrent_videos)
        
    async def process_video(
        self,
        video_id: str,
        output_path: Path,
        progress: Optional[Progress] = None,
        task_id: Optional[TaskID] = None,
        video_title: Optional[str] = None,
        is_playlist: bool = False
    ) -> bool:
        """
        Process a single video: fetch transcript and generate study notes.
        
        For chaptered videos (>1 hour), creates separate files per chapter.
        
        Args:
            video_id: YouTube video ID
            output_path: Base path for output
            progress: Optional Rich Progress instance
            task_id: Optional task ID for progress tracking
            video_title: Optional video title for display
            is_playlist: Whether this video is part of a playlist
            
        Returns:
            True if successful, False otherwise
        """
        async with self.semaphore:
            try:
                # Fetch video metadata
                if not video_title:
                    from ..youtube.metadata import get_video_title, get_video_duration, get_video_chapters
                    video_title = get_video_title(video_id)
                    duration = get_video_duration(video_id)
                    chapters = get_video_chapters(video_id)
                else:
                    from ..youtube.metadata import get_video_duration, get_video_chapters
                    duration = get_video_duration(video_id)
                    chapters = get_video_chapters(video_id)
                
                if progress and task_id is not None:
                    progress.update(task_id, description=f"[cyan]📥 {video_title[:40]}...[/cyan]")
                
                # Fetch transcript
                transcript_obj = await fetch_transcript(video_id, self.languages)
                
                # Determine generation strategy
                use_chapters = duration > 3600 and len(chapters) > 0 and not is_playlist  # >1 hour with chapters, not in playlist
                
                if use_chapters:
                    console.print(f"[cyan]📖 Detected {len(chapters)} chapters (video duration: {duration//60}min)[/cyan]")
                    console.print(f"[cyan]Using chapter-based generation → separate files per chapter[/cyan]")
                    
                    # Split transcript by chapters
                    from ..youtube.transcript import split_transcript_by_chapters
                    chapter_transcripts = split_transcript_by_chapters(transcript_obj, chapters)
                    
                    if progress and task_id is not None:
                        progress.update(task_id, description=f"[cyan]🤖 {video_title[:40]}... (chapters)[/cyan]")
                    
                    # Generate notes for each chapter and save separately
                    from ..prompts.chapter_notes import (
                        SYSTEM_PROMPT as CHAPTER_SYSTEM_PROMPT,
                        get_chapter_prompt,
                    )
                    
                    # Chaptered video: output/VideoTitle/01_ChapterName.md
                    safe_title = sanitize_filename(video_title)
                    output_folder = self.output_dir / safe_title
                    output_folder.mkdir(parents=True, exist_ok=True)
                    
                    console.print(f"[cyan]📚 Generating notes for {len(chapter_transcripts)} chapters...[/cyan]")
                    
                    from rich.progress import Progress as RichProgress, SpinnerColumn, TextColumn
                    
                    with RichProgress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        console=console
                    ) as ch_progress:
                        ch_task = ch_progress.add_task(
                            description="Processing chapters...",
                            total=len(chapter_transcripts)
                        )
                        
                        for i, (chapter_title, chapter_text) in enumerate(chapter_transcripts.items(), 1):
                            ch_progress.update(ch_task, description=f"Chapter {i}/{len(chapter_transcripts)}: {chapter_title[:30]}...")
                            
                            notes = await self.generator.provider.generate(
                                system_prompt=CHAPTER_SYSTEM_PROMPT,
                                user_prompt=get_chapter_prompt(chapter_title, chapter_text)
                            )
                            
                            # Save individual chapter file
                            safe_chapter = sanitize_filename(chapter_title)
                            chapter_file = output_folder / f"{i:02d}_{safe_chapter}.md"
                            chapter_file.write_text(notes, encoding='utf-8')
                            
                            ch_progress.advance(ch_task)
                    
                    console.print(f"[green]✓[/green] {video_title} ({len(chapters)} chapters)")
                    console.print(f"  [dim]→ {output_folder}[/dim]")
                    return True
                    
                else:
                    # Regular single-file generation
                    transcript_text = transcript_obj.to_text()
                    
                    if progress and task_id is not None:
                        progress.update(task_id, description=f"[cyan]🤖 {video_title[:40]}...[/cyan]")
                    
                    # Generate regular notes
                    notes = await self.generator.generate_study_notes(
                        transcript_text,
                        video_title=video_title
                    )
                    
                    # Save to file
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(notes, encoding='utf-8')
                    
                    if progress and task_id is not None:
                        progress.update(task_id, description=f"[green]✓ {video_title[:40]}...[/green]")
                    
                    console.print(f"[green]✓[/green] {video_title}")
                    console.print(f"  [dim]→ {output_path}[/dim]")
                    return True
                
            except Exception as e:
                logger.error(f"Failed to process video {video_id}: {e}")
                title_display = video_title or video_id
                console.print(f"[red]✗ {title_display[:50]}[/red]")
                console.print(f"  [dim red]{str(e)}[/dim red]")
                if progress and task_id is not None:
                    progress.update(task_id, description=f"[red]✗ {title_display[:40]}...[/red]")
                return False
    
    async def process_playlist(self, playlist_id: str, playlist_name: str = "playlist") -> int:
        """
        Process all videos in a playlist with concurrent processing.
        
        Args:
            playlist_id: YouTube playlist ID
            playlist_name: Name for the output folder
            
        Returns:
            Number of successfully processed videos
        """
        # Extract video IDs
        video_ids = await extract_playlist_videos(playlist_id)
        
        # Fetch actual titles for all videos
        from ..youtube.metadata import get_video_title
        console.print(f"[cyan]📋 Fetching video titles...[/cyan]")
        video_titles = {}
        for video_id in video_ids:
            video_titles[video_id] = get_video_title(video_id)
        
        # Create output directory
        output_folder = self.output_dir / sanitize_filename(playlist_name)
        output_folder.mkdir(parents=True, exist_ok=True)
        
        console.print(f"\n[cyan]⚡ Processing {len(video_ids)} videos (max {config.max_concurrent_videos} concurrent)[/cyan]\n")
        
        # Create tasks for concurrent processing
        tasks = []
        
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            overall_task = progress.add_task(
                description="Overall progress",
                total=len(video_ids)
            )
            
            for video_id in video_ids:
                title = video_titles.get(video_id, video_id)
                safe_title = sanitize_filename(title)
                # Playlist: PlaylistName/VideoTitle.md
                output_path = output_folder / f"{safe_title}.md"
                
                task = self.process_video(
                    video_id,
                    output_path,
                    progress,
                    overall_task,
                    video_title=title,
                    is_playlist=True  # Mark as playlist video
                )
                tasks.append(task)
            
            # Process all videos
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Count successes
            success_count = sum(1 for r in results if r is True)
            
        console.print(f"\n[green]✓ {success_count}/{len(video_ids)} videos processed successfully[/green]")
        console.print(f"[cyan]📁 Output:[/cyan] {output_folder}")
        
        return success_count
    
    async def run(self, url: str) -> None:
        """
        Run the pipeline for a given YouTube URL.
        
        Args:
            url: YouTube video or playlist URL
        """
        console.print(f"\n[bold cyan]🎓 YouTube Study Material Pipeline[/bold cyan]")
        console.print(f"[dim]Model: {self.model}[/dim]\n")
        
        # Parse URL
        parsed = parse_youtube_url(url)
        
        if parsed.url_type == 'video':
            # Single video: output/VideoTitle/VideoTitle.md
            from ..youtube.metadata import get_video_title
            video_title = get_video_title(parsed.video_id)
            
            console.print(f"[cyan]📹 Video:[/cyan] {video_title}\n")
            
            safe_title = sanitize_filename(video_title)
            output_folder = self.output_dir / safe_title
            output_path = output_folder / f"{safe_title}.md"
            
            success = await self.process_video(parsed.video_id, output_path, video_title=video_title, is_playlist=False)
            
            if success:
                console.print(f"\n[green]✓ Pipeline completed successfully![/green]")
            else:
                console.print(f"\n[red]✗ Pipeline failed[/red]")
                
        elif parsed.url_type == 'playlist':
            # Playlist: output/PlaylistName/VideoTitle.md
            from ..youtube.metadata import get_playlist_info
            playlist_title, _ = get_playlist_info(parsed.playlist_id)
            
            console.print(f"[cyan]📑 Playlist:[/cyan] {playlist_title}\n")
            
            success_count = await self.process_playlist(
                parsed.playlist_id,
                playlist_title
            )
            
            if success_count > 0:
                console.print(f"\n[green]✓ Pipeline completed![/green]")
            else:
                console.print(f"\n[red]✗ All videos failed[/red]")
