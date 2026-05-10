"""Command-line interface using Typer."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any
from urllib.parse import urlparse

import typer

from notewise._constants import (
    CONFIG_FILENAME,
    DEFAULT_NOTES_OUTPUT_FORMAT,
    DEFAULT_TARGET_LANGUAGE,
    DEFAULT_TEMPERATURE,
    DEFAULT_THROTTLE_SECONDS,
    MAX_TEMPERATURE,
    MIN_TEMPERATURE,
    MIN_THROTTLE_SECONDS,
    OAUTH_LOGIN_ALLOWED_PROVIDERS,
    OAUTH_LOGIN_CODEX_ALIAS,
    OAUTH_LOGIN_DIRECT_PROVIDERS,
    OAUTH_LOGIN_PROVIDER_LABELS,
    OAUTH_LOGIN_PROVIDER_PROMPT,
    OAUTH_LOGIN_UNSUPPORTED_PROVIDER_MESSAGE,
    SUPPORTED_NOTES_OUTPUT_FORMATS,
)


if TYPE_CHECKING:
    from notewise.cli._runtime import CliProcessRunner


# Lazy-loaded patch points kept at module scope for test compatibility.
_console: Any = None
config: Any = None
CorePipeline: Any = None
parse_youtube_url: Any = None
extract_playlist_videos: Any = None
get_playlist_info: Any = None
get_video_metadata: Any = None
get_video_details: Any = None
get_source_metadata: Any = None
PipelineDashboard: Any = None
Live: Any = None
run_setup_wizard: Any = None
show_current_config: Any = None
check_for_updates: Any = None
run_oauth_login: Any = None


app = typer.Typer(
    name="notewise",
    help=("Convert YouTube videos and playlists into structured study materials."),
    add_completion=True,
    rich_markup_mode="rich",
    pretty_exceptions_show_locals=False,
)
cache_app = typer.Typer(
    name="cache",
    help="Inspect and manage the local SQLite cache.",
    rich_markup_mode="rich",
)
logs_app = typer.Typer(
    name="logs",
    help="Inspect and manage session logs.",
    rich_markup_mode="rich",
)
auth_app = typer.Typer(
    name="auth",
    help="Authenticate OAuth/device-flow LLM providers.",
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
    """Create a cached Rich console lazily to keep CLI import time low."""
    global _console
    from rich.console import Console

    if _console is None:
        _console = Console()
    return _console


def _get_config_file_path() -> Path:
    """Return the canonical config file path."""
    from notewise.config import get_state_dir

    return get_state_dir() / CONFIG_FILENAME


def _get_config() -> Any:
    """Load shared settings lazily for fast commands."""
    global config
    if config is None:
        from notewise.config import settings as _config

        config = _config
    return config


def _load_process_dependencies() -> None:
    """Populate process-specific lazy globals that tests patch directly."""
    global CorePipeline
    global Live
    global PipelineDashboard
    global extract_playlist_videos
    global get_playlist_info
    global get_source_metadata
    global get_video_details
    global get_video_metadata
    global parse_youtube_url

    _get_config()
    if CorePipeline is None:
        from notewise.pipeline.core import CorePipeline as _CorePipeline

        CorePipeline = _CorePipeline
    if parse_youtube_url is None:
        from notewise.youtube.parser import (
            parse_youtube_url as _parse_youtube_url,
        )

        parse_youtube_url = _parse_youtube_url
    if extract_playlist_videos is None:
        from notewise.youtube.playlist import (
            extract_playlist_videos as _extract_playlist_videos,
        )

        extract_playlist_videos = _extract_playlist_videos
    if get_playlist_info is None:
        from notewise.youtube.metadata import (
            get_playlist_info as _get_playlist_info,
        )

        get_playlist_info = _get_playlist_info
    if get_video_metadata is None:
        from notewise.youtube.metadata import (
            get_video_metadata as _get_video_metadata,
        )

        get_video_metadata = _get_video_metadata
    if get_video_details is None:
        from notewise.youtube.metadata import (
            get_video_details as _get_video_details,
        )

        get_video_details = _get_video_details
    if get_source_metadata is None:
        from notewise.youtube.metadata import (
            get_source_metadata as _get_source_metadata,
        )

        get_source_metadata = _get_source_metadata
    if PipelineDashboard is None:
        from notewise.ui.dashboard import PipelineDashboard as _PipelineDashboard

        PipelineDashboard = _PipelineDashboard
    if Live is None:
        from rich.live import Live as _Live

        Live = _Live


def _load_setup_dependencies() -> None:
    """Populate setup-wizard helpers lazily."""
    global run_setup_wizard
    global show_current_config

    if run_setup_wizard is None:
        from notewise.ui.setup_wizard import run_setup_wizard as _run_setup_wizard

        run_setup_wizard = _run_setup_wizard
    if show_current_config is None:
        from notewise.ui.setup_wizard import (
            show_current_config as _show_current_config,
        )

        show_current_config = _show_current_config


def _load_update_dependencies() -> None:
    """Populate update-check helpers lazily."""
    global check_for_updates

    if check_for_updates is None:
        from notewise.updater import check_for_updates as _check_for_updates

        check_for_updates = _check_for_updates


def _load_auth_dependencies() -> None:
    """Populate OAuth login helpers lazily."""
    global run_oauth_login

    if run_oauth_login is None:
        from notewise.ui.oauth_flow import run_oauth_login as _run_oauth_login

        run_oauth_login = _run_oauth_login


def _print_oauth_provider_choices(choices: list[str]) -> dict[str, str]:
    """Print numbered OAuth provider choices and return the selection map."""
    choice_labels = {
        str(index): choice for index, choice in enumerate(choices, start=1)
    }
    for index, choice in choice_labels.items():
        _get_console().print(
            f"[dim]{index}.[/dim] {OAUTH_LOGIN_PROVIDER_LABELS[choice]}"
        )
    return choice_labels


def _select_oauth_provider(provider: str | None) -> str:
    """Resolve an optional auth provider argument to a concrete OAuth provider."""
    from rich.prompt import Prompt

    choices = list(OAUTH_LOGIN_DIRECT_PROVIDERS)
    if provider is None:
        choice_labels = _print_oauth_provider_choices(choices)
        selected = Prompt.ask(
            OAUTH_LOGIN_PROVIDER_PROMPT,
            choices=list(choice_labels),
        )
        return choice_labels[selected]

    normalized = provider.strip().lower()
    if normalized not in OAUTH_LOGIN_ALLOWED_PROVIDERS:
        allowed = ", ".join(OAUTH_LOGIN_ALLOWED_PROVIDERS)
        raise typer.BadParameter(
            OAUTH_LOGIN_UNSUPPORTED_PROVIDER_MESSAGE.format(allowed=allowed)
        )
    if normalized == OAUTH_LOGIN_CODEX_ALIAS:
        return "chatgpt"
    return normalized


def check_config_exists() -> bool:
    """Check if user configuration exists."""
    return _get_config_file_path().exists()


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
    output_format: Annotated[
        str,
        typer.Option(
            "--format",
            help=(
                "Notes output format. Pass one value or a comma-separated list, "
                "for example [green]md,html[/green]. Supported values: "
                f"[green]{', '.join(SUPPORTED_NOTES_OUTPUT_FORMATS)}[/green]."
            ),
        ),
    ] = DEFAULT_NOTES_OUTPUT_FORMAT,
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
    target_language: Annotated[
        str,
        typer.Option(
            "--target-language",
            help=(
                "Language for generated notes and translated headings "
                "(for example [green]English[/green], [green]Hindi[/green], "
                "or [green]pt-BR[/green])."
            ),
        ),
    ] = DEFAULT_TARGET_LANGUAGE,
    temperature: Annotated[
        float | None,
        typer.Option(
            "--temperature",
            "-t",
            help=(
                "LLM response temperature (overrides config). "
                f"Range: {MIN_TEMPERATURE:.1f} to {MAX_TEMPERATURE:.1f} "
                f"(default = {DEFAULT_TEMPERATURE:.1f})"
            ),
            min=MIN_TEMPERATURE,
            max=MAX_TEMPERATURE,
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
    throttle: Annotated[
        float,
        typer.Option(
            "--throttle",
            help=(
                "Delay repeated LLM generation calls by this many seconds. "
                "Useful for pacing chunked or chapter-based runs on low-quota plans."
            ),
            min=MIN_THROTTLE_SECONDS,
        ),
    ] = DEFAULT_THROTTLE_SECONDS,
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
                "Outputs plain progress lines to stdout - "
                "useful for CI, cron jobs, and log piping."
            ),
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Write DEBUG-level diagnostics to the session log file.",
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
    timestamps: Annotated[
        bool,
        typer.Option(
            "--timestamps",
            help=(
                "Prefix generated chapter headers with their chapter start time, "
                "for example [green]# [00:34] Chapter Title[/green]."
            ),
        ),
    ] = False,
    chapter_directory_output: Annotated[
        bool,
        typer.Option(
            "--chapter-directory-output",
            help=(
                "Write per-chapter Markdown files into a video folder. By default, "
                "chapter-aware generation is combined into a single final notes file."
            ),
        ),
    ] = False,
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
      [cyan]notewise process "https://youtube.com/watch?v=VIDEO_ID"[/cyan]
      [cyan]notewise process "URL" -m gpt-4o[/cyan]
      [cyan]notewise process batch_urls.txt -o ./course-notes[/cyan]
    """
    console = _get_console()
    runner: CliProcessRunner | None = None

    try:
        _load_process_dependencies()
        from notewise.cli._runtime import CliProcessRunner
        from notewise.errors import ValidationError
        from notewise.llm.provider import suppress_litellm_noise
        from notewise.logging import configure_logging, get_session_log_path
        from notewise.pipeline._documents import normalize_output_formats

        configure_logging(verbose=verbose)
        suppress_litellm_noise()
        settings = _get_config()
        try:
            selected_output_formats = normalize_output_formats(output_format)
        except ValidationError as error:
            raise typer.BadParameter(str(error), param_hint="--format") from error

        runner = CliProcessRunner(
            console=console,
            config=settings,
            core_pipeline_cls=CorePipeline,
            parse_youtube_url=parse_youtube_url,
            extract_playlist_videos=extract_playlist_videos,
            get_playlist_info=get_playlist_info,
            dashboard_cls=PipelineDashboard,
            live_cls=Live,
            selected_model=model or settings.default_model,
            selected_output=output or settings.default_output_dir,
            selected_output_formats=selected_output_formats,
            selected_languages=language or settings.default_languages,
            selected_target_language=target_language,
            selected_temperature=(
                temperature if temperature is not None else settings.temperature
            ),
            selected_max_tokens=(
                max_tokens if max_tokens is not None else settings.max_tokens
            ),
            selected_throttle_seconds=throttle,
            force=force,
            no_ui=no_ui,
            quiz=quiz,
            export_transcript=export_transcript,
            timestamps=timestamps,
            chapter_directory_output=chapter_directory_output,
            selected_cookie_file=(
                str(cookie_file)
                if cookie_file is not None
                else settings.youtube_cookie_file
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
        import structlog

        structlog.get_logger(__name__).exception("cli.fatal_error")
        if runner is not None:
            runner.print_single_failure(
                "Unexpected Error",
                "notewise hit an unexpected internal error before it could finish.",
                item_label="Status",
                intro="Please check the current log file and try again.",
            )
        else:
            from notewise.logging import get_session_log_path

            console.print(
                "\n[red]notewise hit an unexpected internal error.[/red]\n"
                f"[dim]Current log: {get_session_log_path()}[/dim]\n"
            )
        raise typer.Exit(code=1) from None


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """
    [bold cyan]notewise[/bold cyan]: AI-Powered Video Study Notes Generator.

    Convert YouTube content into structured Markdown notes.
    """
    if ctx.invoked_subcommand is None:
        console = _get_console()
        from notewise.cli._banner import print_banner

        print_banner(console)
        console.print()
        console.print("[bold]Quick Start[/bold]")
        console.print(
            '  [cyan]notewise process "https://youtube.com/watch?v=ID"[/cyan]'
        )
        console.print(
            '  [cyan]notewise process "https://youtube.com/playlist?list=ID"[/cyan]'
        )
        console.print("  [cyan]notewise process urls.txt[/cyan]")
        console.print()
        console.print("[bold]Commands[/bold]")
        console.print("  [cyan]process[/cyan]      Generate study notes")
        console.print("  [cyan]setup[/cyan]        Configure API keys")
        console.print("  [cyan]config[/cyan]       Show the current masked config")
        console.print("  [cyan]auth[/cyan]         Login to OAuth providers")
        console.print("  [cyan]stats[/cyan]        View processing totals")
        console.print("  [cyan]history[/cyan]      View recent videos")
        console.print("  [cyan]info[/cyan]         Show config or inspect a URL")
        console.print("  [cyan]doctor[/cyan]       Check runtime health")
        console.print("  [cyan]cache[/cyan]        Manage cached data")
        console.print("  [cyan]logs[/cyan]         Inspect session logs")
        console.print("  [cyan]edit-config[/cyan]  Open config in your editor")
        console.print("  [cyan]update[/cyan]       Check for a newer release")
        console.print("  [cyan]version[/cyan]      Show installed version")
        console.print()
        console.print(
            "[dim]Run [cyan]notewise COMMAND --help[/cyan] for command details.[/dim]"
        )


@app.command()
def setup(
    force: Annotated[
        bool,
        typer.Option(
            "--force", "-f", help="Force reconfiguration even if config exists."
        ),
    ] = False,
    show: Annotated[
        bool,
        typer.Option(
            "--show",
            help="Show the current configuration without rewriting it.",
        ),
    ] = False,
) -> None:
    """
    Configure API keys and preferences interactively.

    Runs a wizard to generate the [bold]~/.notewise/config.env[/bold] file.
    """
    _load_setup_dependencies()
    if show:
        show_current_config(console=_get_console())
        return
    run_setup_wizard(force=force)


@app.command("config")
def show_config_command() -> None:
    """Show the current resolved configuration with secrets masked."""
    _load_setup_dependencies()
    show_current_config(console=_get_console())


@app.command()
def config_path() -> None:
    """Show the path to the configuration file."""
    console = _get_console()
    config_file = _get_config_file_path()

    if config_file.exists():
        console.print(f"\n[cyan]Configuration file:[/cyan] {config_file}")
        console.print("\n[dim]To edit: Open the file above in a text editor[/dim]")
        console.print(
            "[dim]To reconfigure: Run[/dim] [cyan]notewise setup --force[/cyan]\n"
        )
    else:
        console.print("\n[yellow]No configuration found.[/yellow]")
        console.print(
            "[dim]Run[/dim] [cyan]notewise setup[/cyan] [dim]to create one.[/dim]\n"
        )


@app.command()
def version() -> None:
    """Show version information."""
    console = _get_console()
    try:
        from notewise import __version__

        ver = __version__
    except ImportError:
        ver = "dev"

    console.print(f"[cyan]notewise[/cyan] version [green]{ver}[/green]")


@app.command()
def update() -> None:
    """Check for a newer NoteWise release and show upgrade commands."""
    console = _get_console()
    _load_update_dependencies()
    from notewise.errors import UpdateError

    try:
        status = check_for_updates()
    except UpdateError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from None

    if not status.available:
        console.print("[green]You already have the latest NoteWise version.[/green]")
        console.print(f"[dim]Install source: {status.install_source}[/dim]")
        return

    console.print(
        "[yellow]Update available:[/yellow] "
        f"[green]{status.latest_version}[/green] "
        f"(current: {status.current_version})"
    )
    console.print(f"[dim]Install source: {status.install_source}[/dim]")
    console.print(f"[dim]{status.release_url}[/dim]")
    console.print()
    console.print("[bold]Upgrade with:[/bold]")
    for command in status.update_commands:
        console.print(f"  [cyan]{command}[/cyan]")


@app.command()
def stats(
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            help="Filter aggregate stats to a single model.",
        ),
    ] = None,
    since: Annotated[
        str | None,
        typer.Option(
            "--since",
            help="Filter to the last N days. Examples: 7 or 30d.",
        ),
    ] = None,
) -> None:
    """Show aggregate processing statistics from the local cache."""
    from notewise.cli._admin import render_stats

    render_stats(_get_console(), since=since, model=model)


