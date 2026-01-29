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
        
    def validate_provider(self) -> bool:
        """
        Validate that the API key for the selected provider is set.
        Returns True if valid, False otherwise.
        """
        import os
        model = self.model.lower()
        key_map = {
            "gemini": "GEMINI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "claude": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "gpt": "OPENAI_API_KEY",
            "groq": "GROQ_API_KEY",
            "mistral": "MISTRAL_API_KEY",
            "xai": "XAI_API_KEY",
            "grok": "XAI_API_KEY",
        }
        
        required_var = None
        for prefix, var_name in key_map.items():
            if prefix in model:
                required_var = var_name
                break
        
        if required_var:
            if not os.environ.get(required_var):
                console.print(f"\n[red bold]✗ Missing API Key for {self.model}[/red bold]")
                console.print(f"[yellow]Expected environment variable: {required_var}[/yellow]")
                console.print(f"[dim]Please check your .env file or run:[/dim] [cyan]yt-study setup[/cyan]\n")
                return False
                
        return True
        
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
        """
        async with self.semaphore:
            # Create a task for this video if running in a playlist (is_playlist=True)
            # If standalone, we use the progress passed in or None
            local_task_id = task_id
            
            if is_playlist and progress:
                # Create a specific bar for this video
                display_title = (video_title or video_id)[:30]
                local_task_id = progress.add_task(
                    description=f"[cyan]⏳ {display_title}... (Waiting)[/cyan]", 
                    total=None
                )

            try:
                # Fetch dictionary metadata
                if not video_title:
                    from ..youtube.metadata import get_video_title, get_video_duration, get_video_chapters
                    video_title = get_video_title(video_id)
                    duration = get_video_duration(video_id)
                    chapters = get_video_chapters(video_id)
                else:
                    from ..youtube.metadata import get_video_duration, get_video_chapters
                    duration = get_video_duration(video_id)
                    chapters = get_video_chapters(video_id)
                
                title_display = (video_title or video_id)[:40]
                
                if progress and local_task_id is not None:
                    progress.update(local_task_id, description=f"[cyan]📥 {title_display}... (Transcript)[/cyan]")
                
                # Fetch transcript
                transcript_obj = await fetch_transcript(video_id, self.languages)
                
                # Determine generation strategy
                use_chapters = duration > 3600 and len(chapters) > 0 and not is_playlist
                
                if use_chapters:
                    if progress and local_task_id is not None:
                        progress.update(local_task_id, description=f"[cyan]📖 {title_display}... (Chapters)[/cyan]")
                    else:
                        console.print(f"[cyan]📖 Detected {len(chapters)} chapters[/cyan]")

                    # Split transcript
                    from ..youtube.transcript import split_transcript_by_chapters
                    chapter_transcripts = split_transcript_by_chapters(transcript_obj, chapters)
                    
                    # Generate per chapter
                    from ..prompts.chapter_notes import SYSTEM_PROMPT as CHAPTER_SYSTEM_PROMPT, get_chapter_prompt
                    
                    safe_title = sanitize_filename(video_title)
                    output_folder = self.output_dir / safe_title
                    output_folder.mkdir(parents=True, exist_ok=True)
                    
                    # If we are in a playlist, we don't want a nested Live progress. 
                    # If standalone, we can use one.
                    # Simplified: Just update the main bar with "Chapter X/Y"
                    
                    for i, (chapter_title, chapter_text) in enumerate(chapter_transcripts.items(), 1):
                        status_msg = f"Chapter {i}/{len(chapter_transcripts)}"
                        if progress and local_task_id is not None:
                            progress.update(local_task_id, description=f"[cyan]🤖 {title_display}... ({status_msg})[/cyan]")
                        elif not is_playlist:
                             console.print(f"[cyan]  Processing {status_msg}...[/cyan]")

                        notes = await self.generator.provider.generate(
                            system_prompt=CHAPTER_SYSTEM_PROMPT,
                            user_prompt=get_chapter_prompt(chapter_title, chapter_text)
                        )
                        
                        safe_chapter = sanitize_filename(chapter_title)
                        chapter_file = output_folder / f"{i:02d}_{safe_chapter}.md"
                        chapter_file.write_text(notes, encoding='utf-8')
                    
                    if progress and local_task_id is not None:
                         progress.update(local_task_id, description=f"[green]✓ {title_display} (Done)[/green]", completed=True)
                         if is_playlist:
                             # Keep it visible for a moment or just hide it
                             progress.update(local_task_id, visible=False)
                    else:
                        console.print(f"[green]✓[/green] {video_title} ({len(chapters)} chapters)")

                    return True
                    
                else:
                    # Single file
                    transcript_text = transcript_obj.to_text()
                    
                    if progress and local_task_id is not None:
                        progress.update(local_task_id, description=f"[cyan]🤖 {title_display}... (Generating)[/cyan]")
                    
                    notes = await self.generator.generate_study_notes(transcript_text, video_title=video_title)
                    
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(notes, encoding='utf-8')
                    
                    if progress and local_task_id is not None:
                         progress.update(local_task_id, description=f"[green]✓ {title_display} (Done)[/green]", completed=True)
                         if is_playlist:
                             progress.update(local_task_id, visible=False)
                    else:
                         console.print(f"[green]✓[/green] {video_title}")

                    return True
                
            except Exception as e:
                logger.error(f"Failed to process {video_id}: {e}")
                if progress and local_task_id is not None:
                    progress.update(local_task_id, description=f"[red]✗ {(video_title or video_id)[:20]}... (Failed)[/red]", visible=True)
                    # Don't hide failed tasks immediately so user sees them
                else:
                    console.print(f"[red]✗ {video_title or video_id}[/red]: {str(e)}")
                return False

    async def process_playlist(self, playlist_id: str, playlist_name: str = "playlist") -> int:
        """Process playlist with concurrent dynamic progress bars."""
        video_ids = await extract_playlist_videos(playlist_id)
        
        # Pre-fetch titles concurrently
        from ..youtube.metadata import get_video_title
        
        TITLE_FETCH_CONCURRENCY = 10
        console.print(f"[cyan]📋 Fetching titles for {len(video_ids)} videos (max {TITLE_FETCH_CONCURRENCY} at a time)...[/cyan]")
        
        title_semaphore = asyncio.Semaphore(TITLE_FETCH_CONCURRENCY)
        
        async def fetch_title_safe(vid):
            async with title_semaphore:
                try:
                    return await asyncio.to_thread(get_video_title, vid)
                except Exception:
                    return vid
                
        titles = await asyncio.gather(*(fetch_title_safe(vid) for vid in video_ids))
        video_titles = dict(zip(video_ids, titles))
        
        output_folder = self.output_dir / sanitize_filename(playlist_name)
        output_folder.mkdir(parents=True, exist_ok=True)
        
        console.print(f"\n[cyan]⚡ Processing {len(video_ids)} videos (max {config.max_concurrent_videos} concurrent)[/cyan]\n")
        
        tasks = []
        
        with Progress(
            SpinnerColumn(),
            BarColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            
            main_task = progress.add_task(f"[bold]Playlist Progress[/bold]", total=len(video_ids))
            
            for i, video_id in enumerate(video_ids, 1):
                title = video_titles.get(video_id, video_id)
                safe_title = sanitize_filename(title)
                output_path = output_folder / f"{safe_title}.md"
                
                # Wrapper to advance main progress bar
                async def process_wrapper(vid=video_id, path=output_path, t=title):
                    res = await self.process_video(
                        vid,
                        path,
                        progress=progress,
                        task_id=None, # process_video will create a new task
                        video_title=t,
                        is_playlist=True
                    )
                    progress.advance(main_task)
                    return res
                
                tasks.append(process_wrapper())
            
            # Execute all tasks concurrently (limited by semaphore inside process_video)
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
        success_count = 0
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"Playlist task failed with exception: {r}")
            elif r is True:
                success_count += 1
                
        return success_count
    
    async def run(self, url: str) -> None:
        """
        Run the pipeline for a given YouTube URL.
        
        Args:
            url: YouTube video or playlist URL
        """
        console.print(f"\n[bold cyan]🎓 YouTube Study Material Pipeline[/bold cyan]")
        console.print(f"[dim]Model: {self.model}[/dim]\n")

        # Validate Provider Credentials
        if not self.validate_provider():
            return
        
        # Parse URL
        parsed = parse_youtube_url(url)
        
        if parsed.url_type == 'video':
            if not parsed.video_id:
                console.print("[red]Error: Video ID could not be extracted[/red]")
                return

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
            if not parsed.playlist_id:
                console.print("[red]Error: Playlist ID could not be extracted[/red]")
                return

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
