"""Command-line interface using Typer."""

import asyncio
import logging
import os
from collections.abc import Callable
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
console_handler.setLevel(logging.WARNING)
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
    cookies: Annotated[
        Path | None,
        typer.Option(
            "--cookies",
            help=(
                "Path to cookies.txt in Netscape format for best-effort "
                "authenticated transcript requests."
            ),
            exists=True,
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ] = None,
    use_oauth: Annotated[
        bool | None,
        typer.Option(
            "--use-oauth/--no-use-oauth",
            help=(
                "Enable pytubefix OAuth flow for metadata/playlist requests. "
                "Falls back to config when omitted."
            ),
        ),
    ] = None,
    token_file: Annotated[
        Path | None,
        typer.Option(
            "--token-file",
            help=(
                "OAuth token cache path used with --use-oauth. "
                "Overrides config when provided."
            ),
            exists=False,
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ] = None,
    save_oauth_token: Annotated[
        bool | None,
        typer.Option(
            "--save-oauth-token/--no-save-oauth-token",
            help=(
                "Allow/disallow writing OAuth token cache to disk. "
                "Falls back to config when omitted."
            ),
        ),
    ] = None,
    auto_refresh_oauth_token: Annotated[
        bool | None,
        typer.Option(
            "--auto-refresh-oauth-token/--no-auto-refresh-oauth-token",
            help=(
                "When token cache is stale/invalid, reset and retry once. "
                "Falls back to config when omitted."
            ),
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
        from rich.live import Live
        from rich.table import Table

        from .core.config import config
        from .core.config_helpers import default_youtube_oauth_token_file
        from .core.pipeline import (
            CorePipeline,
            EventType,
            PipelineEvent,
            PipelineResult,
            dedupe_video_ids,
            sanitize_filename,
        )
        from .core.youtube.metadata import get_playlist_info
        from .core.youtube.parser import parse_youtube_url
        from .core.youtube.playlist import extract_playlist_videos
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
        selected_use_oauth = (
            use_oauth if use_oauth is not None else config.youtube_use_oauth
        )
        selected_save_oauth_token = (
            save_oauth_token
            if save_oauth_token is not None
            else config.youtube_save_oauth_token
        )
        selected_auto_refresh_oauth_token = (
            auto_refresh_oauth_token
            if auto_refresh_oauth_token is not None
            else config.youtube_auto_refresh_oauth_token
        )
        selected_token_file = (
            token_file if token_file is not None else config.youtube_oauth_token_file
        )
        if (
            selected_use_oauth
            and selected_save_oauth_token
            and selected_token_file is None
        ):
            selected_token_file = default_youtube_oauth_token_file()
        oauth_token_file = (
            str(selected_token_file) if selected_token_file is not None else None
        )

        # Validate API key before launching UI
        key_name = config.get_api_key_name_for_model(selected_model)
        if key_name and not os.environ.get(key_name):
            console.print(
                f"\n[red bold]✗ Missing API Key for {selected_model}[/red bold]"
            )
            console.print(f"[yellow]Expected environment variable: {key_name}[/yellow]")
            console.print("[dim]Run [cyan]yt-study setup[/cyan] to configure.[/dim]\n")
            raise typer.Exit(code=1)

        def _print_run_summary(
            result: PipelineResult, dashboard: PipelineDashboard
        ) -> None:
            """Render a summary table after the Live display closes."""
            if not result.total_count:
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
            console.print("[dim]Check logs for detailed error reports.[/dim]\n")

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
            EventType.CHAPTER_GENERATING: lambda t, e: (
                f"[cyan]🤖 {t}... (Ch {e.chapter_number}/{e.total_chapters})[/cyan]"
            ),
            EventType.CHAPTER_CHUNK_GENERATING: lambda t, e: (
                f"[cyan]🤖 {t}... (Ch {e.chapter_number}/{e.total_chapters},"
                f" Part {e.chunk_number}/{e.total_chunks})[/cyan]"
            ),
            EventType.GENERATION_COMPLETE: lambda t, _: (
                f"[green]✓ {t}... (Generated)[/green]"
            ),
        }

        async def _run_single_url(single_url: str) -> bool:
            """Parse one URL and run the pipeline (Rich dashboard or headless)."""
            try:
                parsed = parse_youtube_url(single_url)
            except ValueError as e:
                console.print(f"[red]Input Error: {e}[/red]")
                return False

            if parsed.url_type == "video":
                if not parsed.video_id:
                    console.print("[red]Error: Could not extract video ID[/red]")
                    return False
                video_ids = [parsed.video_id]
                playlist_name = "Single Video"
                out_dir = selected_output
            else:  # playlist
                if not parsed.playlist_id:
                    console.print("[red]Error: Could not extract playlist ID[/red]")
                    return False
                playlist_name, _ = await asyncio.to_thread(
                    get_playlist_info,
                    parsed.playlist_id,
                    use_oauth=selected_use_oauth,
                    token_file=oauth_token_file,
                    allow_oauth_cache=selected_save_oauth_token,
                )
                video_ids = await extract_playlist_videos(
                    parsed.playlist_id,
                    use_oauth=selected_use_oauth,
                    token_file=oauth_token_file,
                    allow_oauth_cache=selected_save_oauth_token,
                )
                video_ids = dedupe_video_ids(video_ids)
                out_dir = selected_output / sanitize_filename(playlist_name)
                out_dir.mkdir(parents=True, exist_ok=True)

            pipeline = CorePipeline(
                model=selected_model,
                output_dir=out_dir,
                languages=selected_languages,
                temperature=selected_temperature,
                max_tokens=selected_max_tokens,
                cookies_path=cookies,
                use_oauth=selected_use_oauth,
                oauth_token_file=selected_token_file,
                save_oauth_token=selected_save_oauth_token,
                auto_refresh_oauth_token=selected_auto_refresh_oauth_token,
                force=force,
                quiz=quiz,
            )

            if no_ui:
                # ── Headless path: plain text progress ──────────────────────
                _HEADLESS_LABELS: dict[EventType, str] = {
                    EventType.METADATA_START: "Fetching metadata",
                    EventType.METADATA_FETCHED: "Metadata ready",
                    EventType.TRANSCRIPT_FETCHING: "Fetching transcript",
                    EventType.TRANSCRIPT_FETCHED: "Transcript ready",
                    EventType.GENERATION_START: "Generating notes",
                    EventType.CHUNK_GENERATING: "Generating chunk",
                    EventType.CHAPTER_GENERATING: "Generating chapter",
                    EventType.CHAPTER_CHUNK_GENERATING: "Generating chapter part",
                    EventType.GENERATION_COMPLETE: "Generation complete",
                    EventType.VIDEO_SUCCESS: "Done",
                    EventType.VIDEO_SKIPPED: "Skipped (already processed)",
                    EventType.VIDEO_FAILED: "Failed",
                }

                def on_event_headless(event: PipelineEvent) -> None:
                    if event.event_type in (
                        EventType.PIPELINE_START,
                        EventType.PIPELINE_COMPLETE,
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
                    elif event.error:
                        extra = f": {event.error}"
                    console.print(f"{label}: {title}{extra}", markup=False)

                result = await pipeline.run(video_ids, on_event=on_event_headless)
                if result.total_count:
                    console.print(
                        f"\nDone: {result.success_count}/"
                        f"{result.total_count} succeeded."
                    )
                    if result.failure_count:
                        for vid, err in result.errors.items():
                            console.print(f"  FAILED {vid}: {err}")
                    _print_cost_summary(result)
                return result.failure_count == 0

            # ── Rich dashboard path ──────────────────────────────────────────
            concurrency = min(len(video_ids), config.max_concurrent_videos)
            dashboard = PipelineDashboard(
                total_videos=len(video_ids),
                concurrency=concurrency,
                playlist_name=playlist_name,
                model_name=selected_model,
            )

            # --- Event → Dashboard bridge ---
            # Use WorkerSlotManager to track video-to-slot assignments
            slot_manager = WorkerSlotManager(concurrency)

            def on_event(event: PipelineEvent) -> None:
                vid = event.video_id
                title = (event.title or vid)[:40]
                slot = slot_manager.get_slot(vid)

                # Handle slot acquisition for new videos
                if event.event_type == EventType.METADATA_START:
                    assigned = slot_manager.acquire_slot(vid)
                    if assigned is not None:
                        slot = assigned
                        status_fn = DASHBOARD_STATUS_MAP.get(event.event_type)
                        if status_fn:
                            dashboard.update_worker(assigned, status_fn(title, event))

                # Handle standard status updates
                elif event.event_type in DASHBOARD_STATUS_MAP and slot is not None:
                    status_fn = DASHBOARD_STATUS_MAP[event.event_type]
                    dashboard.update_worker(slot, status_fn(title, event))

                # Handle completion/failure events (release slots)
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

            with Live(dashboard, refresh_per_second=10, console=console, screen=False):
                result = await pipeline.run(video_ids, on_event=on_event)

            _print_run_summary(result, dashboard)
            return result.failure_count == 0

        async def run_processing() -> bool:
            """Determine if input is URL or batch file and dispatch."""
            input_path = Path(url).expanduser()

            if input_path.exists():
                if not input_path.is_file():
                    console.print(
                        "[red]Input Error: Batch file path is not a file: "
                        f"{input_path}[/red]"
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
                    console.print(
                        f"[bold red]❌ Error reading batch file:[/bold red] {e}"
                    )
                    return True

                if not urls:
                    console.print("[yellow]⚠ Batch file is empty.[/yellow]")
                    return True

                had_failures = False

                for i, batch_url in enumerate(urls, 1):
                    console.rule(f"[bold cyan]Batch Item {i}/{len(urls)}[/bold cyan]")
                    try:
                        run_failed = not await _run_single_url(batch_url)
                        had_failures = run_failed or had_failures
                    except Exception as e:
                        console.print(f"[bold red]❌ Batch item failed:[/bold red] {e}")
                        had_failures = True
                return had_failures
            elif looks_like_batch_file_path(url):
                console.print(
                    f"[red]Input Error: Batch file does not exist: {input_path}[/red]"
                )
                return True
            else:
                return not await _run_single_url(url)

        had_failures = asyncio.run(run_processing())
        if had_failures:
            raise typer.Exit(code=1)

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠ Process interrupted by user[/yellow]")
        raise typer.Exit(code=1) from None
    except typer.Exit:
        raise
    except Exception as e:
        from rich.panel import Panel

        console.print(
            Panel(f"[bold red]Fatal Error[/bold red]\n{str(e)}", border_style="red")
        )
        logging.exception("Fatal error in CLI process")
        raise typer.Exit(code=1) from e


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