@app.command()
def history(
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            min=1,
            help="Maximum number of recent videos to show.",
        ),
    ] = 10,
) -> None:
    """Show recently processed videos from the local cache."""
    from notewise.cli._admin import render_history

    render_history(_get_console(), limit=limit)


@app.command()
def info(
    url: Annotated[
        str | None,
        typer.Argument(
            help="Optional YouTube video or playlist URL to inspect.",
            show_default=False,
        ),
    ] = None,
) -> None:
    """Show runtime info or inspect a YouTube source without processing it."""
    console = _get_console()
    if url is None:
        from notewise.cli._admin import render_runtime_info

        render_runtime_info(console)
        return

    _load_process_dependencies()
    settings = _get_config()
    from notewise.cli._admin import render_source_info
    from notewise.cli._formatters import print_single_failure
    from notewise.errors import PlaylistError, ValidationError, VideoUnavailableError

    try:
        with console.status("Inspecting source..."):
            asyncio.run(
                render_source_info(
                    console,
                    url=url,
                    parse_youtube_url=parse_youtube_url,
                    get_video_details=get_video_details,
                    get_source_metadata=get_source_metadata,
                    get_playlist_info=get_playlist_info,
                    extract_playlist_videos=extract_playlist_videos,
                    cookie_file=settings.youtube_cookie_file,
                )
            )
    except (ValidationError, ValueError) as error:
        print_single_failure(
            console,
            "Input Error",
            str(error),
            item_label="Source",
        )
        raise typer.Exit(code=1) from None
    except (PlaylistError, VideoUnavailableError) as error:
        print_single_failure(
            console,
            "Source Error",
            str(error),
            item_label="Source",
        )
        raise typer.Exit(code=1) from None
    except Exception:
        import structlog

        structlog.get_logger(__name__).exception("cli.info_error")
        print_single_failure(
            console,
            "Unexpected Error",
            "notewise could not inspect this source. "
            "Check the current log for details.",
            item_label="Source",
        )
        raise typer.Exit(code=1) from None


