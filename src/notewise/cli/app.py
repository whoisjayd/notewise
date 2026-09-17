"""Command-line interface using Typer."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, NoReturn
from urllib.parse import urlparse

import typer

from notewise._constants import (
    DEFAULT_CACHE_PRUNE_OLDER_THAN_DAYS,
    DEFAULT_HISTORY_LIMIT,
    DEFAULT_LOGS_CLEAN_OLDER_THAN_DAYS,
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
    SCHEMELESS_YOUTUBE_PREFIXES,
    SUPPORTED_NOTES_OUTPUT_FORMATS,
    TRANSCRIPT_COLLISION_SUFFIX_START,
    TRANSCRIPT_COMMAND_FILE_STEM_SUFFIX,
    TRANSCRIPT_COMMAND_PLAYLIST_MESSAGE,
    TRANSCRIPT_JSON_OUTPUT_FORMAT,
    TRANSCRIPT_SAVED_PREFIX,
    TRANSCRIPT_STATUS_MESSAGE,
    TRANSCRIPT_TEXT_OUTPUT_FORMAT,
)
from notewise.errors import (
    ConfigurationError,
    IPBlockError,
    TranscriptUnavailableError,
    ValidationError,
    VideoUnavailableError,
    format_user_error,
)
from notewise.logging import _is_sensitive_key


if TYPE_CHECKING:
    from notewise.cli._runtime import CliProcessRunner
    from notewise.domain.youtube import VideoTranscript


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
fetch_transcript: Any = None
PipelineDashboard: Any = None
Live: Any = None
run_setup_wizard: Any = None
show_current_config: Any = None
check_for_updates: Any = None
run_oauth_login: Any = None


_HELP_OPTION_NAMES = ["-h", "--help"]

app = typer.Typer(
    name="notewise",
    help=("Convert YouTube videos and playlists into structured study materials."),
    add_completion=True,
    rich_markup_mode="rich",
    pretty_exceptions_show_locals=False,
    context_settings={"help_option_names": _HELP_OPTION_NAMES},
)
cache_app = typer.Typer(
    name="cache",
    help="Inspect and manage the local SQLite cache.",
    rich_markup_mode="rich",
    context_settings={"help_option_names": _HELP_OPTION_NAMES},
)
logs_app = typer.Typer(
    name="logs",
    help="Inspect and manage session logs.",
    rich_markup_mode="rich",
    context_settings={"help_option_names": _HELP_OPTION_NAMES},
)
auth_app = typer.Typer(
    name="auth",
    help="Authenticate OAuth/device-flow LLM providers.",
    rich_markup_mode="rich",
    context_settings={"help_option_names": _HELP_OPTION_NAMES},
)

inference_app = typer.Typer(
    name="inference",
    help="Manage saved OpenAI-compatible inference endpoints.",
    rich_markup_mode="rich",
    context_settings={"help_option_names": _HELP_OPTION_NAMES},
)
config_app = typer.Typer(
    name="config",
    help="View and manage persisted configuration.",
    rich_markup_mode="rich",
    context_settings={"help_option_names": _HELP_OPTION_NAMES},
)


def _get_console() -> Any:
    """Create a cached Rich console lazily to keep CLI import time low."""
    global _console
    from rich.console import Console

    if _console is None:
        _console = Console()
    return _console


def _get_config_file_path() -> Path:
    """Return the canonical config database path."""
    from notewise.config import get_config_db_path

    return get_config_db_path()


def _format_config_validation_error(error: Any) -> str:
    """Return a user-facing summary for settings validation failures."""
    from notewise.config import format_settings_validation_error

    return format_settings_validation_error(error)


def _print_configuration_error(error: Exception) -> None:
    """Render expected configuration failures without a traceback."""
    from notewise.cli._formatters import print_single_failure

    print_single_failure(
        _get_console(),
        "Configuration Error",
        str(error),
        item_label="Config",
    )


def _get_config_or_exit() -> Any:
    """Load shared settings, printing a clean error and exiting on failure."""
    try:
        return _get_config()
    except ConfigurationError as error:
        _print_configuration_error(error)
        raise typer.Exit(code=1) from None


def _get_config() -> Any:
    """Load shared settings lazily for fast commands."""
    global config
    if config is None:
        from pydantic import ValidationError as PydanticValidationError

        from notewise.config import settings as _config
        from notewise.errors import ConfigurationError

        try:
            _config._get_instance()
        except PydanticValidationError as error:
            raise ConfigurationError(_format_config_validation_error(error)) from error

        config = _config
    return config


def _reload_and_validate_config() -> None:
    """Force AppSettings to reload after a config write, surfacing validation errors."""
    from pydantic import ValidationError as PydanticValidationError

    from notewise.config import settings as _config

    global config
    try:
        _config.reload()
    except PydanticValidationError as error:
        _print_configuration_error(
            ConfigurationError(_format_config_validation_error(error))
        )
        raise typer.Exit(code=1) from None
    config = _config


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
    global fetch_transcript

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
    if fetch_transcript is None:
        from notewise.youtube.transcript import (
            fetch_transcript as _fetch_transcript,
        )

        fetch_transcript = _fetch_transcript
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
    from notewise.config import config_exists

    return config_exists()


def looks_like_batch_file_path(value: str) -> bool:
    """Heuristic for path-like batch-file inputs that should not be parsed as URLs."""
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return False

    normalized = value.strip().lower().replace("\\", "/")
    if normalized.startswith(SCHEMELESS_YOUTUBE_PREFIXES):
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
        str | None,
        typer.Argument(
            help=(
                "YouTube video or playlist URL, or path to a text file containing URLs."
            ),
            show_default=False,
        ),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            "-m",
            help=(
                "AI model. Examples: [green]gpt-5.5[/green], "
                "[green]gemini/gemini-3.1-pro-preview[/green]."
            ),
            rich_help_panel="Common",
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
            rich_help_panel="Common",
        ),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option(
            "--format",
            "-r",
            help=(
                "Output format(s), comma-separated. Example: [green]md,html[/green]. "
                "Supported: "
                f"[green]{', '.join(SUPPORTED_NOTES_OUTPUT_FORMATS)}[/green]."
            ),
            rich_help_panel="Common",
        ),
    ] = DEFAULT_NOTES_OUTPUT_FORMAT,
    language: Annotated[
        list[str] | None,
        typer.Option(
            "--language",
            "-l",
            help=("Transcript languages, e.g. [green]en[/green], [green]hi[/green]."),
            rich_help_panel="Common",
        ),
    ] = None,
    target_language: Annotated[
        str,
        typer.Option(
            "--target-language",
            "-L",
            help=(
                "Generated notes language, e.g. [green]English[/green], "
                "[green]Hindi[/green], [green]pt-BR[/green]."
            ),
            rich_help_panel="Common",
        ),
    ] = DEFAULT_TARGET_LANGUAGE,
    temperature: Annotated[
        float | None,
        typer.Option(
            "--temperature",
            "-t",
            help=(
                f"LLM temperature, {MIN_TEMPERATURE:.1f}-{MAX_TEMPERATURE:.1f} "
                f"(default {DEFAULT_TEMPERATURE:.1f})."
            ),
            min=MIN_TEMPERATURE,
            max=MAX_TEMPERATURE,
            rich_help_panel="Advanced",
        ),
    ] = None,
    max_tokens: Annotated[
        int | None,
        typer.Option(
            "--max-tokens",
            "-k",
            help=("Maximum LLM response tokens. Omit for the model default."),
            min=1,
            rich_help_panel="Advanced",
        ),
    ] = None,
    throttle: Annotated[
        float,
        typer.Option(
            "--throttle",
            "-w",
            help=("Delay repeated LLM calls, useful for low-quota providers."),
            min=MIN_THROTTLE_SECONDS,
            rich_help_panel="Advanced",
        ),
    ] = DEFAULT_THROTTLE_SECONDS,
    base_url: Annotated[
        str | None,
        typer.Option(
            "--base-url",
            help="OpenAI-compatible endpoint URL for this run.",
            rich_help_panel="Advanced",
        ),
    ] = None,
    api_key: Annotated[
        str | None,
        typer.Option(
            "--api-key",
            help="OpenAI-compatible endpoint API key for this run.",
            rich_help_panel="Advanced",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            "-F",
            help=("Re-process videos even when cached outputs already exist."),
            rich_help_panel="Advanced",
        ),
    ] = False,
    no_ui: Annotated[
        bool,
        typer.Option(
            "--no-ui",
            "-n",
            help=("Disable the Rich dashboard and print plain progress lines."),
            rich_help_panel="Advanced",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Write DEBUG-level diagnostics to the session log file.",
            rich_help_panel="Advanced",
        ),
    ] = False,
    quiz: Annotated[
        bool,
        typer.Option(
            "--quiz",
            "-q",
            help="Generate a multiple-choice quiz alongside the notes.",
            rich_help_panel="Extras",
        ),
    ] = False,
    export_transcript: Annotated[
        str | None,
        typer.Option(
            "--export-transcript",
            "-x",
            help=(
                "Export raw transcript as [green]txt[/green] or [green]json[/green]."
            ),
            rich_help_panel="Extras",
        ),
    ] = None,
    timestamps: Annotated[
        bool,
        typer.Option(
            "--timestamps",
            "-s",
            help=(
                "Prefix chapter headings with start times, e.g. [green][00:34][/green]."
            ),
            rich_help_panel="Extras",
        ),
    ] = False,
    chapter_directory_output: Annotated[
        bool,
        typer.Option(
            "--chapter-directory-output",
            "-C",
            help=("Write per-chapter Markdown files into a video folder."),
            rich_help_panel="Extras",
        ),
    ] = False,
    cookie_file: Annotated[
        Path | None,
        typer.Option(
            "--cookie-file",
            "--cookies",
            "-c",
            help=("Netscape-format cookies .txt file for YouTube requests."),
            exists=False,
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
            rich_help_panel="Advanced",
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
      [cyan]notewise process "URL" -m gpt-5.5 -f[/cyan]
      [cyan]notewise process batch_urls.txt -o ./course-notes[/cyan]
    """
    console = _get_console()
    if url is None:
        from rich.prompt import Prompt

        url = Prompt.ask("YouTube video/playlist URL, or path to a batch file").strip()
        if not url:
            console.print("[red]A URL or batch file path is required.[/red]")
            raise typer.Exit(code=1)

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
        selected_model = model or settings.default_model
        get_custom_endpoint = getattr(settings, "get_custom_endpoint_for_model", None)
        configured_endpoint_value = (
            get_custom_endpoint(selected_model)
            if callable(get_custom_endpoint)
            else None
        )
        configured_endpoint = (
            configured_endpoint_value
            if (
                isinstance(configured_endpoint_value, tuple)
                and len(configured_endpoint_value) == 2
                and all(isinstance(value, str) for value in configured_endpoint_value)
            )
            else None
        )
        if base_url is not None:
            from notewise.errors import CustomEndpointError
            from notewise.llm.custom_endpoint import normalize_openai_base_url

            try:
                selected_api_base = normalize_openai_base_url(base_url)
            except CustomEndpointError as error:
                raise typer.BadParameter(str(error), param_hint="--base-url") from error
        elif configured_endpoint is not None:
            selected_api_base = configured_endpoint[0]
        else:
            selected_api_base = None

        selected_api_key = (
            api_key
            if api_key is not None
            else configured_endpoint[1]
            if (
                configured_endpoint is not None
                and selected_api_base == configured_endpoint[0]
            )
            else None
        )
        if (
            base_url is not None
            and configured_endpoint is not None
            and selected_api_key is None
        ):
            raise typer.BadParameter(
                "An explicit --api-key is required when --base-url changes "
                "a saved endpoint.",
                param_hint="--api-key",
            )

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
            selected_model=selected_model,
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
            selected_api_base=selected_api_base,
            selected_api_key=selected_api_key,
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
    except typer.BadParameter as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from None
    except ConfigurationError as error:
        _print_configuration_error(error)
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


