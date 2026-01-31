"""Main pipeline orchestrator with concurrent processing."""

import asyncio
import logging
import re
from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, TaskID
from rich.table import Table

from ..config import config
from ..llm.generator import StudyMaterialGenerator
from ..llm.providers import get_provider
from ..prompts.chapter_notes import get_chapter_prompt

# Use main system prompt for chapters too
from ..prompts.study_notes import SYSTEM_PROMPT as CHAPTER_SYSTEM_PROMPT
from ..ui.dashboard import PipelineDashboard
from ..youtube.metadata import (
    get_playlist_info,
    get_video_chapters,
    get_video_duration,
    get_video_title,
)
from ..youtube.parser import parse_youtube_url
from ..youtube.playlist import extract_playlist_videos
from ..youtube.transcript import (
    YouTubeIPBlockError,
    fetch_transcript,
    split_transcript_by_chapters,
)


console = Console()
logger = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """
    Sanitize a string to be used as a filename.

    Args:
        name: Raw filename string.

    Returns:
        Sanitized string safe for file systems.
    """
    # Remove or replace invalid characters
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    # Replace multiple spaces with single space
    name = re.sub(r"\s+", " ", name)
    # Trim and limit length
    name = name.strip()[:100]
    return name if name else "untitled"


class PipelineOrchestrator:
    """
    Orchestrates the end-to-end pipeline for video processing.

    Manages concurrency, error handling, and UI updates.
    """

    def __init__(
        self,
        model: str = "gemini/gemini-2.0-flash",
        output_dir: Path | None = None,
        languages: list[str] | None = None,
    ):
        """
        Initialize orchestrator.

        Args:
            model: LLM model string.
            output_dir: Output directory path.
            languages: Preferred transcript languages.
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

        Returns:
            True if valid (or warning logged), False if critical missing config.
        """
        key_name = config.get_api_key_name_for_model(self.model)

        if key_name:
            import os

            if not os.environ.get(key_name):
                console.print(
                    f"\n[red bold]✗ Missing API Key for {self.model}[/red bold]"
                )
                console.print(
                    f"[yellow]Expected environment variable: {key_name}[/yellow]"
                )
                console.print(
                    "[dim]Please check your .env file or run:[/dim] "
                    "[cyan]yt-study setup[/cyan]\n"
                )
                return False

        return True

    async def process_video(
        self,
        video_id: str,
        output_path: Path,
        progress: Progress | None = None,
        task_id: TaskID | None = None,
        video_title: str | None = None,
        is_playlist: bool = False,
    ) -> bool:
        """
        Process a single video: fetch transcript and generate study notes.

        Args:
            video_id: YouTube Video ID.
            output_path: Destination path for the MD file.
            progress: Rich Progress instance.
            task_id: Rich TaskID.
            video_title: Pre-fetched title (optional).
            is_playlist: Whether this is part of a playlist (affects UI logging).

        Returns:
            True on success, False on failure.
        """
        async with self.semaphore:
            local_task_id = task_id

            # If standalone (not part of worker pool), create a specific
            # bar if requested
            if is_playlist and progress and task_id is None:
                display_title = (video_title or video_id)[:30]
                local_task_id = progress.add_task(
                    description=f"[cyan]⏳ {display_title}... (Waiting)[/cyan]",
                    total=None,
                )

            try:
                # 1. Fetch Metadata
                if not video_title:
                    # Run in thread to avoid blocking
                    video_title = await asyncio.to_thread(get_video_title, video_id)

                # Fetch duration and chapters concurrently
                duration, chapters = await asyncio.gather(
                    asyncio.to_thread(get_video_duration, video_id),
                    asyncio.to_thread(get_video_chapters, video_id),
                )

                title_display = (video_title or video_id)[:40]

                if progress and local_task_id is not None:
                    progress.update(
                        local_task_id,
                        description=f"[cyan]📥 {title_display}... (Transcript)[/cyan]",
                    )

                # 2. Fetch Transcript
                transcript_obj = await fetch_transcript(video_id, self.languages)

                # 3. Determine Generation Strategy
                # Use chapters if video is long (>1h) and chapters exist
                use_chapters = duration > 3600 and len(chapters) > 0 and not is_playlist

                if use_chapters:
                    if progress and local_task_id is not None:
                        progress.update(
                            local_task_id,
                            description=(
                                f"[cyan]📖 {title_display}... (Chapters)[/cyan]"
                            ),
                        )
                    # else block removed as redundant

                    # Split transcript
                    chapter_transcripts = split_transcript_by_chapters(
                        transcript_obj, chapters
                    )

                    # Create folder for chapter notes
                    safe_title = sanitize_filename(video_title)
                    output_folder = self.output_dir / safe_title
                    output_folder.mkdir(parents=True, exist_ok=True)

                    # Generate chapter notes
                    # Fix: Iterate here and call generator for each chapter
                    # to save individually

                    for i, (chap_title, chap_text) in enumerate(
                        chapter_transcripts.items(), 1
                    ):
                        status_msg = f"Chapter {i}/{len(chapter_transcripts)}"
                        if progress and local_task_id is not None:
                            progress.update(
                                local_task_id,
                                description=(
                                    f"[cyan]🤖 {title_display}... ({status_msg})[/cyan]"
                                ),
                            )

                        notes = await self.generator.provider.generate(
                            system_prompt=CHAPTER_SYSTEM_PROMPT,
                            user_prompt=get_chapter_prompt(chap_title, chap_text),
                        )

                        # Save individual chapter
                        safe_chapter = sanitize_filename(chap_title)
                        chapter_file = output_folder / f"{i:02d}_{safe_chapter}.md"
                        chapter_file.write_text(notes, encoding="utf-8")

                    if progress and local_task_id is not None:
                        progress.update(
                            local_task_id,
                            description=f"[green]✓ {title_display} (Done)[/green]",
                            completed=True,
                        )

                    return True

                else:
                    # Single file generation
                    transcript_text = transcript_obj.to_text()

                    if progress and local_task_id is not None:
                        progress.update(
                            local_task_id,
                            description=(
                                f"[cyan]🤖 {title_display}... (Generating)[/cyan]"
                            ),
                        )

                    notes = await self.generator.generate_study_notes(
                        transcript_text,
                        video_title=title_display,
                        progress=progress,
                        task_id=local_task_id,
                    )

                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(notes, encoding="utf-8")

                    if progress and local_task_id is not None:
                        progress.update(
                            local_task_id,
                            description=f"[green]✓ {title_display} (Done)[/green]",
                            completed=True,
                        )

                    return True

            except Exception as e:
                logger.error(f"Failed to process {video_id}: {e}")

                err_msg = str(e)
                if isinstance(e, YouTubeIPBlockError) or (
                    "blocking requests" in err_msg
                ):
                    err_display = "[bold red]IP BLOCKED[/bold red]"
                    console.print(
                        Panel(
                            "[bold red]🚫 YouTube IP Block Detected[/bold red]\n\n"
                            "YouTube is limiting requests from your IP address.\n"
                            "[yellow]➤ Recommendation:[/yellow] Use a VPN or "
                            "wait ~1 hour.",
                            border_style="red",
                        )
                    )
                else:
                    err_display = "(Failed)"

                if progress and local_task_id is not None:
                    progress.update(
                        local_task_id,
                        description=(
                            f"[red]✗ {(video_title or video_id)[:20]}... "
                            f"{err_display}[/red]"
                        ),
                        visible=True,
                    )

                return False

    async def _process_with_dashboard(
        self,
        video_ids: list[str],
        playlist_name: str = "Queue",
        is_single_video: bool = False,
    ) -> int:
        """Process a list of videos using the Advanced Dashboard UI."""
        from ..ui.dashboard import PipelineDashboard

        # Initialize Dashboard FIRST to capture all output
        # Adjust concurrency display: if total_videos < max_concurrency,
        # only show needed workers
        actual_concurrency = min(len(video_ids), config.max_concurrent_videos)

        dashboard = PipelineDashboard(
            total_videos=len(video_ids),
            concurrency=actual_concurrency,
            playlist_name=playlist_name,
            model_name=self.model,
        )

        success_count = 0
        video_titles = {}

        # Run Live Display (inline, not full screen)
        # We start it immediately to show "Fetching metadata..." state
        with Live(dashboard, refresh_per_second=10, console=console, screen=False):
            # --- Phase 1: Metadata Fetching ---
            TITLE_FETCH_CONCURRENCY = 10
            if not is_single_video:
                dashboard.update_overall_status(
                    f"[cyan]📋 Fetching metadata for {len(video_ids)} videos...[/cyan]"
                )

            title_semaphore = asyncio.Semaphore(TITLE_FETCH_CONCURRENCY)

            async def fetch_title_safe(vid: str) -> str:
                async with title_semaphore:
                    try:
                        return await asyncio.to_thread(get_video_title, vid)
                    except Exception:
                        return vid

            # Fetch titles
            titles = await asyncio.gather(*(fetch_title_safe(vid) for vid in video_ids))
            video_titles = dict(zip(video_ids, titles, strict=True))

            # --- Phase 2: Processing ---
            if not is_single_video:
                dashboard.update_overall_status("[bold blue]Total Progress[/bold blue]")

            # Determine base output folder
            if is_single_video:
                base_folder = self.output_dir
            else:
                base_folder = self.output_dir / sanitize_filename(playlist_name)
                base_folder.mkdir(parents=True, exist_ok=True)

            # Worker Queue Implementation
            queue: asyncio.Queue[str] = asyncio.Queue()
            for vid in video_ids:
                queue.put_nowait(vid)

            async def worker(worker_idx: int, task_id: TaskID) -> None:
                nonlocal success_count
                while not queue.empty():
                    try:
                        video_id = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                    title = video_titles.get(video_id, video_id)
                    safe_title = sanitize_filename(title)

                    if is_single_video:
                        video_folder = base_folder / safe_title
                        output_path = video_folder / f"{safe_title}.md"
                    else:
                        output_path = base_folder / f"{safe_title}.md"

                    # Update status
                    dashboard.update_worker(
                        worker_idx, f"[yellow]{title[:30]}...[/yellow]"
                    )

                    try:
                        result = await self.process_video(
                            video_id,
                            output_path,
                            progress=dashboard.worker_progress,
                            task_id=task_id,
                            video_title=title,
                            is_playlist=True,
                        )

                        if result:
                            success_count += 1
                            dashboard.add_completion(title)
                        else:
                            dashboard.add_failure(title)

                    except Exception as e:
                        logger.error(f"Worker {worker_idx} failed on {video_id}: {e}")
                        dashboard.update_worker(worker_idx, f"[red]Error: {e}[/red]")
                        dashboard.add_failure(title)
                        await asyncio.sleep(2)
                    finally:
                        queue.task_done()

                # Worker done
                dashboard.update_worker(worker_idx, "[dim]Idle[/dim]")

            try:
                workers = [
                    asyncio.create_task(worker(i, dashboard.worker_tasks[i]))
                    for i in range(actual_concurrency)
                ]
                await asyncio.gather(*workers)
            except Exception as e:
                logger.error(f"Dashboard execution failed: {e}")

        # Print summary table after dashboard closes
        self._print_summary(dashboard)

        return success_count

    def _print_summary(self, dashboard: "PipelineDashboard") -> None:
        """Print a summary table of the run."""
        if not dashboard.recent_completions and not dashboard.recent_failures:
            return

        summary_table = Table(
            title="📊 Processing Summary",
            border_style="cyan",
            show_header=True,
            header_style="bold magenta",
        )
        summary_table.add_column("Status", justify="center")
        summary_table.add_column("Video Title", style="dim")

        # Add failures first (more important)
        if dashboard.recent_failures:
            for fail in dashboard.recent_failures:
                summary_table.add_row("[bold red]FAILED[/bold red]", fail)

        # Add successes
        if dashboard.recent_completions:
            for comp in dashboard.recent_completions:
                summary_table.add_row("[green]SUCCESS[/green]", comp)

        console.print("\n")
        console.print(summary_table)
        console.print(
            f"\n[bold]Total Completed:[/bold] "
            f"{dashboard.overall_progress.tasks[0].completed}/"
            f"{dashboard.overall_progress.tasks[0].total}"
        )
        console.print("[dim]Check logs for detailed error reports.[/dim]\n")

    async def process_playlist(
        self, playlist_id: str, playlist_name: str = "playlist"
    ) -> int:
        """Process playlist with concurrent dynamic progress bars."""
        video_ids = await extract_playlist_videos(playlist_id)
        return await self._process_with_dashboard(video_ids, playlist_name)

    async def run(self, url: str) -> None:
        """
        Run the pipeline for a given YouTube URL.

        Args:
            url: YouTube video or playlist URL.
        """
        # Validate Provider Credentials
        if not self.validate_provider():
            return

        try:
            # Parse URL
            parsed = parse_youtube_url(url)

            if parsed.url_type == "video":
                if not parsed.video_id:
                    console.print("[red]Error: Video ID could not be extracted[/red]")
                    return

                await self._process_with_dashboard(
                    [parsed.video_id],
                    playlist_name="Single Video",
                    is_single_video=True,
                )

                # Summary is already printed by _process_with_dashboard

            elif parsed.url_type == "playlist":
                if not parsed.playlist_id:
                    console.print(
                        "[red]Error: Playlist ID could not be extracted[/red]"
                    )
                    return

                # Fetch basic playlist info first - handled in dashboard now
                # if needed or kept minimal. Actually, playlist title fetching
                # is useful to show BEFORE starting but _process_with_dashboard
                # fetches metadata anyway.
                # However, to pass playlist_name to dashboard, we might want it.
                # But waiting for title can be slow.
                # Let's let the dashboard handle titles for videos.
                # For playlist title, we can try fast fetch or default to ID.

                # Fetching playlist title here is blocking/slow if not careful.
                # Let's just use ID as name initially or fetch it quickly.
                # The original code did fetch it.

                # To reduce redundancy, we remove the print statement
                # "Playlist: ..."
                playlist_title, _ = await asyncio.to_thread(
                    get_playlist_info, parsed.playlist_id
                )

                # Removed redundant print:
                # console.print(f"[cyan]📑 Playlist:[/cyan] {playlist_title}\n")

                await self.process_playlist(parsed.playlist_id, playlist_title)

                # Summary handled by dashboard

        except ValueError as e:
            console.print(f"[red]Input Error: {e}[/red]")
        except Exception as e:
            console.print(f"[red]Unexpected Error: {e}[/red]")
            logger.exception("Pipeline run failed")