@app.command()
def doctor() -> None:
    """Run a non-destructive health check for config, cache, and logs."""
    from notewise.cli._admin import render_doctor

    render_doctor(_get_console())


@auth_app.command("login")
def auth_login(
    provider: Annotated[
        str | None,
        typer.Argument(
            help="OAuth provider: chatgpt or github_copilot; codex aliases chatgpt.",
        ),
    ] = None,
) -> None:
    """Run LiteLLM OAuth/device-flow login for subscription providers."""
    console = _get_console()
    selected_provider = _select_oauth_provider(provider)
    _load_auth_dependencies()
    if not run_oauth_login(selected_provider, console=console):
        raise typer.Exit(code=1)


@app.command("edit-config")
def edit_config() -> None:
    """Open the config file in the configured editor or OS default editor."""
    from notewise.cli._admin import edit_config as open_config_in_editor

    open_config_in_editor(_get_console())


@cache_app.command("info")
def cache_info() -> None:
    """Show cache database metadata and entry counts."""
    from notewise.cli._admin import render_cache_info

    render_cache_info(_get_console())


@cache_app.callback(invoke_without_command=True)
def cache(
    ctx: typer.Context,
    info: Annotated[
        bool,
        typer.Option(
            "--info",
            help="Show cache database metadata and entry counts.",
        ),
    ] = False,
    show: Annotated[
        str | None,
        typer.Option(
            "--show",
            metavar="VIDEO_ID",
            help="Show cached metadata for a specific video.",
        ),
    ] = None,
    clear: Annotated[
        bool,
        typer.Option(
            "--clear",
            help="Delete the local cache database.",
        ),
    ] = False,
    prune: Annotated[
        int | None,
        typer.Option(
            "--prune",
            min=0,
            metavar="DAYS",
            help="Prune stale cache entries older than this many days.",
        ),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="Skip confirmation when used with --clear.",
        ),
    ] = False,
) -> None:
    """Inspect and manage the local SQLite cache."""
    if ctx.invoked_subcommand is not None:
        return

    selected_actions = (
        int(info) + int(show is not None) + int(clear) + int(prune is not None)
    )
    if selected_actions > 1:
        raise typer.BadParameter(
            "Use only one of --info, --show, --clear, or --prune at a time."
        )
    if yes and not clear:
        raise typer.BadParameter("--yes can only be used together with --clear.")

    if show is not None:
        cache_show(show)
        return
    if clear:
        cache_clear(yes=yes)
        return
    if prune is not None:
        cache_prune(older_than=prune)
        return
    cache_info()


