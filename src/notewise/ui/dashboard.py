"""
Dashboard UI component for pipeline visualization.

Handles the rendering of progress bars, worker status, configuration status,
and completion logs using Rich's Live display capabilities.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from time import monotonic

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

from notewise._constants import (
    DASHBOARD_ACTIVE_PHASE,
    DASHBOARD_ACTIVITY_TITLE_LIMIT,
    DASHBOARD_CONFIG_VALUE_LIMIT,
    DASHBOARD_HEADER_LIVE_LABEL,
    DASHBOARD_HEADER_MODEL_ICON,
    DASHBOARD_HEADER_OUTPUT_LABEL,
    DASHBOARD_HEADER_SOURCE_LABEL,
    DASHBOARD_IDLE_MARKUP,
    DASHBOARD_IDLE_STATUS,
    DASHBOARD_PANEL_TITLE_MARKUP,
    DASHBOARD_PROGRESS_BAR_WIDTH,
    DASHBOARD_PROGRESS_LABEL_MARKUP,
    DASHBOARD_PROGRESS_PERCENT_MARKUP,
    DASHBOARD_PROGRESS_SEPARATOR,
    DASHBOARD_PROGRESS_TOTAL_MARKUP,
    DASHBOARD_RECENT_ACTIVITY_LIMIT,
    DASHBOARD_RECENT_EMPTY_MARKUP,
    DASHBOARD_SECTION_ACTIVE_TASKS_HEADING,
    DASHBOARD_SECTION_CHAPTER_TASKS_HEADING,
    DASHBOARD_SECTION_FLAGS_CONFIG_HEADING,
    DASHBOARD_SECTION_RECENT_ACTIVITY_HEADING,
    DASHBOARD_SECTION_RUN_STATUS_HEADING,
    DASHBOARD_SECTION_WORKERS_HEADING,
    DASHBOARD_SKIPPED_SUFFIX,
    DASHBOARD_SUMMARY_COMPLETED_LABEL,
    DASHBOARD_SUMMARY_FAILED_LABEL,
    DASHBOARD_SUMMARY_QUEUED_LABEL,
    DASHBOARD_SUMMARY_RUNNING_LABEL,
    DASHBOARD_SUMMARY_SKIPPED_LABEL,
    DASHBOARD_UNKNOWN_VALUE,
    DASHBOARD_WORKER_DETAIL_LIMIT,
    DASHBOARD_WORKER_LABEL_TEMPLATE,
    DASHBOARD_WORKER_TABLE_HEADERS,
    DASHBOARD_WORKER_TITLE_LIMIT,
    DASHBOARD_WORKER_VIDEO_PREFIX,
)


@dataclass(frozen=True)
class DashboardConfigItem:
    """One safe dashboard configuration value."""

    label: str
    value: str


@dataclass
class DashboardWorkerSnapshot:
    """Structured state for one visible video worker."""

    phase: str = DASHBOARD_IDLE_STATUS
    title: str = DASHBOARD_UNKNOWN_VALUE
    detail: str = ""
    started_at: float | None = None

    @property
    def is_active(self) -> bool:
        """Return whether this worker is processing a video."""
        return self.started_at is not None and self.phase != DASHBOARD_IDLE_STATUS


class PipelineDashboard:
    """
    Manages the TUI dashboard state and rendering.

    Provides a visual overview of:
    - Run context and selected safe CLI/config values
    - Overall playlist/batch progress
    - Individual worker status
    - Chapter worker status
    - Recent completions, skips, and failures
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
        *,
        run_label: str | None = None,
        output_path: str | None = None,
        config_items: tuple[DashboardConfigItem, ...] = (),
    ):
        """
        Initialize the dashboard.

        Args:
            total_videos: Total number of items to process.
            concurrency: Number of parallel workers.
            playlist_name: Name of the current batch/playlist.
            model_name: The LLM model in use.
            chapter_concurrency: Number of parallel chapter workers.
            run_label: Safe source label for the dashboard header.
            output_path: Safe output location display value.
            config_items: Safe runtime configuration values to render.
        """
        self.playlist_name = playlist_name
        self.model_name = model_name
        self.run_label = run_label or playlist_name
        self.output_path = output_path
        self.config_items = tuple(config_items)
        self.chapter_concurrency = max(0, chapter_concurrency)
        self.recent_completions: deque[str] = deque(
            maxlen=DASHBOARD_RECENT_ACTIVITY_LIMIT
        )
        self.recent_failures: deque[str] = deque(maxlen=DASHBOARD_RECENT_ACTIVITY_LIMIT)
        self.skipped_count = 0
        self.completed_count = 0
        self.failed_count = 0
        self.worker_snapshots: list[DashboardWorkerSnapshot] = [
            DashboardWorkerSnapshot() for _ in range(concurrency)
        ]

        # 1. Overall Progress Bar
        self.overall_progress = Progress(
            TextColumn(DASHBOARD_PROGRESS_LABEL_MARKUP),
            BarColumn(
                bar_width=DASHBOARD_PROGRESS_BAR_WIDTH,
                style="black",
                complete_style="green",
                finished_style="green",
            ),
            TextColumn(DASHBOARD_PROGRESS_PERCENT_MARKUP),
            TextColumn(DASHBOARD_PROGRESS_SEPARATOR),
            TextColumn(DASHBOARD_PROGRESS_TOTAL_MARKUP),
            TextColumn(DASHBOARD_PROGRESS_SEPARATOR),
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
                DASHBOARD_IDLE_MARKUP,
                label=DASHBOARD_WORKER_LABEL_TEMPLATE.format(
                    prefix=prefix,
                    number=i + 1,
                ),
                worker_id=i + 1,
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
                DASHBOARD_IDLE_MARKUP,
                label=DASHBOARD_WORKER_LABEL_TEMPLATE.format(
                    prefix=prefix,
                    number=chapter_index + 1,
                ),
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

    def _safe_cell(self, value: str, *, limit: int | None = None) -> str:
        """Return a markup-safe, optionally truncated table value."""
        display_value = value
        if limit is not None:
            display_value = self._truncate_title(display_value, limit=limit)
        return escape(display_value)

    def _elapsed_for_worker(self, snapshot: DashboardWorkerSnapshot) -> str:
        """Return a compact elapsed time string for a worker snapshot."""
        if snapshot.started_at is None:
            return DASHBOARD_UNKNOWN_VALUE
        elapsed_seconds = max(0, int(monotonic() - snapshot.started_at))
        minutes, seconds = divmod(elapsed_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"

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
            if status == DASHBOARD_IDLE_MARKUP:
                self.clear_worker_state(index)
            elif 0 <= index < len(self.worker_snapshots):
                snapshot = self.worker_snapshots[index]
                if snapshot.started_at is None:
                    snapshot.started_at = monotonic()
                if snapshot.phase == DASHBOARD_IDLE_STATUS:
                    snapshot.phase = DASHBOARD_ACTIVE_PHASE
                snapshot.detail = status

    def update_worker_state(
        self,
        index: int,
        *,
        phase: str,
        title: str,
        detail: str = "",
    ) -> None:
        """Update the structured state shown in the worker table."""
        if not 0 <= index < len(self.worker_snapshots):
            return
        if phase == DASHBOARD_IDLE_STATUS:
            self.clear_worker_state(index)
            return
        snapshot = self.worker_snapshots[index]
        snapshot.phase = phase or DASHBOARD_IDLE_STATUS
        snapshot.title = title or DASHBOARD_UNKNOWN_VALUE
        snapshot.detail = detail
        if snapshot.started_at is None:
            snapshot.started_at = monotonic()

    def clear_worker_state(self, index: int) -> None:
        """Reset one structured worker snapshot to idle."""
        if 0 <= index < len(self.worker_snapshots):
            self.worker_snapshots[index] = DashboardWorkerSnapshot()

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
            description=DASHBOARD_IDLE_MARKUP,
        )

    def clear_chapter_workers(self, video_id: str | None = None) -> None:
        """Reset all chapter worker slots, optionally only for one video."""
        for slot_index, task_id in enumerate(self.chapter_tasks):
            slot_video_id = self._chapter_slot_video_ids[slot_index]
            if video_id is not None and slot_video_id != video_id:
                continue
            self._chapter_slot_keys[slot_index] = None
            self._chapter_slot_video_ids[slot_index] = None
            self.chapter_progress.update(task_id, description=DASHBOARD_IDLE_MARKUP)

    def add_completion(self, title: str) -> None:
        """
        Register a completed video and advance progress.

        Args:
            title: Title of the completed video.
        """
        self.recent_completions.appendleft(title)
        self.completed_count += 1
        self.overall_progress.advance(self.overall_task)

    def add_skipped(self, title: str) -> None:
        """
        Register a skipped video and advance progress.

        Args:
            title: Title of the skipped video.
        """
        self.recent_completions.appendleft(f"{title}{DASHBOARD_SKIPPED_SUFFIX}")
        self.skipped_count += 1
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

    def _render_header(self) -> Table:
        """Render the dashboard header and run context."""
        header = Table.grid(expand=True)
        header.add_column(ratio=1)
        header.add_column(justify="right")
        safe_run_label = self._safe_cell(
            self.run_label,
            limit=DASHBOARD_ACTIVITY_TITLE_LIMIT,
        )
        safe_model_name = self._safe_cell(
            self.model_name,
            limit=DASHBOARD_CONFIG_VALUE_LIMIT,
        )
        header.add_row(
            f"[bold white]{DASHBOARD_HEADER_SOURCE_LABEL}[/bold white] "
            f"[bold yellow]{safe_run_label}[/]",
            f"[dim]{DASHBOARD_HEADER_MODEL_ICON} {safe_model_name}[/dim]",
        )
        if self.output_path:
            safe_output_path = self._safe_cell(
                self.output_path,
                limit=DASHBOARD_CONFIG_VALUE_LIMIT,
            )
            header.add_row(
                f"[bold white]{DASHBOARD_HEADER_OUTPUT_LABEL}[/bold white] "
                f"[cyan]{safe_output_path}[/cyan]",
                f"[dim]{DASHBOARD_HEADER_LIVE_LABEL}[/dim]",
            )
        return header

    def _render_progress_summary(self) -> Table:
        """Render high-level run counters."""
        total = int(self.overall_progress.tasks[self.overall_task].total or 0)
        processed = self.completed_count + self.skipped_count + self.failed_count
        running = sum(1 for snapshot in self.worker_snapshots if snapshot.is_active)
        queued = max(0, total - processed - running)

        table = Table.grid(expand=True, padding=(0, 1))
        table.add_column(style="green")
        table.add_column(style="yellow")
        table.add_column(style="red")
        table.add_column(style="cyan")
        table.add_column(style="blue")
        table.add_row(
            f"{DASHBOARD_SUMMARY_COMPLETED_LABEL}: {self.completed_count}",
            f"{DASHBOARD_SUMMARY_SKIPPED_LABEL}: {self.skipped_count}",
            f"{DASHBOARD_SUMMARY_FAILED_LABEL}: {self.failed_count}",
            f"{DASHBOARD_SUMMARY_RUNNING_LABEL}: {running}",
            f"{DASHBOARD_SUMMARY_QUEUED_LABEL}: {queued}",
        )
        return table

    def _render_config_items(self) -> Table | None:
        """Render safe dashboard configuration items."""
        if not self.config_items:
            return None
        table = Table.grid(expand=True, padding=(0, 1))
        table.add_column(style="bold white", ratio=1)
        table.add_column(style="cyan", ratio=2)
        table.add_column(style="bold white", ratio=1)
        table.add_column(style="cyan", ratio=2)

        row: list[str] = []
        for item in self.config_items:
            row.extend(
                [
                    self._safe_cell(item.label),
                    self._safe_cell(item.value, limit=DASHBOARD_CONFIG_VALUE_LIMIT),
                ]
            )
            if len(row) == 4:
                table.add_row(*row)
                row = []
        if row:
            while len(row) < 4:
                row.append("")
            table.add_row(*row)
        return table

    def _render_worker_table(self) -> Table:
        """Render structured worker state."""
        table = Table.grid(expand=True, padding=(0, 1))
        table.add_column(style="bold cyan", ratio=1)
        table.add_column(style="white", ratio=2)
        table.add_column(style="white", ratio=4)
        table.add_column(style="magenta", ratio=3)
        table.add_column(style="dim", ratio=1)
        table.add_row(*DASHBOARD_WORKER_TABLE_HEADERS)
        for index, snapshot in enumerate(self.worker_snapshots, start=1):
            table.add_row(
                f"{DASHBOARD_WORKER_VIDEO_PREFIX}{index}",
                self._safe_cell(snapshot.phase),
                self._safe_cell(snapshot.title, limit=DASHBOARD_WORKER_TITLE_LIMIT),
                self._safe_cell(snapshot.detail, limit=DASHBOARD_WORKER_DETAIL_LIMIT),
                self._elapsed_for_worker(snapshot),
            )
        return table

    def _render_recent_activity(self) -> Table:
        """Render recent completions and failures."""
        completed_table = Table.grid(expand=True, padding=(0, 1))

        has_activity = False

        if self.recent_failures:
            has_activity = True
            for title in self.recent_failures:
                display_title = self._truncate_title(
                    title,
                    limit=DASHBOARD_ACTIVITY_TITLE_LIMIT,
                )
                safe_title = escape(display_title)
                completed_table.add_row(f"[red]✗[/red] [dim]{safe_title}[/]")

        if self.recent_completions:
            has_activity = True
            for title in self.recent_completions:
                display_title = self._truncate_title(
                    title,
                    limit=DASHBOARD_ACTIVITY_TITLE_LIMIT,
                )
                safe_title = escape(display_title)
                is_skipped = title.endswith(DASHBOARD_SKIPPED_SUFFIX)
                icon = "↷" if is_skipped else "✓"
                color = "yellow" if is_skipped else "green"
                completed_table.add_row(
                    f"[{color}]{icon}[/{color}] [dim]{safe_title}[/]"
                )

        if not has_activity:
            completed_table.add_row(DASHBOARD_RECENT_EMPTY_MARKUP)
        return completed_table

    def __rich__(self) -> RenderableType:
        """
        Render the dashboard interface.

        Returns:
            A Rich Renderable (Panel containing Group).
        """
        elements: list[RenderableType] = [
            self._render_header(),
            Rule(style="dim"),
            Text(DASHBOARD_SECTION_RUN_STATUS_HEADING, style="bold white"),
            self.overall_progress,
            self._render_progress_summary(),
            Rule(style="dim"),
        ]

        config_table = self._render_config_items()
        if config_table is not None:
            elements.extend(
                [
                    Text(DASHBOARD_SECTION_FLAGS_CONFIG_HEADING, style="bold white"),
                    config_table,
                    Rule(style="dim"),
                ]
            )

        if self.worker_tasks:
            elements.extend(
                [
                    Text(DASHBOARD_SECTION_WORKERS_HEADING, style="bold white"),
                    self._render_worker_table(),
                    Rule(style="dim"),
                    Text(DASHBOARD_SECTION_ACTIVE_TASKS_HEADING, style="bold white"),
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
                    Text(DASHBOARD_SECTION_CHAPTER_TASKS_HEADING, style="bold white"),
                    self.chapter_progress,
                    Rule(style="dim"),
                ]
            )

        elements.extend(
            [
                Text(DASHBOARD_SECTION_RECENT_ACTIVITY_HEADING, style="bold white"),
                self._render_recent_activity(),
            ]
        )

        body = Group(*elements)

        return Panel(
            body,
            title=DASHBOARD_PANEL_TITLE_MARKUP,
            border_style="cyan",
            padding=(0, 1),
        )