async def _download_video_transcript(
    video_id: str,
    languages: list[str],
    cookie_file: str | None,
) -> tuple[str, VideoTranscript]:
    """Fetch metadata title plus transcript, reusing video_data when available."""
    from notewise.youtube.metadata import video_metadata_from_details

    title = video_id
    video_data = await get_video_details(video_id, cookie_file)
    if video_data is not None:
        meta = video_metadata_from_details(video_id, video_data)
        if meta.title:
            title = meta.title

    transcript_kwargs: dict[str, Any] = {"cookie_file": cookie_file}
    if video_data is not None:
        transcript_kwargs["video_data"] = video_data
    transcript = await fetch_transcript(video_id, languages, **transcript_kwargs)
    return title, transcript


def _write_transcript_artifact(
    transcript: VideoTranscript,
    title: str,
    video_id: str,
    output_dir: Path,
    export_format: str,
) -> Path:
    """Write the transcript artifact, suffixing the video ID on collisions."""
    import json

    from notewise.utils import sanitize_filename

    safe_title = sanitize_filename(title)
    stem = f"{safe_title}{TRANSCRIPT_COMMAND_FILE_STEM_SUFFIX}"
    extension = (
        TRANSCRIPT_JSON_OUTPUT_FORMAT
        if export_format == TRANSCRIPT_JSON_OUTPUT_FORMAT
        else TRANSCRIPT_TEXT_OUTPUT_FORMAT
    )
    export_path = output_dir / f"{stem}.{extension}"
    if export_path.exists():
        export_path = output_dir / f"{stem}-{video_id}.{extension}"
        collision_index = TRANSCRIPT_COLLISION_SUFFIX_START
        while export_path.exists():
            export_path = output_dir / (
                f"{stem}-{video_id}-{collision_index}.{extension}"
            )
            collision_index += 1

    if extension == TRANSCRIPT_JSON_OUTPUT_FORMAT:
        data = {
            "video_id": transcript.video_id,
            "language": transcript.language,
            "language_code": transcript.language_code,
            "is_generated": transcript.is_generated,
            "segments": [
                {
                    "text": seg.text,
                    "start": seg.start,
                    "duration": seg.duration,
                }
                for seg in transcript.segments
            ],
        }
        export_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    else:
        export_path.write_text(transcript.to_text(), encoding="utf-8")
    return export_path


