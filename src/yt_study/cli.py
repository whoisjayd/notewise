"""Command-line interface using Typer."""

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

import structlog
import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from .core.telemetry import telemetry


# Suppress LiteLLM verbose logging early
os.environ["LITELLM_LOG"] = "ERROR"
logging.getLogger("LiteLLM").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Setup logging directories
log_dir = Path.home() / ".yt-study" / "logs"
try:
    log_dir.mkdir(parents=True, exist_ok=True)
except Exception:
    log_dir = Path.cwd() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

# Log files
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_file_json = log_dir / "yt-study.jsonl"


# Configure structlog
def configure_logging() -> None:
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    structlog.configure(
        processors=shared_processors
        + [
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.make_filtering_bound_logger(logging.INFO),
            (
                structlog.dev.ConsoleRenderer()
                if sys.stderr.isatty()
                else structlog.processors.JSONRenderer()
            ),
        ],
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )

    # Standard logging bridge
    logging.basicConfig(
        format="%(message)s",
        level=logging.WARNING,
        handlers=[RichHandler(rich_tracebacks=True, show_time=False, show_path=False)],
    )

    # File handler for JSON logs
    file_handler = logging.FileHandler(log_file_json, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
        )
    )
    logging.getLogger().addHandler(file_handler)


configure_logging()
logger = structlog.get_logger(__name__)

app = typer.Typer(
    name="yt-study",
    help=(
        "Convert YouTube videos and playlists into comprehensive "
        "study materials using AI."
    ),
    add_completion=True,
    rich_markup_mode="rich",
)

console = Console()


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
                "or [green]gemini/gemini-2.0-flash[/green]"
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
            "-f",
            help="Force re-processing even if output already exists.",
        ),
    ] = False,
    export_transcript: Annotated[
        bool,
        typer.Option(
            "--export-transcript",
            "--raw",
            help="Export raw transcript to a separate text file.",
        ),
    ] = False,
    no_chapters: Annotated[
        bool,
        typer.Option(
            "--no-chapters",
            help="Disable use of YouTube chapters.",
        ),
    ] = False,
    no_synthetic: Annotated[
        bool,
        typer.Option(
            "--no-synthetic",
            help="Disable generation of synthetic chapters if native ones are missing.",
        ),
    ] = False,
    chunk_size: Annotated[
        int | None,
        typer.Option(
            "--chunk-size",
            help="Token chunk size for processing (overrides config).",
            min=100,
        ),
    ] = None,
    chunk_overlap: Annotated[
        int | None,
        typer.Option(
            "--chunk-overlap",
            help="Token chunk overlap (overrides config).",
            min=0,
        ),
    ] = None,
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
    with telemetry.track_command("process"):
        # Ensure configuration exists
        ensure_setup()

        try:
            # Lazy import for faster CLI startup
            from .config import config
            from .pipeline.orchestrator import PipelineOrchestrator

            # Use config values as defaults, allow CLI overrides
            selected_model = model or config.default_model
            selected_output = output or config.default_output_dir
            selected_languages = language or config.default_languages
            selected_temperature = (
                temperature if temperature is not None else config.temperature
            )
            selected_max_tokens = (
                max_tokens if max_tokens is not None else config.max_tokens
            )

            # Create orchestrator
            orchestrator = PipelineOrchestrator(
                model=selected_model,
                output_dir=selected_output,
                languages=selected_languages,
                temperature=selected_temperature,
                max_tokens=selected_max_tokens,
                force=force,
                export_transcript=export_transcript,
                use_chapters=not no_chapters,
                use_synthetic_chapters=not no_synthetic,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )

            async def run_processing() -> None:
                """Determine if input is URL or file and run pipeline."""
                input_path = Path(url)

                # Check if input is an existing file (Batch Mode)
                if input_path.exists() and input_path.is_file():
                    # Removed redundant panel print here since dashboard handles UI
                    try:
                        # Robust encoding handling and line splitting
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
                        return

                    if not urls:
                        console.print("[yellow]⚠ Batch file is empty.[/yellow]")
                        return

                    # Removed: console.print(f"[dim]Found {len(urls)} URLs[/dim]\n")

                    for i, batch_url in enumerate(urls, 1):
                        # Keep this rule as it separates batch items distinctly
                        description = (
                            f"[bold cyan]Batch Item {i}/{len(urls)}[/bold cyan]"
                        )
                        console.rule(description)
                        # Removed redundant URL print as dashboard shows title/status
                        try:
                            await orchestrator.run(batch_url)
                        except Exception as e:
                            console.print(
                                f"[bold red]❌ Batch item failed:[/bold red] {e}"
                            )
                else:
                    # Single URL Mode (Orchestrator handles Video vs Playlist detection)
                    await orchestrator.run(url)

            # Run pipeline
            asyncio.run(run_processing())

        except KeyboardInterrupt:
            console.print("\n[yellow]⚠ Process interrupted by user[/yellow]")
            raise typer.Exit(code=1) from None
        except Exception as e:
            # Import Panel locally
            from rich.panel import Panel

            console.print(
                Panel(f"[bold red]Fatal Error[/bold red]\n{str(e)}", border_style="red")
            )
            logger.exception("Fatal error in CLI process", error=str(e))
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
    with telemetry.track_command("setup"):
        try:
            from .setup_wizard import run_setup_wizard

            run_setup_wizard(force=force)
        except ImportError as e:
            console.print("[red]Setup wizard module missing.[/red]")
            raise typer.Exit(code=1) from e


