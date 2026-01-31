"""Command-line interface using Typer."""

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Annotated

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

        # Create orchestrator
        orchestrator = PipelineOrchestrator(
            model=selected_model,
            output_dir=selected_output,
            languages=selected_languages,
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
                    console.rule(f"[bold cyan]Batch Item {i}/{len(urls)}[/bold cyan]")
                    # Removed redundant URL print as dashboard shows title/status
                    try:
                        await orchestrator.run(batch_url)
                    except Exception as e:
                        console.print(f"[bold red]❌ Batch item failed:[/bold red] {e}")
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