@app.command()
def transcript(
    url: Annotated[
        str | None,
        typer.Argument(
            help="YouTube video URL to download the transcript for.",
            show_default=False,
        ),
    ] = None,
    export_format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help=(
                "Transcript file format. Supported: "
                "[green]txt[/green], [green]json[/green]."
            ),
            rich_help_panel="Common",
        ),
    ] = TRANSCRIPT_TEXT_OUTPUT_FORMAT,
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
            rich_help_panel="Common",
        ),
    ] = None,
    language: Annotated[
        list[str] | None,
        typer.Option(
            "--language",
            "-l",
            help=("Transcript languages, e.g. [green]en[/green], [green]hi[/green]."),
            rich_help_panel="Common",
        ),
    ] = None,
    cookie_file: Annotated[
        Path | None,
        typer.Option(
            "--cookie-file",
            "--cookies",
            "-c",
            help=("Netscape-format cookies .txt file for YouTube requests."),
            exists=False,
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
            rich_help_panel="Advanced",
        ),
    ] = None,
) -> None:
    """
    Download a single video's transcript without any AI generation.

    Requires no API key or model. For playlists and batch files, use
    `notewise process --export-transcript` instead.

    \b
    Examples:
      [cyan]notewise transcript "https://youtube.com/watch?v=VIDEO_ID"[/cyan]
      [cyan]notewise transcript "URL" --format json -o ./exports[/cyan]
    """
    console = _get_console()
    if url is None:
        from rich.prompt import Prompt

        url = Prompt.ask("YouTube video URL").strip()
        if not url:
            console.print("[red]A URL is required.[/red]")
            raise typer.Exit(code=1)

    try:
        from notewise.cli._formatters import print_single_failure
        from notewise.pipeline._artifacts import normalize_transcript_export_format

        normalized_format = normalize_transcript_export_format(export_format)

        if looks_like_batch_file_path(url):
            console.print(f"\n[red]{TRANSCRIPT_COMMAND_PLAYLIST_MESSAGE}[/red]\n")
            raise typer.Exit(code=1)

        _load_process_dependencies()
        settings = _get_config()
        selected_output = output or settings.default_output_dir
        selected_languages = language or settings.default_languages
        selected_cookie_file = (
            str(cookie_file)
            if cookie_file is not None
            else settings.youtube_cookie_file
        )

        parsed = parse_youtube_url(url)
        if parsed.url_type != "video" or not parsed.video_id:
            console.print(f"\n[red]{TRANSCRIPT_COMMAND_PLAYLIST_MESSAGE}[/red]\n")
            raise typer.Exit(code=1)
        selected_output.mkdir(parents=True, exist_ok=True)

        with console.status(TRANSCRIPT_STATUS_MESSAGE):
            title, fetched_transcript = asyncio.run(
                _download_video_transcript(
                    parsed.video_id,
                    selected_languages,
                    selected_cookie_file,
                )
            )

        written_path = _write_transcript_artifact(
            fetched_transcript,
            title,
            parsed.video_id,
            selected_output,
            normalized_format or TRANSCRIPT_TEXT_OUTPUT_FORMAT,
        )
        console.print(f"[green]{TRANSCRIPT_SAVED_PREFIX}[/green] {written_path}")

    except ConfigurationError as error:
        _print_configuration_error(error)
        raise typer.Exit(code=1) from None
    except typer.Exit:
        raise
    except (
        TranscriptUnavailableError,
        VideoUnavailableError,
        IPBlockError,
    ) as error:
        print_single_failure(
            console,
            "Transcript Error",
            format_user_error(error),
            item_label="Video",
        )
        raise typer.Exit(code=1) from None

    except (ValidationError, ValueError) as error:
        print_single_failure(console, "Input Error", str(error), item_label="URL")
        raise typer.Exit(code=1) from None

    except Exception:
        import structlog

        structlog.get_logger(__name__).exception("cli.transcript_error")
        print_single_failure(
            console,
            "Unexpected Error",
            "notewise could not download this transcript. "
            "Check the current log for details.",
            item_label="Status",
        )
        raise typer.Exit(code=1) from None


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """
    [bold cyan]notewise[/bold cyan]: AI-Powered Video Study Notes Generator.

    Convert YouTube content into structured Markdown notes.
    """
    if ctx.invoked_subcommand not in (None, "process"):
        from notewise.logging import configure_logging

        configure_logging()

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
            "-s",
            help="Show the current configuration without rewriting it.",
        ),
    ] = False,
) -> None:
    """
    Configure API keys and preferences interactively.

    Runs a wizard that saves your settings to the
    [bold]~/.notewise/config.db[/bold] database.
    """
    _load_setup_dependencies()
    if show:
        _get_config_or_exit()
        show_current_config(console=_get_console())
        return
    run_setup_wizard(force=force)