@app.command()
def config_path() -> None:
    """Show the path to the configuration file."""
    with telemetry.track_command("config_path"):
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
    with telemetry.track_command("version"):
        try:
            from . import __version__

            ver = __version__
        except ImportError:
            ver = "dev"

        console.print(f"[cyan]yt-study[/cyan] version [green]{ver}[/green]")


@app.command()
def update() -> None:
    """Check for updates and show upgrade instructions."""
    with telemetry.track_command("update"):
        from .core.updates import is_update_available, is_frozen
        from . import __version__

        console.print("[cyan]Checking for updates...[/cyan]")
        available, latest = is_update_available()

        if available:
            console.print(f"\n[yellow]A new version of yt-study is available: [green]{latest}[/green] (current: {__version__})[/yellow]")

            if is_frozen():
                console.print("\n[bold]Download the new version from GitHub Releases:[/bold]")
                console.print("[blue]https://github.com/jayss/yt-study/releases[/blue]\n")
            else:
                console.print("\n[bold]Run one of the following to upgrade:[/bold]")
                console.print("  [cyan]uv tool upgrade yt-study[/cyan]")
                console.print("  [dim]or[/dim]")
                console.print("  [cyan]pip install --upgrade yt-study[/cyan]\n")
        elif latest:
            console.print(f"\n[green]You are on the latest version ({__version__}).[/green]\n")
        else:
            console.print("\n[red]Could not check for updates. Please check your internet connection.[/red]\n")


@app.command()
def serve(
    port: Annotated[
        int,
        typer.Option(
            "--port",
            "-p",
            help="Port to run the visualizer on.",
            min=1,
            max=65535,
        ),
    ] = 8080,
    host: Annotated[
        str,
        typer.Option(
            "--host",
            "-H",
            help="Host to run the visualizer on.",
        ),
    ] = "0.0.0.0",
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output directory to scan for projects.",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = None,
) -> None:
    """
    Launch the web-based study material visualizer.

    Scans the output directory and provides an interactive UI to browse
    notes and watch videos with synced timestamps.
    """
    with telemetry.track_command("serve"):
        try:
            from .config import config
            from .ui.web import start_web_ui

            selected_output = output or config.default_output_dir

            console.print(f"\n[bold cyan]🚀 Launching Visualizer[/bold cyan]")
            console.print(f"[dim]Output directory:[/dim] [green]{selected_output}[/green]")
            console.print(f"[dim]URL:[/dim] [bold blue]http://{host}:{port}[/bold blue]\n")

            start_web_ui(port=port, host=host, output_dir=selected_output)
        except Exception as e:
            console.print(f"[red]Error starting visualizer:[/red] {e}")
            raise typer.Exit(code=1) from e


@app.command(name="telemetry")
def telemetry_cmd(
    stats: Annotated[
        bool,
        typer.Option(
            "--stats",
            help="Show usage statistics.",
        ),
    ] = True,
) -> None:
    """
    Manage application telemetry.
    """
    if stats:
        data = telemetry.get_stats()

        table = Table(title="Application Usage Statistics")
        table.add_column("Command", style="cyan")
        table.add_column("Starts", style="magenta")
        table.add_column("Successes", style="green")
        table.add_column("Fails", style="red")

        for cmd, counts in data["commands"].items():
            table.add_row(
                cmd,
                str(counts["starts"]),
                str(counts["successes"]),
                str(counts["fails"]),
            )

        console.print(table)
        total = data["total_commands"]
        success = data["success_count"]
        rate = (success / total * 100) if total > 0 else 0
        console.print(f"\n[dim]Total commands run:[/dim] [bold]{total}[/bold]")
        console.print(f"[dim]Overall success rate:[/dim] [bold]{rate:.1f}%[/bold]")


if __name__ == "__main__":
    app()
