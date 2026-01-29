"""
Dashboard UI component for pipeline visualization.
Handles the rendering of progress bars, worker status, and completion logs.
"""

from collections import deque
from typing import List, Deque

from rich.console import Group, RenderableType
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
from rich.markup import escape


class PipelineDashboard:
    """
    Manages the TUI dashboard state and rendering.
    
    Attributes:
        total_videos (int): Total number of videos to process.
        concurrency (int): Number of concurrent workers.
        playlist_name (str): Name of the playlist or video context.
        model_name (str): Name of the LLM model being used.
    """

    def __init__(
        self, 
        total_videos: int, 
        concurrency: int, 
        playlist_name: str, 
        model_name: str
    ):
        self.playlist_name = playlist_name
        self.model_name = model_name
        self.recent_completions: Deque[str] = deque(maxlen=3)
        
        # 1. Overall Progress Bar
        self.overall_progress = Progress(
            TextColumn("[bold blue]Total Progress"),
            BarColumn(
                bar_width=40, 
                style="black", 
                complete_style="green", 
                finished_style="green"
            ),
            TextColumn("[bold green]{task.percentage:>3.0f}%"),
            TextColumn("•"),
            TextColumn("[bold white]{task.completed}/{task.total}"),
            TextColumn("•"),
            TimeElapsedColumn(),
            expand=True
        )
        self.overall_task = self.overall_progress.add_task("", total=total_videos)
        
        # 2. Worker Progress Bars
        self.worker_progress = Progress(
            TextColumn("[bold cyan]{task.fields[label]}[/bold cyan]"),
            SpinnerColumn(),
            TextColumn("{task.description}"),
            expand=True
        )
        
        self.worker_tasks: List[TaskID] = []
        for i in range(concurrency):
            prefix = "└──" if i == concurrency - 1 else "├──"
            tid = self.worker_progress.add_task(
                "[dim]Idle[/dim]", 
                label=f"{prefix} Worker {i+1}", 
                worker_id=i+1
            )
            self.worker_tasks.append(tid)

    def update_worker(self, index: int, status: str, style: str = ""):
        """Update a specific worker's status text."""
        if 0 <= index < len(self.worker_tasks):
            task_id = self.worker_tasks[index]
            description = f"[{style}]{status}[/{style}]" if style else status
            self.worker_progress.update(task_id, description=description)

    def add_completion(self, title: str):
        """Register a completed video."""
        self.recent_completions.appendleft(title)
        self.overall_progress.advance(self.overall_task)

    def __rich__(self) -> RenderableType:
        """Render the dashboard interface."""
        # Header Section
        header = Table.grid(expand=True)
        header.add_column(ratio=1)
        header.add_column(justify="right")
        header.add_row(
            f"[bold white]📑 Playlist:[/bold white] [bold yellow]{self.playlist_name}[/]",
            f"[dim]🤖 {self.model_name}[/dim]"
        )
        
        # Recent Completions Section
        completed_table = Table.grid(expand=True, padding=(0, 1))
        if self.recent_completions:
            for title in self.recent_completions:
                # Truncate long titles for display
                display_title = title[:60] + "..." if len(title) > 60 else title
                safe_title = escape(display_title)
                completed_table.add_row(f"[green]✓[/green] [dim]{safe_title}[/]")
        else:
            completed_table.add_row("[dim italic]No videos completed yet...[/]")

        # Compose Layout Group
        body = Group(
            header,
            Rule(style="dim"),
            self.overall_progress,
            Rule(style="dim"),
            Text("⚡ Active Tasks", style="bold white"),
            self.worker_progress,
            Rule(style="dim"),
            Text("✅ Recent Completions", style="bold white"),
            completed_table
        )
        
        return Panel(
            body,
            title="[bold cyan]yt-study Pipeline[/bold cyan]",
            border_style="cyan",
            padding=(0, 1)
        )
