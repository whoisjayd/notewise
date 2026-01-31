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

    def __init__(
        self, total_videos: int, concurrency: int, playlist_name: str, model_name: str
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
        self.recent_completions: deque[str] = deque(maxlen=3)
        self.recent_failures: deque[str] = deque(maxlen=3)

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

    def update_worker(self, index: int, status: str, style: str = "") -> None:
        """
        Update a specific worker's status text.

        Args:
            index: Worker index (0-based).
            status: New status text.
            style: Optional Rich style tag to wrap the text.
        """
        if 0 <= index < len(self.worker_tasks):
            task_id = self.worker_tasks[index]
            description = f"[{style}]{status}[/{style}]" if style else status
            self.worker_progress.update(task_id, description=description)

    def add_completion(self, title: str) -> None:
        """
        Register a completed video and advance progress.

        Args:
            title: Title of the completed video.
        """
        self.recent_completions.appendleft(title)
        self.overall_progress.advance(self.overall_task)

    def add_failure(self, title: str) -> None:
        """
        Register a failed video.

        Args:
            title: Title of the failed video.
        """
        self.recent_failures.appendleft(title)
        # We assume failures still count towards "processing done" so we
        # advance the bar.
        self.overall_progress.advance(self.overall_task)

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

        if self.recent_completions:
            has_activity = True
            for title in self.recent_completions:
                display_title = title[:60] + "..." if len(title) > 60 else title
                safe_title = escape(display_title)
                completed_table.add_row(f"[green]✓[/green] [dim]{safe_title}[/]")

        if self.recent_failures:
            has_activity = True
            for title in self.recent_failures:
                display_title = title[:60] + "..." if len(title) > 60 else title
                safe_title = escape(display_title)
                completed_table.add_row(f"[red]✗[/red] [dim]{safe_title}[/]")

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

        elements.extend(
            [Text("✅ Recent Activity", style="bold white"), completed_table]
        )

        # Type casting for Group
        # Elements are mixed types (Table, Rule, Progress, Text) which
        # satisfy RenderableType
        # but mypy struggles with the list inference

        body = Group(*elements)  # type: ignore

        return Panel(
            body,
            title="[bold cyan]🎓 YouTube Study Material Pipeline[/bold cyan]",
            border_style="cyan",
            padding=(0, 1),
        )