@config_app.callback(invoke_without_command=True)
def config_command(ctx: typer.Context) -> None:
    """Show, get, set, or unset persisted configuration values."""
    if ctx.invoked_subcommand is not None:
        return
    _load_setup_dependencies()
    _get_config_or_exit()
    show_current_config(console=_get_console())


@config_app.command("keys")
def config_keys() -> None:
    """List every config key that get/set/unset accept."""
    from notewise.config import allowed_config_keys

    console = _get_console()
    for key in sorted(allowed_config_keys()):
        console.print(key)


def _select_config_key(console: Any) -> str:
    """List every allowed config key and prompt for one by index."""
    from rich.prompt import Prompt
    from rich.table import Table

    from notewise.config import allowed_config_keys

    keys = sorted(allowed_config_keys())
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Key", style="cyan")
    for index, key in enumerate(keys, 1):
        table.add_row(str(index), key)
    console.print(table)

    choice = Prompt.ask("\nSelect config key number").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(keys):
        return keys[int(choice) - 1]
    console.print("[red]Invalid choice.[/red]")
    raise typer.Exit(code=1)


@config_app.command("edit")
def config_edit() -> None:
    """Interactively browse and edit config, grouped by category."""
    from notewise.ui.setup_wizard import run_config_editor

    _get_config_or_exit()
    run_config_editor(console=_get_console())


