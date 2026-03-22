"""
Dashboard UI component for pipeline visualization.

Handles the rendering of progress bars, worker status, and completion logs
using Rich's Live display capabilities.
"""

from collections import deque

from rich.console import Group, RenderableType
from rich.markup import escape
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.rule import Rule
from rich.table import Table
from rich.text import Text


class PipelineDashboard:
    """
    Manages the TUI dashboard state and rendering.

    Provides a visual overview of:
    - Overall playlist progress
    - Individual worker threads status
    - Recent completions
    - Failures
    """

    @staticmethod
    def _truncate_title(title: str, *, limit: int) -> str:
        """Clamp long titles to a UI-friendly width using a single ellipsis."""
        return f"{title[:limit]}…" if len(title) > limit else title

    def __init__(
        self,
        total_videos: int,
        concurrency: int,
        playlist_name: str,
        model_name: str,
        chapter_concurrency: int = 0,
    ):
        """
        Initialize the dashboard.

        Args:
            total_videos: Total number of items to process.
            concurrency: Number of parallel workers.
            playlist_name: Name of the current batch/playlist.
            model_name: The LLM model in use.
        """
        self.playlist_name = playlist_name
        self.model_name = model_name
        self.chapter_concurrency = max(0, chapter_concurrency)
        self.recent_completions: deque[str] = deque(maxlen=3)
        self.recent_failures: deque[str] = deque(maxlen=3)
        self.skipped_count = 0
        self.completed_count = 0
        self.failed_count = 0

        # 1. Overall Progress Bar
        self.overall_progress = Progress(
            TextColumn("[bold blue]Total Progress"),
            BarColumn(
                bar_width=40,
                style="black",
                complete_style="green",
                finished_style="green",
            ),
            TextColumn("[bold green]{task.percentage:>3.0f}%"),
            TextColumn("•"),
            TextColumn("[bold white]{task.completed}/{task.total}"),
            TextColumn("•"),
            TimeElapsedColumn(),
            expand=True,
        )
        self.overall_task = self.overall_progress.add_task("", total=total_videos)

        # 2. Worker Progress Bars
        self.worker_progress = Progress(
            TextColumn("[bold cyan]{task.fields[label]}[/bold cyan]"),
            SpinnerColumn(),
            TextColumn("{task.description}"),
            expand=True,
        )

        self.worker_tasks: list[TaskID] = []
        for i in range(concurrency):
            prefix = "└──" if i == concurrency - 1 else "├──"
            tid = self.worker_progress.add_task(
                "[dim]Idle[/dim]", label=f"{prefix} Worker {i + 1}", worker_id=i + 1
            )
            self.worker_tasks.append(tid)

        # 3. Chapter worker progress bars, partitioned under each video worker.
        self.chapter_progress = Progress(
            TextColumn("[bold magenta]{task.fields[label]}[/bold magenta]"),
            SpinnerColumn(),
            TextColumn("{task.description}"),
            expand=True,
        )
        self.chapter_tasks: list[TaskID] = []
        self._chapter_slot_keys: list[str | None] = []
        self._chapter_slot_video_ids: list[str | None] = []
        for chapter_index in range(self.chapter_concurrency):
            prefix = "└──" if chapter_index == self.chapter_concurrency - 1 else "├──"
            task_id = self.chapter_progress.add_task(
                "[dim]Idle[/dim]",
                label=f"{prefix} Worker {chapter_index + 1}",
                chapter_slot=chapter_index + 1,
            )
            self.chapter_tasks.append(task_id)
            self._chapter_slot_keys.append(None)
            self._chapter_slot_video_ids.append(None)

    def _set_task_description(
        self,
        progress: Progress,
        task_id: TaskID,
        status: str,
    ) -> None:
        """Apply one worker description update."""
        progress.update(task_id, description=status)

    def _chapter_slot_index(self, chapter_key: str) -> int | None:
        """Return the assigned slot index for one active chapter key."""
        try:
            return self._chapter_slot_keys.index(chapter_key)
        except ValueError:
            return None

    def _first_free_chapter_slot(self) -> int | None:
        """Return the first available chapter slot index."""
        try:
            return self._chapter_slot_keys.index(None)
        except ValueError:
            return None

    def update_worker(self, index: int, status: str) -> None:
        """
        Update a specific worker's status text.

        Args:
            index: Worker index (0-based).
            status: New status text.
        """
        if 0 <= index < len(self.worker_tasks):
            task_id = self.worker_tasks[index]
            self._set_task_description(self.worker_progress, task_id, status)

    def start_chapter_worker(
        self,
        chapter_key: str,
        video_id: str,
        status: str,
    ) -> None:
        """Assign a chapter to a visible chapter worker slot."""
        if not self.chapter_tasks:
            return
        slot_index = self._chapter_slot_index(chapter_key)
        if slot_index is None:
            slot_index = self._first_free_chapter_slot()
        if slot_index is None:
            return
        self._chapter_slot_keys[slot_index] = chapter_key
        self._chapter_slot_video_ids[slot_index] = video_id
        self._set_task_description(
            self.chapter_progress,
            self.chapter_tasks[slot_index],
            status,
        )

    def update_chapter_worker(
        self,
        chapter_key: str,
        status: str,
    ) -> None:
        """Update one assigned chapter worker slot."""
        slot_index = self._chapter_slot_index(chapter_key)
        if slot_index is None:
            return
        self._set_task_description(
            self.chapter_progress,
            self.chapter_tasks[slot_index],
            status,
        )

    def complete_chapter_worker(self, chapter_key: str) -> None:
        """Release one chapter worker slot back to idle."""
        slot_index = self._chapter_slot_index(chapter_key)
        if slot_index is None:
            return
        self._chapter_slot_keys[slot_index] = None
        self._chapter_slot_video_ids[slot_index] = None
        self.chapter_progress.update(
            self.chapter_tasks[slot_index],
            description="[dim]Idle[/dim]",
        )

    def clear_chapter_workers(self, video_id: str | None = None) -> None:
        """Reset all chapter worker slots, optionally only for one video."""
        for slot_index, task_id in enumerate(self.chapter_tasks):
            slot_video_id = self._chapter_slot_video_ids[slot_index]
            if video_id is not None and slot_video_id != video_id:
                continue
            self._chapter_slot_keys[slot_index] = None
            self._chapter_slot_video_ids[slot_index] = None
            self.chapter_progress.update(task_id, description="[dim]Idle[/dim]")

    def add_completion(self, title: str) -> None:
        """
        Register a completed video and advance progress.

        Args:
            title: Title of the completed video.
        """
        self.recent_completions.appendleft(title)
        if title.endswith(" (skipped)"):
            self.skipped_count += 1
        else:
            self.completed_count += 1
        self.overall_progress.advance(self.overall_task)

    def add_failure(self, title: str) -> None:
        """
        Register a failed video.

        Args:
            title: Title of the failed video.
        """
        self.recent_failures.appendleft(title)
        self.failed_count += 1
        # We assume failures still count towards "processing done" so we
        # advance the bar.
        self.overall_progress.advance(self.overall_task)

    def set_total_videos(self, total_videos: int) -> None:
        """
        Update the overall expected work count.

        This is used by batch mode when playlist URLs expand into more videos
        after processing has already started.
        """
        self.overall_progress.update(self.overall_task, total=total_videos)

    def update_overall_status(self, description: str) -> None:
        """
        Update the description of the overall progress bar.

        Args:
            description: New description text.
        """
        self.overall_progress.update(self.overall_task, description=description)

    def __rich__(self) -> RenderableType:
        """
        Render the dashboard interface.

        Returns:
            A Rich Renderable (Panel containing Group).
        """
        # Header Section
        header = Table.grid(expand=True)
        header.add_column(ratio=1)
        header.add_column(justify="right")
        header.add_row(
            f"[bold white]📑 Playlist:[/bold white] "
            f"[bold yellow]{self.playlist_name}[/]",
            f"[dim]🤖 {self.model_name}[/dim]",
        )

        # Recent Completions Section
        completed_table = Table.grid(expand=True, padding=(0, 1))

        has_activity = False

        if self.recent_failures:
            has_activity = True
            for title in self.recent_failures:
                display_title = self._truncate_title(title, limit=60)
                safe_title = escape(display_title)
                completed_table.add_row(f"[red]✗[/red] [dim]{safe_title}[/]")

        if self.recent_completions:
            has_activity = True
            for title in self.recent_completions:
                display_title = self._truncate_title(title, limit=60)
                safe_title = escape(display_title)
                completed_table.add_row(f"[green]✓[/green] [dim]{safe_title}[/]")

        if not has_activity:
            completed_table.add_row("[dim italic]No videos completed yet...[/]")

        # Compose Layout Group
        # Only show worker progress if there are multiple tasks (not single
        # video). OR if we want to show it anyway. The user requested hiding
        # idle workers. But for simplicity, let's keep it consistent: always
        # show tasks section, but maybe cleaner.

        elements = [
            header,
            Rule(style="dim"),
            self.overall_progress,
            Rule(style="dim"),
        ]

        # Only add active tasks section if there are workers
        if self.worker_tasks:
            elements.extend(
                [
                    Text("⚡ Active Tasks", style="bold white"),
                    self.worker_progress,
                    Rule(style="dim"),
                ]
            )

        has_active_chapter_workers = any(
            key is not None for key in self._chapter_slot_keys
        )
        if self.chapter_tasks and has_active_chapter_workers:
            elements.extend(
                [
                    Text("🧩 Chapter Tasks", style="bold white"),
                    self.chapter_progress,
                    Rule(style="dim"),
                ]
            )

        elements.extend(
            [Text("✅ Recent Activity", style="bold white"), completed_table]
        )

        body = Group(*elements)

        return Panel(
            body,
            title="[bold cyan]🎓 YouTube Study Material Pipeline[/bold cyan]",
            border_style="cyan",
            padding=(0, 1),
        )
