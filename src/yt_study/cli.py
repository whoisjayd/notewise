"""Command-line interface using Typer."""

import asyncio
import logging
import os
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from typing_extensions import Annotated

# Suppress LiteLLM verbose logging
os.environ["LITELLM_LOG"] = "ERROR"
logging.getLogger("LiteLLM").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Setup logging
logging.basicConfig(
    level=logging.WARNING,  # Only show warnings and errors
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, show_time=False)]
)

app = typer.Typer(
    name="yt-study",
    help="🎓 Convert YouTube videos and playlists into comprehensive study materials using AI.",
    add_completion=True,
)

console = Console()


def check_config_exists() -> bool:
    """Check if user configuration exists."""
    config_path = Path.home() / ".yt-study" / "config.env"
    return config_path.exists()


def ensure_setup():
    """Ensure setup wizard has been run."""
    if not check_config_exists():
        console.print("\n[yellow]⚠ No configuration found. Running setup wizard...[/yellow]\n")
        from .setup_wizard import run_setup_wizard
        run_setup_wizard(force=False)


@app.command()
def process(
    url: Annotated[
        str,
        typer.Argument(
            help="YouTube video or playlist URL"
        )
    ],
    model: Annotated[
        Optional[str],
        typer.Option(
            "--model", "-m",
            help="LLM model (overrides config)"
        )
    ] = None,
    output: Annotated[
        Optional[Path],
        typer.Option(
            "--output", "-o",
            help="Output directory (overrides config)"
        )
    ] = None,
    language: Annotated[
        Optional[List[str]],
        typer.Option(
            "--language", "-l",
            help="Preferred transcript languages (e.g., en, hi)"
        )
    ] = None,
) -> None:
    """
    Generate comprehensive study notes from YouTube videos or playlists.
    
    \b
    Examples:
      yt-study process "https://youtube.com/watch?v=VIDEO_ID"
      yt-study process "URL" -m gpt-4o
      yt-study process "URL" -l hi -l en -o ./my-notes
    
    \b
    First time? Run: yt-study setup
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
        
        # Create orchestrator
        orchestrator = PipelineOrchestrator(
            model=selected_model,
            output_dir=selected_output,
            languages=language or config.default_languages
        )
        
        # Run pipeline
        asyncio.run(orchestrator.run(url))
        
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠ Interrupted by user[/yellow]")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"\n[red]✗ Error: {str(e)}[/red]")
        raise typer.Exit(code=1)


# Make process the default command when called without subcommand
@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """
    🎓 Convert YouTube videos and playlists into comprehensive study materials using AI.
    
    \b
    Quick start:
      yt-study "https://youtube.com/watch?v=VIDEO_ID"
      yt-study setup  # Configure your LLM provider
    
    \b
    Commands:
      process     Generate study notes from YouTube URL
      setup       Configure API keys and preferences  
      config-path Show configuration file location
      version     Show version information
    """
    # Only show help if no subcommand is being invoked
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


@app.command()
def setup(
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Force reconfiguration")
    ] = False
):
    """
    Run the interactive setup wizard to configure API keys and preferences.
    
    \b
    This will guide you through:
    - Selecting your preferred LLM provider (Gemini, ChatGPT, Claude, etc.)
    - Choosing a specific model
    - Setting up your API key
    - Configuring output directory
    """
    from .setup_wizard import run_setup_wizard
    run_setup_wizard(force=force)


@app.command()
def config_path():
    """Show the path to the configuration file."""
    config_file = Path.home() / ".yt-study" / "config.env"
    
    if config_file.exists():
        console.print(f"\n[cyan]Configuration file:[/cyan] {config_file}")
        console.print(f"\n[dim]To edit: Open the file above in a text editor[/dim]")
        console.print(f"[dim]To reconfigure: Run[/dim] [cyan]yt-study setup --force[/cyan]\n")
    else:
        console.print(f"\n[yellow]No configuration found.[/yellow]")
        console.print(f"[dim]Run[/dim] [cyan]yt-study setup[/cyan] [dim]to create one.[/dim]\n")


@app.command()
def version():
    """Show version information."""
    from . import __version__
    console.print(f"[cyan]yt-study[/cyan] version [green]{__version__}[/green]")


if __name__ == "__main__":
    app()