@config_app.command("get")
def config_get(
    key: Annotated[
        str | None,
        typer.Argument(
            help="Config key to read, e.g. DEFAULT_MODEL. "
            "Run `notewise config keys` for the full list. "
            "Omit to pick from a list."
        ),
    ] = None,
) -> None:
    """Print one persisted configuration value."""
    from notewise.ui.setup_wizard import load_config

    console = _get_console()
    if key is None:
        key = _select_config_key(console)
    normalized_key = key.strip().upper()
    try:
        current_config = load_config()
    except ConfigurationError as error:
        _print_configuration_error(error)
        raise typer.Exit(code=1) from None

    if normalized_key not in current_config:
        console.print(f"[yellow]{normalized_key} is not set.[/yellow]")
        raise typer.Exit(code=1)

    value = current_config[normalized_key]
    if _is_sensitive_key(normalized_key):
        from notewise.utils import mask_secret

        value = mask_secret(value, suffix=" (set)")
    console.print(value)


@config_app.command("set")
def config_set(
    key: Annotated[
        str | None,
        typer.Argument(
            help="Config key to write, e.g. DEFAULT_MODEL. "
            "Run `notewise config keys` for the full list. "
            "Omit to pick from a list."
        ),
    ] = None,
    value: Annotated[
        str | None,
        typer.Argument(
            help="Value to store for this key. Omit for a sensitive key "
            "(e.g. an API key) to be prompted with hidden input instead of "
            "leaving it in shell history."
        ),
    ] = None,
) -> None:
    """Set one persisted configuration value."""
    import sqlite3

    from pydantic import ValidationError as PydanticValidationError

    from notewise.config import allowed_config_keys, validate_candidate_config
    from notewise.errors import CustomEndpointError
    from notewise.ui.setup_wizard import load_config, save_config

    console = _get_console()
    if key is None:
        key = _select_config_key(console)
    normalized_key = key.strip().upper()
    if normalized_key not in allowed_config_keys():
        _exit_inference_error(
            f"{normalized_key!r} is not a recognized config key. "
            "Run `notewise config keys` to see all supported keys."
        )

    if value is None:
        from rich.prompt import Prompt

        value = Prompt.ask(
            f"Enter value for {normalized_key}",
            password=_is_sensitive_key(normalized_key),
        )

    try:
        candidate = {**load_config(suppress_errors=True), normalized_key: value}
        validate_candidate_config(candidate)
    except PydanticValidationError as error:
        _print_configuration_error(
            ConfigurationError(_format_config_validation_error(error))
        )
        raise typer.Exit(code=1) from None

    try:
        save_config({normalized_key: value}, console=console)
    except (CustomEndpointError, ConfigurationError, OSError, sqlite3.Error) as error:
        _exit_inference_error(str(error))
    _reload_and_validate_config()


@config_app.command("unset")
def config_unset(
    key: Annotated[
        str | None,
        typer.Argument(
            help="Config key to remove, e.g. TEMPERATURE. "
            "Run `notewise config keys` for the full list. "
            "Omit to pick from a list."
        ),
    ] = None,
) -> None:
    """Remove one persisted configuration value."""
    from notewise.config import get_config_db_path
    from notewise.storage import config_store

    console = _get_console()
    if key is None:
        key = _select_config_key(console)
    normalized_key = key.strip().upper()
    db_path = get_config_db_path()

    # A single atomic DELETE against the owning table, rather than a
    # load-mutate-replace round trip, so this can't clobber a concurrent
    # `config set`/`inference add` that commits in between.
    if not config_store.remove_config_key(db_path, normalized_key):
        console.print(f"[yellow]{normalized_key} is not set.[/yellow]")
        raise typer.Exit(code=1)

    _reload_and_validate_config()
    console.print(f"[green]Removed {normalized_key} from configuration.[/green]")


