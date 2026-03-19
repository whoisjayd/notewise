"""Command-line interface using Typer."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

import structlog
import typer

from yt_study._constants import CONFIG_FILENAME
from yt_study.cli.runtime import CliProcessRunner


# Lazy-loaded patch points kept at module scope for test compatibility.
config: Any = None
CorePipeline: Any = None
parse_youtube_url: Any = None
extract_playlist_videos: Any = None
get_playlist_info: Any = None
PipelineDashboard: Any = None
Live: Any = None
run_setup_wizard: Any = None


app = typer.Typer(
    name="yt-study",
    help=(
        "🎓 Convert YouTube videos and playlists into comprehensive "
        "study materials using AI."
    ),
    add_completion=True,
    rich_markup_mode="rich",
)

_SCHEMELESS_YOUTUBE_PREFIXES = (
    "youtube.com/",
    "www.youtube.com/",
    "m.youtube.com/",
    "music.youtube.com/",
    "youtu.be/",
)


def _get_console() -> Any:
    """Create a Rich console lazily to keep CLI import time low."""
    from rich.console import Console

    return Console()


def _get_config_file_path() -> Path:
    """Return the canonical config file path."""
    from yt_study.config import get_state_dir

    return get_state_dir() / CONFIG_FILENAME


def _load_cli_dependencies() -> None:
    """Populate lazy module globals that tests patch directly."""
    global CorePipeline
    global Live
    global PipelineDashboard
    global config
    global extract_playlist_videos
    global get_playlist_info
    global parse_youtube_url
    global run_setup_wizard

    if Live is None:
        from rich.live import Live as _Live

        Live = _Live
    if config is None:
        from yt_study.config import settings as _config

        config = _config
    if CorePipeline is None:
        from yt_study.services.pipeline import CorePipeline as _CorePipeline

        CorePipeline = _CorePipeline
    if parse_youtube_url is None:
        from yt_study.infrastructure.youtube.parser import (
            parse_youtube_url as _parse_youtube_url,
        )

        parse_youtube_url = _parse_youtube_url
    if extract_playlist_videos is None:
        from yt_study.infrastructure.youtube.playlist import (
            extract_playlist_videos as _extract_playlist_videos,
        )

        extract_playlist_videos = _extract_playlist_videos
    if get_playlist_info is None:
        from yt_study.infrastructure.youtube.metadata import (
            get_playlist_info as _get_playlist_info,
        )

        get_playlist_info = _get_playlist_info
    if PipelineDashboard is None:
        from yt_study.ui.dashboard import PipelineDashboard as _PipelineDashboard

        PipelineDashboard = _PipelineDashboard
    if run_setup_wizard is None:
        from yt_study.ui.setup_wizard import run_setup_wizard as _run_setup_wizard

        run_setup_wizard = _run_setup_wizard


def check_config_exists() -> bool:
    """Check if user configuration exists."""
    return _get_config_file_path().exists()


def ensure_setup() -> None:
    """Ensure setup wizard has been run before processing."""
    if not check_config_exists():
        console = _get_console()
        _load_cli_dependencies()
        console.print(
            "\n[yellow]⚠ No configuration found. Running setup wizard...[/yellow]\n"
        )
        run_setup_wizard(force=False)


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
    export_transcript: Annotated[
        str | None,
        typer.Option(
            "--export-transcript",
            help=(
                "Export raw transcript to a file. "
                "Format: [green]txt[/green] (plain text) or "
                "[green]json[/green] (with timestamps)."
            ),
        ),
    ] = None,
    cookie_file: Annotated[
        Path | None,
        typer.Option(
            "--cookie-file",
            "--cookies",
            help=(
                "Path to Netscape-format cookies .txt file used for YouTube requests."
            ),
            exists=False,
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
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
    console = _get_console()
    runner: CliProcessRunner | None = None

    try:
        _load_cli_dependencies()
        from yt_study.logging_config import configure_logging, get_session_log_path

        configure_logging()
        ensure_setup()

        runner = CliProcessRunner(
            console=console,
            config=config,
            core_pipeline_cls=CorePipeline,
            parse_youtube_url=parse_youtube_url,
            extract_playlist_videos=extract_playlist_videos,
            get_playlist_info=get_playlist_info,
            dashboard_cls=PipelineDashboard,
            live_cls=Live,
            selected_model=model or config.default_model,
            selected_output=output or config.default_output_dir,
            selected_languages=language or config.default_languages,
            selected_temperature=(
                temperature if temperature is not None else config.temperature
            ),
            selected_max_tokens=(
                max_tokens if max_tokens is not None else config.max_tokens
            ),
            force=force,
            no_ui=no_ui,
            quiz=quiz,
            export_transcript=export_transcript,
            selected_cookie_file=(
                str(cookie_file)
                if cookie_file is not None
                else config.youtube_cookie_file
            ),
        )

        had_failures = asyncio.run(
            runner.run(url, looks_like_batch_file_path=looks_like_batch_file_path)
        )
        if had_failures:
            raise typer.Exit(code=1)

    except KeyboardInterrupt:
        if runner is not None:
            runner.print_single_failure(
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
        structlog.get_logger(__name__).exception("cli.fatal_error")
        if runner is not None:
            runner.print_single_failure(
                "Unexpected Error",
                "yt-study hit an unexpected internal error before it could finish.",
                item_label="Status",
                intro="Please check the current log file and try again.",
            )
        else:
            from yt_study.logging_config import get_session_log_path

            console.print(
                "\n[red]yt-study hit an unexpected internal error.[/red]\n"
                f"[dim]Current log: {get_session_log_path()}[/dim]\n"
            )
        raise typer.Exit(code=1) from None


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """
    [bold cyan]yt-study[/bold cyan]: AI-Powered Video Study Notes Generator.

    Convert YouTube content into structured Markdown notes.
    """
    if ctx.invoked_subcommand is None:
        console = _get_console()
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
    _load_cli_dependencies()
    run_setup_wizard(force=force)


@app.command()
def config_path() -> None:
    """Show the path to the configuration file."""
    console = _get_console()
    config_file = _get_config_file_path()

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
    console = _get_console()
    try:
        from yt_study import __version__

        ver = __version__
    except ImportError:
        ver = "dev"

    console.print(f"[cyan]yt-study[/cyan] version [green]{ver}[/green]")


if __name__ == "__main__":
    app()
