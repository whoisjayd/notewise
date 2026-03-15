"""Command-line interface using Typer."""

import asyncio
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import typer
from rich.console import Console
from rich.logging import RichHandler


# Suppress LiteLLM verbose logging early
os.environ["LITELLM_LOG"] = "ERROR"
logging.getLogger("LiteLLM").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Setup logging
log_dir = Path.home() / ".yt-study" / "logs"
try:
    log_dir.mkdir(parents=True, exist_ok=True)
except Exception:
    # Fallback if home is not writable
    log_dir = Path.cwd() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

# Use timestamped log file for session isolation
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_file = log_dir / f"yt-study-{timestamp}.log"

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Console Handler: Warning+, Clean output
console_handler = RichHandler(rich_tracebacks=False, show_time=False, show_path=False)
# Keep terminal output fully user-facing; detailed logs go to the session file.
console_handler.setLevel(logging.CRITICAL + 1)
root_logger.addHandler(console_handler)

# File Handler: Debug+, Detailed format
try:
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    root_logger.addHandler(file_handler)
except Exception:
    pass

app = typer.Typer(
    name="yt-study",
    help=(
        "🎓 Convert YouTube videos and playlists into comprehensive "
        "study materials using AI."
    ),
    add_completion=True,
    rich_markup_mode="rich",
)

console = Console()
_SCHEMELESS_YOUTUBE_PREFIXES = (
    "youtube.com/",
    "www.youtube.com/",
    "m.youtube.com/",
    "music.youtube.com/",
    "youtu.be/",
)


def check_config_exists() -> bool:
    """Check if user configuration exists."""
    config_path = Path.home() / ".yt-study" / "config.env"
    return config_path.exists()


def ensure_setup() -> None:
    """
    Ensure setup wizard has been run.
    Triggers setup if config is missing.
    """
    if not check_config_exists():
        console.print(
            "\n[yellow]⚠ No configuration found. Running setup wizard...[/yellow]\n"
        )
        try:
            from .setup_wizard import run_setup_wizard

            run_setup_wizard(force=False)
        except ImportError as e:
            console.print("[red]Critical: Could not import setup wizard.[/red]")
            raise typer.Exit(code=1) from e


def looks_like_batch_file_path(value: str) -> bool:
    """Heuristic for path-like batch-file inputs that should not be parsed as URLs."""
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return False

    normalized = value.strip().lower().replace("\\", "/")
    if normalized.startswith(_SCHEMELESS_YOUTUBE_PREFIXES):
        return False

    input_path = Path(value).expanduser()
    return (
        bool(input_path.suffix)
        or input_path.is_absolute()
        or bool(input_path.drive)
        or value.startswith((".", "~"))
        or ("/" in value)
        or ("\\" in value)
    )