@app.command()
def config_path() -> None:
    """Show the path to the configuration database."""
    console = _get_console()
    config_file = _get_config_file_path()

    if check_config_exists():
        console.print(f"\n[cyan]Configuration database:[/cyan] {config_file}")
        console.print(
            "\n[dim]To view: Run[/dim] [cyan]notewise config[/cyan]\n"
            "[dim]To change one value: Run[/dim] "
            "[cyan]notewise config set KEY VALUE[/cyan]\n"
            "[dim]To edit in your editor: Run[/dim] [cyan]notewise edit-config[/cyan]"
        )
        console.print(
            "[dim]To reconfigure: Run[/dim] [cyan]notewise setup --force[/cyan]\n"
        )
    else:
        console.print("\n[yellow]No configuration found.[/yellow]")
        console.print(
            "[dim]Run[/dim] [cyan]notewise setup[/cyan] [dim]to create one.[/dim]\n"
        )


@app.command("help")
def help_command(ctx: typer.Context) -> None:
    """Show this message and exit."""
    if ctx.parent is not None:
        typer.echo(ctx.parent.get_help())
    raise typer.Exit()


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
            "-m",
            help="Filter aggregate stats to a single model.",
            rich_help_panel="Filters",
        ),
    ] = None,
    since: Annotated[
        str | None,
        typer.Option(
            "--since",
            "-s",
            help="Filter to the last N days. Examples: 7 or 30d.",
            rich_help_panel="Filters",
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
            "-n",
            min=1,
            help="Maximum number of recent videos to show.",
            rich_help_panel="Display",
        ),
    ] = DEFAULT_HISTORY_LIMIT,
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
        _get_config_or_exit()

        from notewise.cli._admin import render_runtime_info

        render_runtime_info(console)
        return

    from notewise.cli._formatters import print_single_failure
    from notewise.errors import PlaylistError, VideoUnavailableError

    try:
        _load_process_dependencies()
        settings = _get_config()
        from notewise.cli._admin import render_source_info

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
    except ConfigurationError as error:
        _print_configuration_error(error)
        raise typer.Exit(code=1) from None
    except typer.Exit:
        raise
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
    _get_config_or_exit()

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


def _exit_inference_error(message: str) -> NoReturn:
    """Print an inference command error without exposing endpoint credentials."""
    _get_console().print(f"[red]{message}[/red]")
    raise typer.Exit(code=1)


@inference_app.command("list")
def inference_list() -> None:
    """List saved OpenAI-compatible endpoints without their credentials."""
    import sqlite3

    from notewise.config import get_config_db_path
    from notewise.storage import config_store

    try:
        profiles = config_store.list_custom_endpoints(get_config_db_path())
    except sqlite3.Error as error:
        _exit_inference_error(str(error))

    if not profiles:
        _get_console().print("No saved inference endpoints.")
        return

    from rich.table import Table

    table = Table(title="Saved inference endpoints")
    table.add_column("Name")
    table.add_column("Base URL")
    for profile in profiles:
        table.add_row(profile.name, profile.base_url)
    _get_console().print(table)


@inference_app.command("add")
def inference_add(
    name: Annotated[
        str | None, typer.Argument(help="Name for this saved endpoint.")
    ] = None,
    base_url: Annotated[
        str | None,
        typer.Option("--base-url", "-b", help="OpenAI-compatible endpoint URL."),
    ] = None,
    api_key: Annotated[
        str | None, typer.Option("--api-key", "-k", help="API key for this endpoint.")
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", "-m", help="Model ID returned by this endpoint."),
    ] = None,
) -> None:
    """Discover, verify, and save an OpenAI-compatible endpoint.

    Any option left out is prompted for interactively.
    """
    import sqlite3

    from rich.prompt import Prompt

    from notewise.config import get_config_db_path
    from notewise.errors import ConfigurationError, CustomEndpointError
    from notewise.llm.custom_endpoint import (
        CustomEndpointProfile,
        discover_and_verify_model,
        normalize_custom_model_prefix,
        normalize_openai_base_url,
    )
    from notewise.storage import config_store
    from notewise.ui.setup_wizard import _select_or_enter_model

    console = _get_console()
    if name is None:
        name = Prompt.ask("Name for this endpoint").strip()
    if base_url is None:
        base_url = Prompt.ask("Base URL").strip()
    if api_key is None:
        api_key = Prompt.ask("API key", password=True).strip()
    if not api_key.strip():
        raise typer.BadParameter(
            "Custom endpoint API key is required.", param_hint="--api-key"
        )

    try:
        normalized_name = normalize_custom_model_prefix(name)
        normalized_base_url = normalize_openai_base_url(base_url)
        if model is None:
            model = _select_or_enter_model(console, normalized_base_url, api_key)
        pricing = discover_and_verify_model(
            normalized_base_url, api_key, model, endpoint_name=normalized_name
        )
        profile = CustomEndpointProfile(
            name=normalized_name,
            base_url=normalized_base_url,
            api_key=api_key,
            model_pricing=pricing,
        )
        config_store.upsert_custom_endpoint(get_config_db_path(), profile)
    except (ConfigurationError, CustomEndpointError, OSError, sqlite3.Error) as error:
        _exit_inference_error(str(error))

    console.print(
        f"[green]Saved inference endpoint {profile.name!r} "
        f"for model {profile.name}/{model}.[/green]"
    )