@cache_app.command("show")
def cache_show(
    video_id: Annotated[
        str,
        typer.Argument(help="Video ID to inspect in the cache."),
    ],
) -> None:
    """Show cached metadata for a specific video."""
    from notewise.cli._admin import render_cache_entry

    render_cache_entry(_get_console(), video_id=video_id)


@cache_app.command("clear")
def cache_clear(
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="Skip the confirmation prompt and clear the cache immediately.",
        ),
    ] = False,
) -> None:
    """Delete the local cache database."""
    console = _get_console()
    from notewise.cli._admin import clear_cache

    if not yes and not typer.confirm("Delete the local cache database?"):
        console.print("[yellow]Cancelled.[/yellow]")
        return
    clear_cache(console)


@cache_app.command("prune")
def cache_prune(
    older_than: Annotated[
        int,
        typer.Option(
            "--older-than",
            min=0,
            help="Remove cache entries older than this many days.",
        ),
    ] = 30,
) -> None:
    """Prune stale cache entries by age."""
    from notewise.cli._admin import prune_cache

    prune_cache(_get_console(), older_than_days=older_than)


@logs_app.callback(invoke_without_command=True)
def logs(
    ctx: typer.Context,
    tail: Annotated[
        int | None,
        typer.Option(
            "--tail",
            min=1,
            help="Tail the latest session log with the last N lines.",
        ),
    ] = None,
    open: Annotated[
        bool,
        typer.Option(
            "--open",
            help="Open the log directory in the system file manager.",
        ),
    ] = False,
) -> None:
    """Show recent session logs or tail the latest log."""
    if ctx.invoked_subcommand is not None:
        return
    from notewise.cli._admin import render_logs

    render_logs(_get_console(), tail=tail, open_dir=open)


@logs_app.command("clean")
def logs_clean(
    all_logs: Annotated[
        bool,
        typer.Option(
            "--all",
            help="Remove all inactive log files instead of only older ones.",
        ),
    ] = False,
    older_than: Annotated[
        int,
        typer.Option(
            "--older-than",
            min=0,
            help="Remove logs older than this many days.",
        ),
    ] = 7,
) -> None:
    """Prune old log files."""
    from notewise.cli._admin import clean_logs

    clean_logs(_get_console(), all_logs=all_logs, older_than_days=older_than)


app.add_typer(cache_app, name="cache")
app.add_typer(logs_app, name="logs")
app.add_typer(auth_app, name="auth")


if __name__ == "__main__":
    app()