@app.command()
def process(
    url: Annotated[
        str,
        typer.Argument(
            help=(
                "YouTube video or playlist URL, or path to a text file containing URLs."
            ),
            show_default=False,
        ),
    ],
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            "-m",
            help=(
                "LLM model (overrides config). Example: [green]gpt-4o[/green] "
                "or [green]gemini/gemini-2.5-flash[/green]"
            ),
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output directory (overrides config).",
            exists=False,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = None,
    language: Annotated[
        list[str] | None,
        typer.Option(
            "--language",
            "-l",
            help=(
                "Preferred transcript languages "
                "(e.g., [green]en[/green], [green]hi[/green])."
            ),
        ),
    ] = None,
    temperature: Annotated[
        float | None,
        typer.Option(
            "--temperature",
            "-t",
            help=(
                "LLM response temperature (overrides config). "
                "Range: 0.0 to 1.0 (default = 0.7)"
            ),
            min=0.0,
            max=1.0,
        ),
    ] = None,
    max_tokens: Annotated[
        int | None,
        typer.Option(
            "--max-tokens",
            "-k",
            help=(
                "Maximum tokens for LLM responses (overrides config). "
                "Adjust based on model limits. (None for model default)"
            ),
            min=1,
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-F",
            help=(
                "Re-process videos even if output already exists. "
                "By default already-processed videos are skipped."
            ),
        ),
    ] = False,
    no_ui: Annotated[
        bool,
        typer.Option(
            "--no-ui",
            help=(
                "Disable the Rich live dashboard. "
                "Outputs plain progress lines to stdout — "
                "useful for CI, cron jobs, and log piping."
            ),
        ),
    ] = False,
    quiz: Annotated[
        bool,
        typer.Option(
            "--quiz",
            help="Also generate a multiple-choice quiz file alongside the study notes.",
        ),
    ] = False,
) -> None:
    """
    Generate comprehensive study notes from YouTube videos or playlists.

    Supports:
    \b
    1. Single Video URL
    2. Playlist URL
    3. Batch file (text file with one URL per line)

    \b
    Examples:
      [cyan]yt-study process "https://youtube.com/watch?v=VIDEO_ID"[/cyan]
      [cyan]yt-study process "URL" -m gpt-4o[/cyan]
      [cyan]yt-study process batch_urls.txt -o ./course-notes[/cyan]
    """
    ensure_setup()

    try:
        # Lazy imports for faster CLI startup
        from rich.console import Group, RenderableType
        from rich.live import Live
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text

        from .core.config import config
        from .core.pipeline import (
            CorePipeline,
            EventType,
            PipelineEvent,
            PipelineMetrics,
            PipelineResult,
            PipelineSharedState,
            dedupe_video_ids,
            sanitize_filename,
        )
        from .core.youtube.metadata import PublicAccessRequiredError, get_playlist_info
        from .core.youtube.parser import parse_youtube_url
        from .core.youtube.playlist import PlaylistError, extract_playlist_videos
        from .ui.dashboard import PipelineDashboard

        selected_model = model or config.default_model
        selected_output = output or config.default_output_dir
        selected_languages = language or config.default_languages
        selected_temperature = (
            temperature if temperature is not None else config.temperature
        )
        selected_max_tokens = (
            max_tokens if max_tokens is not None else config.max_tokens
        )

        api_key_checked: bool | None = None

        def _ensure_api_key_available() -> bool:
            """Validate the selected model's API key after input preflight succeeds."""
            nonlocal api_key_checked
            if api_key_checked is not None:
                return api_key_checked

            key_name = config.get_api_key_name_for_model(selected_model)
            if key_name and not os.environ.get(key_name):
                _print_failure_panel(
                    "Setup Required",
                    [
                        ("Model", f"Missing API key for {selected_model}"),
                        ("Expected", key_name),
                        ("Next Step", "Run `yt-study setup` to configure it."),
                    ],
                )
                api_key_checked = False
                return False

            api_key_checked = True
            return True

        def _print_failure_panel(
            title: str,
            rows: list[tuple[str, str]],
            *,
            intro: str | None = None,
        ) -> None:
            """Render a user-friendly failure summary and point to the session log."""
            failure_table = Table(
                box=None,
                show_header=False,
                show_edge=False,
                pad_edge=False,
                padding=(0, 1),
            )
            failure_table.add_column("Item", style="bold red", no_wrap=True)
            failure_table.add_column("Message", overflow="fold")

            for item, message in rows:
                failure_table.add_row(item, message)

            renderables: list[RenderableType] = []
            if intro:
                renderables.append(Text(intro, style="bold"))
            renderables.append(failure_table)
            renderables.append(Text(f"Current log: {log_file}", style="dim"))

            console.print("\n")
            console.print(
                Panel(
                    Group(*renderables),
                    title=f"[bold red]{title}[/bold red]",
                    border_style="red",
                )
            )
            console.print()

        def _print_single_failure(
            title: str,
            message: str,
            *,
            item_label: str = "Issue",
            intro: str | None = None,
        ) -> None:
            """Render a one-item failure panel."""
            _print_failure_panel(title, [(item_label, message)], intro=intro)

        def _print_run_summary(
            result: PipelineResult, dashboard: PipelineDashboard
        ) -> None:
            """Render a summary table after the Live display closes."""
            if not result.total_count:
                return

            if result.failure_count:
                intro = None
                if result.success_count:
                    intro = (
                        f"Completed successfully: "
                        f"{result.success_count}/{result.total_count}"
                    )
                _print_failure_panel(
                    "Processing Failed",
                    list(result.errors.items()),
                    intro=intro,
                )
                return

            summary_table = Table(
                title="📊 Processing Summary",
                border_style="cyan",
                show_header=True,
                header_style="bold magenta",
            )
            summary_table.add_column("Status", justify="center")
            summary_table.add_column("Video Title", style="dim")
            for title in dashboard.recent_failures:
                summary_table.add_row("[bold red]FAILED[/bold red]", title)
            for title in dashboard.recent_completions:
                summary_table.add_row("[green]SUCCESS[/green]", title)
            console.print("\n")
            console.print(summary_table)
            console.print(
                f"\n[bold]Total Completed:[/bold] "
                f"{result.success_count}/{result.total_count}"
            )
            _print_cost_summary(result)
            console.print(f"[dim]Current log: {log_file}[/dim]\n")

        def _print_cost_summary(result: PipelineResult) -> None:
            """Render token/time metrics collected during the pipeline run."""
            metrics = result.metrics
            if not metrics:
                return

            def _safe_int(value: object) -> int:
                if isinstance(value, bool):
                    return int(value)
                if isinstance(value, int):
                    return value
                if isinstance(value, float):
                    return int(value)
                if isinstance(value, str):
                    try:
                        return int(value.strip())
                    except ValueError:
                        return 0
                return 0

            def _safe_float(value: object) -> float:
                if isinstance(value, bool):
                    return float(value)
                if isinstance(value, (int, float)):
                    return float(value)
                if isinstance(value, str):
                    try:
                        return float(value.strip())
                    except ValueError:
                        return 0.0
                return 0.0

            prompt_tokens = _safe_int(getattr(metrics, "prompt_tokens", 0))
            completion_tokens = _safe_int(getattr(metrics, "completion_tokens", 0))
            total_tokens = _safe_int(getattr(metrics, "total_tokens", 0))
            cost_usd = _safe_float(getattr(metrics, "cost_usd", 0.0))
            transcript_seconds = _safe_float(
                getattr(metrics, "transcript_seconds", 0.0)
            )
            generation_seconds = _safe_float(
                getattr(metrics, "generation_seconds", 0.0)
            )

            cost_table = Table(
                title="💸 Cost Summary",
                border_style="green",
                show_header=True,
                header_style="bold green",
            )
            cost_table.add_column("Metric", style="cyan")
            cost_table.add_column("Value", justify="right")
            cost_table.add_row("Prompt Tokens", f"{prompt_tokens:,}")
            cost_table.add_row("Completion Tokens", f"{completion_tokens:,}")
            cost_table.add_row("Total Tokens", f"{total_tokens:,}")
            cost_table.add_row("Estimated Cost (USD)", f"${cost_usd:.6f}")
            cost_table.add_row(
                "Transcript Time (s)",
                f"{transcript_seconds:.2f}",
            )
            cost_table.add_row(
                "Generation Time (s)",
                f"{generation_seconds:.2f}",
            )
            console.print("\n")
            console.print(cost_table)

        class WorkerSlotManager:
            """Manages worker slot assignment and release for concurrent processing."""

            def __init__(self, concurrency: int):
                """Initialize slot manager with available slots.

                Args:
                    concurrency: Number of concurrent worker slots.
                """
                self.available_slots: list[int] = list(range(concurrency))
                self.video_slots: dict[str, int] = {}

            def acquire_slot(self, video_id: str) -> int | None:
                """Assign an available slot to a video.

                Args:
                    video_id: The video ID to assign a slot to.

                Returns:
                    The assigned slot index, or None if no slots available.
                """
                if self.available_slots:
                    assigned = self.available_slots.pop(0)
                    self.video_slots[video_id] = assigned
                    return assigned
                return None

            def release_slot(self, video_id: str) -> int | None:
                """Release a slot back to the pool.

                Args:
                    video_id: The video ID whose slot should be released.

                Returns:
                    The released slot index, or None if video had no slot.
                """
                released = self.video_slots.pop(video_id, None)
                if released is not None:
                    self.available_slots.append(released)
                return released

            def get_slot(self, video_id: str) -> int | None:
                """Get the currently assigned slot for a video.

                Args:
                    video_id: The video ID to look up.

                Returns:
                    The assigned slot index, or None if not assigned.
                """
                return self.video_slots.get(video_id)

        # Mirror the pipeline's user-visible event stream in the live dashboard.
        DASHBOARD_STATUS_MAP: dict[EventType, Callable[[str, PipelineEvent], str]] = {
            EventType.METADATA_START: lambda t, _: (
                f"[yellow]{t}... (Metadata)[/yellow]"
            ),
            EventType.METADATA_FETCHED: lambda t, _: f"[cyan]{t}... (Fetched)[/cyan]",
            EventType.TRANSCRIPT_FETCHING: lambda t, _: (
                f"[cyan]📥 {t}... (Transcript)[/cyan]"
            ),
            EventType.TRANSCRIPT_FETCHED: lambda t, _: (
                f"[green]✓ {t}... (Transcript Ready)[/green]"
            ),
            EventType.GENERATION_START: lambda t, _: (
                f"[cyan]🤖 {t}... (Generating)[/cyan]"
            ),
            EventType.CHUNK_GENERATING: lambda t, e: (
                f"[cyan]🤖 {t}... (Chunk {e.chunk_number}/{e.total_chunks})[/cyan]"
            ),
            EventType.GENERATION_COMBINING: lambda t, e: (
                f"[cyan]🧩 {t}... (Combining {e.total_chunks} note parts)[/cyan]"
            ),
            EventType.CHAPTER_GENERATING: lambda t, e: (
                f"[cyan]🤖 {t}... (Ch {e.chapter_number}/{e.total_chapters})[/cyan]"
            ),
            EventType.CHAPTER_CHUNK_GENERATING: lambda t, e: (
                f"[cyan]🤖 {t}... (Ch {e.chapter_number}/{e.total_chapters},"
                f" Part {e.chunk_number}/{e.total_chunks})[/cyan]"
            ),
            EventType.CHAPTER_COMBINING: lambda t, e: (
                f"[cyan]🧩 {t}... (Ch {e.chapter_number}/{e.total_chapters},"
                f" Combining {e.total_chunks} parts)[/cyan]"
            ),
            EventType.QUIZ_GENERATING: lambda t, _: (
                f"[magenta]📝 {t}... (Quiz)[/magenta]"
            ),
            EventType.QUIZ_CHUNK_GENERATING: lambda t, e: (
                "[magenta]📝 "
                f"{t}... (Quiz Part {e.chunk_number}/{e.total_chunks})[/magenta]"
            ),
            EventType.QUIZ_COMBINING: lambda t, e: (
                f"[magenta]🧩 {t}... (Combining {e.total_chunks} quiz parts)[/magenta]"
            ),
            EventType.QUIZ_COMPLETE: lambda t, _: (
                f"[green]✓ {t}... (Quiz Ready)[/green]"
            ),
            EventType.GENERATION_COMPLETE: lambda t, _: (
                f"[green]✓ {t}... (Generated)[/green]"
            ),
        }

        @dataclass
        class PreparedSource:
            """Resolved work for a single input URL or playlist."""

            source_url: str
            label: str
            playlist_name: str
            video_ids: list[str]
            output_dir: Path
            is_playlist: bool = False

        @dataclass
        class PreparedBatchJob:
            """One video job scheduled through the shared batch worker pool."""

            sort_key: tuple[int, int]
            video_id: str
            output_dir: Path
            source_label: str
            is_playlist_video: bool = False

        @dataclass
        class OrderedBatchFailure:
            """Failure row with a stable display order for final reporting."""

            sort_key: tuple[int, int]
            item: str
            message: str

        @dataclass
        class BatchJobResult:
            """Result of one processed batch video job."""

            sort_key: tuple[int, int]
            success: bool
            display_title: str
            failure_row: OrderedBatchFailure | None = None
            metrics: PipelineMetrics = field(default_factory=PipelineMetrics)

        class UserVisibleCliError(Exception):
            """Structured CLI failure that can be rendered without a traceback."""

            def __init__(
                self,
                title: str,
                rows: list[tuple[str, str]],
                *,
                intro: str | None = None,
            ) -> None:
                super().__init__(title)
                self.title = title
                self.rows = rows
                self.intro = intro

        def _build_pipeline(
            output_dir: Path,
            *,
            shared_state: PipelineSharedState | None = None,
        ) -> CorePipeline:
            """Create a pipeline instance for one source."""
            return CorePipeline(
                model=selected_model,
                output_dir=output_dir,
                languages=selected_languages,
                temperature=selected_temperature,
                max_tokens=selected_max_tokens,
                force=force,
                quiz=quiz,
                shared_state=shared_state,
            )

        async def _prepare_source(single_url: str) -> PreparedSource:
            """Resolve one URL into a runnable video or playlist job."""
            try:
                parsed = parse_youtube_url(single_url)
            except ValueError as e:
                raise UserVisibleCliError("Input Error", [("URL", str(e))]) from e

            if parsed.url_type == "video":
                if not parsed.video_id:
                    raise UserVisibleCliError(
                        "Input Error",
                        [("URL", "Could not extract a video ID from this URL.")],
                    )
                return PreparedSource(
                    source_url=single_url,
                    label=parsed.video_id,
                    playlist_name="Single Video",
                    video_ids=[parsed.video_id],
                    output_dir=selected_output,
                )

            if not parsed.playlist_id:
                raise UserVisibleCliError(
                    "Input Error",
                    [("URL", "Could not extract a playlist ID from this URL.")],
                )

            try:
                video_ids = await extract_playlist_videos(parsed.playlist_id)
            except (PlaylistError, PublicAccessRequiredError) as e:
                raise UserVisibleCliError(
                    "Playlist Error",
                    [(parsed.playlist_id, str(e))],
                ) from e

            playlist_name, _ = await asyncio.to_thread(
                get_playlist_info,
                parsed.playlist_id,
            )
            video_ids = dedupe_video_ids(video_ids)
            output_dir = selected_output / sanitize_filename(playlist_name)
            output_dir.mkdir(parents=True, exist_ok=True)

            return PreparedSource(
                source_url=single_url,
                label=playlist_name or parsed.playlist_id,
                playlist_name=playlist_name,
                video_ids=video_ids,
                output_dir=output_dir,
                is_playlist=True,
            )

        def _failure_rows_for_result(
            prepared: PreparedSource,
            result: PipelineResult,
            *,
            include_source_label: bool = False,
        ) -> list[tuple[str, str]]:
            """Format pipeline failures for standalone or batch rendering."""
            if result.errors:
                if include_source_label and prepared.is_playlist:
                    return [
                        (f"{prepared.label} / {video_id}", error)
                        for video_id, error in result.errors.items()
                    ]
                return list(result.errors.items())

            return [
                (
                    prepared.label,
                    "We couldn't process this entry. "
                    "Check the current session log for details.",
                )
            ]

        def _ordered_batch_failures_from_error(
            item_index: int,
            batch_url: str,
            error: UserVisibleCliError,
        ) -> list[OrderedBatchFailure]:
            """Normalize batch preparation failures into sorted summary rows."""
            failures: list[OrderedBatchFailure] = []
            for row_index, (item, message) in enumerate(error.rows, start=1):
                display_item = batch_url if item == "URL" else item
                failures.append(
                    OrderedBatchFailure(
                        sort_key=(item_index, row_index),
                        item=display_item,
                        message=message,
                    )
                )
            return failures

        def _batch_failure_label(
            job: PreparedBatchJob,
            display_title: str,
        ) -> str:
            """Format a batch failure label for direct videos or playlist videos."""
            if job.is_playlist_video:
                return f"{job.source_label} / {display_title}"
            return display_title

        def _print_batch_summary(
            batch_results: list[BatchJobResult],
            early_failures: list[OrderedBatchFailure],
            *,
            total_jobs: int,
        ) -> bool:
            """Render one final summary for a batch run."""
            success_jobs = sum(1 for result in batch_results if result.success)
            failed_rows = [
                (failure.item, failure.message)
                for failure in sorted(
                    [
                        *early_failures,
                        *[
                            result.failure_row
                            for result in batch_results
                            if result.failure_row is not None
                        ],
                    ],
                    key=lambda failure: failure.sort_key,
                )
            ]

            batch_metrics = PipelineMetrics()
            for result in batch_results:
                batch_metrics.add_from(result.metrics)

            if failed_rows:
                intro = None
                if success_jobs and total_jobs:
                    intro = (
                        f"Videos completed successfully: {success_jobs}/{total_jobs}"
                    )
                _print_failure_panel(
                    "Batch Completed with Failures",
                    failed_rows,
                    intro=intro,
                )
                return True

            console.print(
                f"\nDone: {success_jobs}/{total_jobs} batch videos succeeded."
            )
            _print_cost_summary(
                PipelineResult(
                    success_count=success_jobs,
                    failure_count=0,
                    total_count=total_jobs,
                    video_ids=[],
                    errors={},
                    metrics=batch_metrics,
                )
            )
            console.print(f"[dim]Current log: {log_file}[/dim]\n")
            return False

        async def _run_single_url(single_url: str) -> bool:
            """Parse one URL and run the pipeline (Rich dashboard or headless)."""
            try:
                prepared = await _prepare_source(single_url)
            except UserVisibleCliError as e:
                _print_failure_panel(e.title, e.rows, intro=e.intro)
                return False

            if not _ensure_api_key_available():
                return False

            pipeline = _build_pipeline(prepared.output_dir)

            if no_ui:
                # ── Headless path: plain text progress ──────────────────────
                _HEADLESS_LABELS: dict[EventType, str] = {
                    EventType.METADATA_START: "Fetching metadata",
                    EventType.METADATA_FETCHED: "Metadata ready",
                    EventType.TRANSCRIPT_FETCHING: "Fetching transcript",
                    EventType.TRANSCRIPT_FETCHED: "Transcript ready",
                    EventType.GENERATION_START: "Generating notes",
                    EventType.CHUNK_GENERATING: "Generating chunk",
                    EventType.GENERATION_COMBINING: "Combining notes",
                    EventType.CHAPTER_GENERATING: "Generating chapter",
                    EventType.CHAPTER_CHUNK_GENERATING: "Generating chapter part",
                    EventType.CHAPTER_COMBINING: "Combining chapter",
                    EventType.QUIZ_GENERATING: "Generating quiz",
                    EventType.QUIZ_CHUNK_GENERATING: "Generating quiz part",
                    EventType.QUIZ_COMBINING: "Combining quiz",
                    EventType.QUIZ_COMPLETE: "Quiz ready",
                    EventType.GENERATION_COMPLETE: "Generation complete",
                    EventType.VIDEO_SUCCESS: "Done",
                    EventType.VIDEO_SKIPPED: "Skipped (already processed)",
                    EventType.VIDEO_FAILED: "Failed",
                }

                def on_event_headless(event: PipelineEvent) -> None:
                    if event.event_type in (
                        EventType.PIPELINE_START,
                        EventType.PIPELINE_COMPLETE,
                        EventType.VIDEO_FAILED,
                    ):
                        return
                    label = _HEADLESS_LABELS.get(
                        event.event_type, event.event_type.value
                    )
                    title = event.title or event.video_id
                    extra = ""
                    if (
                        event.event_type == EventType.CHAPTER_CHUNK_GENERATING
                        and event.chapter_number
                        and event.total_chapters
                        and event.chunk_number
                        and event.total_chunks
                    ):
                        extra = (
                            f" [Ch {event.chapter_number}/{event.total_chapters},"
                            f" Part {event.chunk_number}/{event.total_chunks}]"
                        )
                    elif event.chunk_number and event.total_chunks:
                        extra = f" [{event.chunk_number}/{event.total_chunks}]"
                    elif event.chapter_number and event.total_chapters:
                        extra = f" [{event.chapter_number}/{event.total_chapters}]"
                    elif event.total_chunks and event.event_type in (
                        EventType.GENERATION_COMBINING,
                        EventType.QUIZ_COMBINING,
                        EventType.CHAPTER_COMBINING,
                    ):
                        extra = f" [{event.total_chunks} parts]"
                    elif event.error:
                        extra = f": {event.error}"
                    console.print(f"{label}: {title}{extra}", markup=False)

                result = await pipeline.run(
                    prepared.video_ids,
                    on_event=on_event_headless,
                )
                if result.total_count:
                    if result.failure_count:
                        intro = None
                        if result.success_count:
                            intro = (
                                f"Completed successfully: "
                                f"{result.success_count}/{result.total_count}"
                            )
                        _print_failure_panel(
                            "Processing Failed",
                            _failure_rows_for_result(prepared, result),
                            intro=intro,
                        )
                    else:
                        console.print(
                            f"\nDone: {result.success_count}/"
                            f"{result.total_count} succeeded."
                        )
                        _print_cost_summary(result)
                        console.print(f"[dim]Current log: {log_file}[/dim]\n")
                return result.failure_count == 0

            # ── Rich dashboard path ──────────────────────────────────────────
            concurrency = min(len(prepared.video_ids), config.max_concurrent_videos)
            dashboard = PipelineDashboard(
                total_videos=len(prepared.video_ids),
                concurrency=concurrency,
                playlist_name=prepared.playlist_name,
                model_name=selected_model,
            )

            slot_manager = WorkerSlotManager(concurrency)

            def on_event(event: PipelineEvent) -> None:
                vid = event.video_id
                title = (event.title or vid)[:40]
                slot = slot_manager.get_slot(vid)

                if event.event_type == EventType.METADATA_START:
                    assigned = slot_manager.acquire_slot(vid)
                    if assigned is not None:
                        slot = assigned
                        status_fn = DASHBOARD_STATUS_MAP.get(event.event_type)
                        if status_fn:
                            dashboard.update_worker(assigned, status_fn(title, event))

                elif event.event_type in DASHBOARD_STATUS_MAP and slot is not None:
                    status_fn = DASHBOARD_STATUS_MAP[event.event_type]
                    dashboard.update_worker(slot, status_fn(title, event))

                elif event.event_type in (
                    EventType.VIDEO_SUCCESS,
                    EventType.VIDEO_SKIPPED,
                    EventType.VIDEO_FAILED,
                ):
                    released = slot_manager.release_slot(vid)
                    if released is not None:
                        dashboard.update_worker(released, "[dim]Idle[/dim]")

                    if event.event_type == EventType.VIDEO_SUCCESS:
                        dashboard.add_completion(event.title or vid)
                    elif event.event_type == EventType.VIDEO_SKIPPED:
                        dashboard.add_completion(f"{event.title or vid} (skipped)")
                    else:
                        dashboard.add_failure(event.title or vid)

            with Live(
                dashboard,
                refresh_per_second=10,
                console=console,
                screen=False,
                transient=True,
            ):
                result = await pipeline.run(prepared.video_ids, on_event=on_event)

            _print_run_summary(result, dashboard)
            return result.failure_count == 0

        async def _run_batch_file(input_path: Path, urls: list[str]) -> bool:
            """Process batch URLs through one shared video worker pool."""
            if not _ensure_api_key_available():
                return True

            batch_workers = max(1, config.max_concurrent_videos)
            dashboard = None
            if not no_ui:
                dashboard = PipelineDashboard(
                    total_videos=0,
                    concurrency=batch_workers,
                    playlist_name=f"Batch File: {input_path.name}",
                    model_name=selected_model,
                )

            shared_state = PipelineSharedState(
                semaphore=asyncio.Semaphore(batch_workers)
            )
            job_queue: asyncio.Queue[PreparedBatchJob | None] = asyncio.Queue()
            batch_results: list[BatchJobResult] = []
            early_failures: list[OrderedBatchFailure] = []
            total_jobs = 0

            async def _run_batch_job(worker_index: int) -> None:
                while True:
                    job = await job_queue.get()
                    if job is None:
                        if dashboard is not None:
                            dashboard.update_worker(worker_index, "[dim]Idle[/dim]")
                        job_queue.task_done()
                        return

                    latest_title = job.video_id
                    fallback_video_id = job.video_id
                    try:
                        pipeline = _build_pipeline(
                            job.output_dir,
                            shared_state=shared_state,
                        )

                        def on_batch_event(
                            event: PipelineEvent,
                            *,
                            _fallback_video_id: str = fallback_video_id,
                        ) -> None:
                            nonlocal latest_title
                            if event.title:
                                latest_title = event.title
                            if (
                                dashboard is None
                                or event.event_type not in DASHBOARD_STATUS_MAP
                            ):
                                return
                            status_fn = DASHBOARD_STATUS_MAP[event.event_type]
                            dashboard.update_worker(
                                worker_index,
                                status_fn(
                                    (latest_title or _fallback_video_id)[:40],
                                    event,
                                ),
                            )

                        result = await pipeline.run(
                            [fallback_video_id],
                            on_event=on_batch_event if dashboard is not None else None,
                        )
                        display_title = latest_title or fallback_video_id

                        if dashboard is not None:
                            dashboard.update_worker(worker_index, "[dim]Idle[/dim]")
                            if result.failure_count:
                                dashboard.add_failure(display_title)
                            else:
                                dashboard.add_completion(display_title)

                        failure_row = None
                        if result.failure_count:
                            failure_message = next(
                                iter(result.errors.values()),
                                "We couldn't process this batch video. "
                                "Check the current session log for details.",
                            )
                            failure_row = OrderedBatchFailure(
                                sort_key=job.sort_key,
                                item=_batch_failure_label(job, display_title),
                                message=failure_message,
                            )

                        batch_results.append(
                            BatchJobResult(
                                sort_key=job.sort_key,
                                success=result.failure_count == 0,
                                display_title=display_title,
                                failure_row=failure_row,
                                metrics=result.metrics,
                            )
                        )
                    except Exception:
                        display_title = latest_title or fallback_video_id
                        logging.exception("Unexpected batch video failure")
                        if dashboard is not None:
                            dashboard.update_worker(worker_index, "[dim]Idle[/dim]")
                            dashboard.add_failure(display_title)
                        batch_results.append(
                            BatchJobResult(
                                sort_key=job.sort_key,
                                success=False,
                                display_title=display_title,
                                failure_row=OrderedBatchFailure(
                                    sort_key=job.sort_key,
                                    item=_batch_failure_label(job, display_title),
                                    message=(
                                        "yt-study hit an unexpected internal "
                                        "error for this video. Check the current "
                                        "log for details."
                                    ),
                                ),
                            )
                        )
                    finally:
                        job_queue.task_done()

            async def _enqueue_batch_jobs() -> None:
                nonlocal total_jobs
                for item_index, batch_url in enumerate(urls, start=1):
                    if dashboard is not None:
                        dashboard.update_overall_status(
                            f"Resolving batch entry {item_index}/{len(urls)}"
                        )
                    try:
                        prepared = await _prepare_source(batch_url)
                    except UserVisibleCliError as e:
                        early_failures.extend(
                            _ordered_batch_failures_from_error(
                                item_index,
                                batch_url,
                                e,
                            )
                        )
                        continue

                    for video_index, video_id in enumerate(
                        prepared.video_ids,
                        start=1,
                    ):
                        total_jobs += 1
                        if dashboard is not None:
                            dashboard.set_total_videos(total_jobs)
                        await job_queue.put(
                            PreparedBatchJob(
                                sort_key=(item_index, video_index),
                                video_id=video_id,
                                output_dir=prepared.output_dir,
                                source_label=prepared.label,
                                is_playlist_video=prepared.is_playlist,
                            )
                        )

                if dashboard is not None:
                    dashboard.update_overall_status("")
                for _ in range(batch_workers):
                    await job_queue.put(None)

            async def _run_batch_queue() -> None:
                workers = [
                    asyncio.create_task(_run_batch_job(worker_index))
                    for worker_index in range(batch_workers)
                ]
                await _enqueue_batch_jobs()
                await job_queue.join()
                await asyncio.gather(*workers)

            if dashboard is not None:
                with Live(
                    dashboard,
                    refresh_per_second=10,
                    console=console,
                    screen=False,
                    transient=True,
                ):
                    await _run_batch_queue()
            else:
                await _run_batch_queue()

            return _print_batch_summary(
                batch_results,
                early_failures,
                total_jobs=total_jobs,
            )

        async def run_processing() -> bool:
            """Determine if input is URL or batch file and dispatch."""
            input_path = Path(url).expanduser()

            if input_path.exists():
                if not input_path.is_file():
                    _print_single_failure(
                        "Input Error",
                        f"Batch file path is not a file: {input_path}",
                        item_label="Batch File",
                    )
                    return True

                # Batch Mode: read one URL per non-comment line
                try:
                    content = input_path.read_text(encoding="utf-8")
                    urls = [
                        line.strip()
                        for line in content.splitlines()
                        if line.strip() and not line.strip().startswith("#")
                    ]
                except Exception as e:
                    _print_single_failure(
                        "Input Error",
                        f"Could not read the batch file: {e}",
                        item_label="Batch File",
                    )
                    return True

                if not urls:
                    _print_single_failure(
                        "Input Error",
                        "The batch file is empty.",
                        item_label="Batch File",
                    )
                    return True

                return await _run_batch_file(input_path, urls)
            elif looks_like_batch_file_path(url):
                _print_single_failure(
                    "Input Error",
                    f"Batch file does not exist: {input_path}",
                    item_label="Batch File",
                )
                return True
            else:
                return not await _run_single_url(url)

        had_failures = asyncio.run(run_processing())
        if had_failures:
            raise typer.Exit(code=1)

    except KeyboardInterrupt:
        failure_printer = locals().get("_print_single_failure")
        if callable(failure_printer):
            failure_printer(
                "Processing Stopped",
                "The run was interrupted before it finished.",
                item_label="Status",
            )
        else:
            console.print("\n[red]Processing stopped before it finished.[/red]\n")
        raise typer.Exit(code=1) from None
    except typer.Exit:
        raise
    except Exception:
        logging.exception("Fatal error in CLI process")
        failure_printer = locals().get("_print_single_failure")
        if callable(failure_printer):
            failure_printer(
                "Unexpected Error",
                "yt-study hit an unexpected internal error before it could finish.",
                item_label="Status",
                intro="Please check the current log file and try again.",
            )
        else:
            console.print(
                "\n[red]yt-study hit an unexpected internal error.[/red]\n"
                f"[dim]Current log: {log_file}[/dim]\n"
            )
        raise typer.Exit(code=1) from None


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """
    [bold cyan]yt-study[/bold cyan]: AI-Powered Video Study Notes Generator.

    Convert YouTube content into structured Markdown notes.
    """
    # Only show help if no subcommand is being invoked
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