@inference_app.command("update")
def inference_update(
    name: Annotated[
        str | None, typer.Argument(help="Name of the saved endpoint.")
    ] = None,
    base_url: Annotated[
        str | None,
        typer.Option(
            "--base-url",
            "-b",
            help="Replacement OpenAI-compatible endpoint URL.",
        ),
    ] = None,
    api_key: Annotated[
        str | None,
        typer.Option("--api-key", "-k", help="Replacement API key for this endpoint."),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", "-m", help="Model ID returned by the endpoint."),
    ] = None,
) -> None:
    """Discover, verify, and replace one saved inference endpoint.

    Any option left out is prompted for interactively (blank keeps the
    current value for base URL and API key).
    """
    if name is not None and base_url is None and api_key is None:
        raise typer.BadParameter(
            "Provide --base-url, --api-key, or both when updating an endpoint."
        )
    if api_key is not None and not api_key.strip():
        raise typer.BadParameter(
            "Custom endpoint API key is required.", param_hint="--api-key"
        )

    import sqlite3

    from rich.prompt import Prompt

    from notewise.config import get_config_db_path
    from notewise.errors import ConfigurationError, CustomEndpointError
    from notewise.llm.custom_endpoint import (
        CustomEndpointProfile,
        default_model_endpoint_match,
        discover_and_verify_model,
        normalize_custom_model_prefix,
        normalize_openai_base_url,
    )
    from notewise.storage import config_store
    from notewise.ui.setup_wizard import (
        _select_endpoint_by_index,
        _select_or_enter_model,
        load_config,
    )

    console = _get_console()
    try:
        db_path = get_config_db_path()
        profiles = config_store.list_custom_endpoints(db_path)
        if name is None:
            if not profiles:
                _exit_inference_error("No saved inference endpoints to update.")
            existing_profile = _select_endpoint_by_index(profiles, console, "update")
            if existing_profile is None:
                raise typer.Exit(code=1)
            normalized_name = existing_profile.name
            if base_url is None:
                base_url = Prompt.ask(
                    f"Base URL [{existing_profile.base_url}]", default=""
                ).strip()
            if api_key is None:
                api_key = Prompt.ask(
                    "API key (blank to keep current)", password=True, default=""
                ).strip()
        else:
            normalized_name = normalize_custom_model_prefix(name)
            existing_profile = next(
                (profile for profile in profiles if profile.name == normalized_name),
                None,
            )
            if existing_profile is None:
                _exit_inference_error(
                    f"No saved inference endpoint is named {normalized_name!r}."
                )

        selected_base_url = (
            normalize_openai_base_url(base_url)
            if base_url
            else existing_profile.base_url
        )
        if (
            name is not None
            and base_url is not None
            and api_key is None
            and selected_base_url != existing_profile.base_url
        ):
            _exit_inference_error(
                "--api-key is required when --base-url changes a saved endpoint."
            )
        selected_api_key = api_key or existing_profile.api_key

        current_config = load_config()
        selected_model = model
        if selected_model is None:
            selected_model = default_model_endpoint_match(
                current_config, normalized_name
            )
        if selected_model is None:
            if name is None:
                selected_model = _select_or_enter_model(
                    console, selected_base_url, selected_api_key
                )
            else:
                _exit_inference_error(
                    "--model is required unless DEFAULT_MODEL uses this endpoint."
                )

        profile = CustomEndpointProfile(
            name=normalized_name,
            base_url=selected_base_url,
            api_key=selected_api_key,
        )
        pricing = discover_and_verify_model(
            profile.base_url,
            profile.api_key,
            selected_model,
            endpoint_name=profile.name,
        )
        from dataclasses import replace

        profile = replace(profile, model_pricing=pricing)
        config_store.upsert_custom_endpoint(db_path, profile)
    except (ConfigurationError, CustomEndpointError, OSError, sqlite3.Error) as error:
        _exit_inference_error(str(error))

    console.print(
        f"[green]Updated inference endpoint {profile.name!r} "
        f"for model {profile.name}/{selected_model}.[/green]"
    )