@app.command()
def setup(
    force: Annotated[
        bool,
        typer.Option(
            "--force", "-f", help="Force reconfiguration even if config exists."
        ),
    ] = False,
) -> None:
    """
    Configure API keys and preferences interactively.

    Runs a wizard to generate the [bold]~/.yt-study/config.env[/bold] file.
    """
    try:
        from .setup_wizard import run_setup_wizard

        run_setup_wizard(force=force)
    except ImportError as e:
        console.print("[red]Setup wizard module missing.[/red]")
        raise typer.Exit(code=1) from e


@app.command()
def config_path() -> None:
    """Show the path to the configuration file."""
    config_file = Path.home() / ".yt-study" / "config.env"

    if config_file.exists():
        console.print(f"\n[cyan]Configuration file:[/cyan] {config_file}")
        console.print("\n[dim]To edit: Open the file above in a text editor[/dim]")
        console.print(
            "[dim]To reconfigure: Run[/dim] [cyan]yt-study setup --force[/cyan]\n"
        )
    else:
        console.print("\n[yellow]No configuration found.[/yellow]")
        console.print(
            "[dim]Run[/dim] [cyan]yt-study setup[/cyan] [dim]to create one.[/dim]\n"
        )


@app.command()
def version() -> None:
    """Show version information."""
    try:
        from . import __version__

        ver = __version__
    except ImportError:
        ver = "dev"

    console.print(f"[cyan]yt-study[/cyan] version [green]{ver}[/green]")


if __name__ == "__main__":
    app()