@inference_app.command("delete")
def inference_delete(
    name: Annotated[
        str | None, typer.Argument(help="Name of the saved endpoint.")
    ] = None,
) -> None:
    """Remove a saved inference endpoint that is not the configured default."""
    import sqlite3

    from notewise.config import get_config_db_path
    from notewise.errors import ConfigurationError, CustomEndpointError
    from notewise.llm.custom_endpoint import (
        default_model_endpoint_match,
        normalize_custom_model_prefix,
    )
    from notewise.storage import config_store
    from notewise.ui.setup_wizard import _select_endpoint_by_index, load_config

    console = _get_console()
    try:
        db_path = get_config_db_path()
        profiles = config_store.list_custom_endpoints(db_path)
        if name is None:
            if not profiles:
                _exit_inference_error("No saved inference endpoints to delete.")
            target_profile = _select_endpoint_by_index(profiles, console, "delete")
            if target_profile is None:
                raise typer.Exit(code=1)
            normalized_name = target_profile.name
        else:
            normalized_name = normalize_custom_model_prefix(name)
            if not any(profile.name == normalized_name for profile in profiles):
                _exit_inference_error(
                    f"No saved inference endpoint is named {normalized_name!r}."
                )

        current_config = load_config()
        if default_model_endpoint_match(current_config, normalized_name) is not None:
            _exit_inference_error(
                f"Cannot delete {normalized_name!r} while it is used by DEFAULT_MODEL."
            )

        config_store.delete_custom_endpoint(db_path, normalized_name)
    except (ConfigurationError, CustomEndpointError, OSError, sqlite3.Error) as error:
        _exit_inference_error(str(error))

    console.print(f"[green]Deleted inference endpoint {normalized_name!r}.[/green]")


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
            "-i",
            help="Show cache database metadata and entry counts.",
            rich_help_panel="Actions",
        ),
    ] = False,
    show: Annotated[
        str | None,
        typer.Option(
            "--show",
            "-s",
            metavar="VIDEO_ID",
            help="Show cached metadata for a specific video.",
            rich_help_panel="Actions",
        ),
    ] = None,
    clear: Annotated[
        bool,
        typer.Option(
            "--clear",
            "-c",
            help="Delete the local cache database.",
            rich_help_panel="Actions",
        ),
    ] = False,
    prune: Annotated[
        int | None,
        typer.Option(
            "--prune",
            "-p",
            min=0,
            metavar="DAYS",
            help="Prune stale cache entries older than this many days.",
            rich_help_panel="Actions",
        ),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Skip confirmation when used with --clear.",
            rich_help_panel="Safety",
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


def _select_cached_video_id(console: Any) -> str:
    """List recently cached videos and prompt for one by index."""
    from rich.prompt import Prompt
    from rich.table import Table

    from notewise.cli._admin import _load_repository

    repository, _db_path = _load_repository()
    if repository is None:
        console.print("[yellow]No cache database found yet.[/yellow]")
        raise typer.Exit(code=1)

    rows = repository.get_recent_videos(limit=DEFAULT_HISTORY_LIMIT)
    if not rows:
        console.print("[yellow]No cached videos found.[/yellow]")
        raise typer.Exit(code=1)

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="cyan")
    table.add_column("Video ID", style="dim")
    for index, row in enumerate(rows, 1):
        table.add_row(str(index), row.title, row.id)
    console.print(table)

    choice = Prompt.ask("\nSelect video # to inspect").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(rows):
        return rows[int(choice) - 1].id
    console.print("[red]Invalid choice.[/red]")
    raise typer.Exit(code=1)


@cache_app.command("show")
def cache_show(
    video_id: Annotated[
        str | None,
        typer.Argument(
            help="Video ID to inspect in the cache. Omit to pick from a list."
        ),
    ] = None,
) -> None:
    """Show cached metadata for a specific video."""
    from notewise.cli._admin import render_cache_entry

    console = _get_console()
    if video_id is None:
        video_id = _select_cached_video_id(console)
    render_cache_entry(console, video_id=video_id)


@cache_app.command("clear")
def cache_clear(
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
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
            "-o",
            min=0,
            help="Remove cache entries older than this many days.",
        ),
    ] = DEFAULT_CACHE_PRUNE_OLDER_THAN_DAYS,
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
            "-t",
            min=1,
            help="Tail the latest session log with the last N lines.",
            rich_help_panel="Actions",
        ),
    ] = None,
    open: Annotated[
        bool,
        typer.Option(
            "--open",
            "-o",
            help="Open the log directory in the system file manager.",
            rich_help_panel="Actions",
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
            "-a",
            help="Remove all inactive log files instead of only older ones.",
            rich_help_panel="Scope",
        ),
    ] = False,
    older_than: Annotated[
        int,
        typer.Option(
            "--older-than",
            "-o",
            min=0,
            help="Remove logs older than this many days.",
            rich_help_panel="Scope",
        ),
    ] = DEFAULT_LOGS_CLEAN_OLDER_THAN_DAYS,
) -> None:
    """Prune old log files."""
    from notewise.cli._admin import clean_logs

    clean_logs(_get_console(), all_logs=all_logs, older_than_days=older_than)


app.add_typer(cache_app, name="cache")
app.add_typer(logs_app, name="logs")
app.add_typer(auth_app, name="auth")
app.add_typer(inference_app, name="inference")
app.add_typer(config_app, name="config")


if __name__ == "__main__":
    app()
