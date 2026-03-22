"""Lightweight helpers for non-pipeline CLI commands."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from collections.abc import Callable
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from yt_study._constants import CONFIG_FILENAME
from yt_study.config import get_cache_db_path, get_state_dir
from yt_study.config import settings as app_settings
from yt_study.logging import get_log_dir, get_session_log_path, prune_log_files


if TYPE_CHECKING:
    from rich.console import Console


def _mask_secret(value: str | None) -> str:
    if not value:
        return "(not set)"
    if len(value) <= 8:
        return "***"
    return f"{value[:6]}...{value[-4:]}"


def _human_size(num_bytes: int) -> str:
    size = float(max(num_bytes, 0))
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return "0 B"


def _format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes or hours:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def _coerce_int(value: object | None, *, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, (str, bytes, bytearray)):
        try:
            return int(value)
        except ValueError:
            return default
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "Never"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    local_value = value.astimezone()
    return local_value.strftime("%Y-%m-%d %H:%M:%S %Z")


def _format_age(value: datetime | None) -> str:
    if value is None:
        return "Never"
    now = datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    delta = now - value.astimezone(timezone.utc)
    days = max(delta.days, 0)
    if days == 0:
        return "today"
    if days == 1:
        return "1 day ago"
    return f"{days} days ago"


def _parse_since_days(value: str | None) -> int | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized.endswith("d"):
        normalized = normalized[:-1]
    days = int(normalized)
    if days < 0:
        raise ValueError("since must be zero or a positive integer day count")
    return days


def _open_with_system_app(path: Path) -> None:
    if os.name == "nt":
        startfile = getattr(os, "startfile", None)
        if startfile is not None:
            startfile(path)
            return
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=True)
        return
    subprocess.run(["xdg-open", str(path)], check=True)


def _open_in_editor(path: Path) -> None:
    editor = os.environ.get("EDITOR")
    if editor:
        subprocess.run([editor, str(path)], check=True)
        return
    if os.name == "nt":
        subprocess.run(["notepad", str(path)], check=True)
        return
    if sys.platform == "darwin":
        subprocess.run(["open", "-t", str(path)], check=True)
        return
    subprocess.run(["nano", str(path)], check=True)


def _load_repository() -> tuple[Any | None, Path]:
    db_path = get_cache_db_path()
    if not db_path.exists():
        return None, db_path
    from yt_study.storage.repository import DatabaseRepository

    return DatabaseRepository.get_instance(db_path), db_path


def render_stats(console: Console, *, since: str | None, model: str | None) -> None:
    from rich.table import Table

    days = _parse_since_days(since)
    repository, _db_path = _load_repository()
    if repository is None:
        console.print("[yellow]No cache database found yet.[/yellow]")
        return

    stats = repository.get_stats(since_days=days, model=model)
    summary = Table(title="Processing Statistics", border_style="cyan")
    summary.add_column("Metric", style="cyan")
    summary.add_column("Value", justify="right")
    summary.add_row("Videos processed", f"{stats.total_videos_processed:,}")
    summary.add_row("Total runs", f"{stats.total_runs:,}")
    summary.add_row("Total tokens", f"{stats.total_tokens_used:,}")
    summary.add_row("Prompt tokens", f"{stats.total_prompt_tokens:,}")
    summary.add_row("Completion tokens", f"{stats.total_completion_tokens:,}")
    summary.add_row("Total cost (USD)", f"${stats.total_cost_usd:.4f}")
    summary.add_row(
        "Transcript time",
        _format_duration(stats.total_transcript_seconds),
    )
    summary.add_row(
        "Generation time",
        _format_duration(stats.total_generation_seconds),
    )
    console.print(summary)

    if not stats.models:
        console.print("[dim]No model-specific runs found for that filter.[/dim]")
        return

    breakdown = Table(title="Model Breakdown", border_style="green")
    breakdown.add_column("Model", style="green")
    breakdown.add_column("Videos", justify="right")
    breakdown.add_column("Runs", justify="right")
    breakdown.add_column("Tokens", justify="right")
    breakdown.add_column("Cost", justify="right")
    for row in stats.models:
        breakdown.add_row(
            row.model,
            f"{row.videos_processed:,}",
            f"{row.run_count:,}",
            f"{row.total_tokens_used:,}",
            f"${row.total_cost_usd:.4f}",
        )
    console.print(breakdown)


def render_history(console: Console, *, limit: int) -> None:
    from rich.table import Table

    repository, _db_path = _load_repository()
    if repository is None:
        console.print("[yellow]No processed video history found yet.[/yellow]")
        return

    rows = repository.get_recent_videos(limit=max(1, limit))
    if not rows:
        console.print("[yellow]No processed video history found yet.[/yellow]")
        return

    table = Table(title="Recent Videos", border_style="cyan")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Title", style="cyan")
    table.add_column("Model", style="green")
    table.add_column("Cost", justify="right")
    table.add_column("Last Run", style="dim")
    for index, row in enumerate(rows, start=1):
        table.add_row(
            str(index),
            row.title,
            row.model,
            f"${row.cost_usd:.4f}",
            _format_datetime(row.last_run_at),
        )
    console.print(table)


def render_runtime_info(console: Console) -> None:
    from rich.panel import Panel
    from rich.table import Table

    settings = app_settings
    config_path = get_state_dir() / CONFIG_FILENAME
    db_path = get_cache_db_path()

    table = Table(box=None, show_header=False, padding=(0, 1))
    table.add_column("Item", style="bold cyan", no_wrap=True)
    table.add_column("Value")
    table.add_row("Config", str(config_path))
    table.add_row("Cache DB", str(db_path))
    table.add_row("Output", str(settings.default_output_dir))
    table.add_row("Model", settings.default_model)
    table.add_row("Languages", ", ".join(settings.default_languages))
    table.add_row("Video workers", str(settings.max_concurrent_videos))
    table.add_row("Chapter workers", str(settings.max_concurrent_chapters))
    table.add_row(
        "YouTube requests/min",
        str(settings.youtube_requests_per_minute),
    )
    table.add_row(
        "Cookie file",
        settings.youtube_cookie_file or "(not set)",
    )
    console.print(Panel(table, title="yt-study Info", border_style="cyan"))


async def render_source_info(
    console: Console,
    *,
    url: str,
    parse_youtube_url: Callable[[str], Any],
    get_video_details: Callable[..., Any],
    get_source_metadata: Callable[..., Any],
    get_playlist_info: Callable[..., Any],
    extract_playlist_videos: Callable[..., Any],
    cookie_file: str | None,
) -> None:
    from rich.panel import Panel
    from rich.table import Table

    parsed = parse_youtube_url(url)
    repository, _db_path = _load_repository()

    if parsed.url_type == "playlist" and parsed.playlist_id is not None:
        source_url = (
            url
            if url.startswith(("http://", "https://"))
            else f"https://www.youtube.com/playlist?list={parsed.playlist_id}"
        )
        raw_metadata = await get_source_metadata(source_url, cookie_file)
        data = raw_metadata.get("data") or {}
        title = str(raw_metadata.get("title") or data.get("title") or "").strip()
        count = _coerce_int(data.get("playlist_count"), default=-1)
        if not title or count < 0:
            title, fetched_count = await get_playlist_info(
                parsed.playlist_id,
                cookie_file,
            )
            if not title:
                title = f"playlist_{parsed.playlist_id}"
            count = fetched_count
        playlist_video_ids = await extract_playlist_videos(
            parsed.playlist_id,
            cookie_file,
        )
        video_ids = list(dict.fromkeys(playlist_video_ids))
        cached_count = (
            sum(
                1
                for video_id in video_ids
                if repository and repository.has_video(video_id)
            )
            if repository is not None
            else 0
        )

        table = Table(box=None, show_header=False, padding=(0, 1))
        table.add_column("Item", style="bold cyan", no_wrap=True)
        table.add_column("Value")
        table.add_row("Type", "Playlist")
        table.add_row("Playlist ID", parsed.playlist_id)
        table.add_row("Title", title or f"playlist_{parsed.playlist_id}")
        uploader = str(data.get("uploader") or data.get("channel") or "").strip()
        if uploader:
            table.add_row("Channel", uploader)
        table.add_row("Source", source_url)
        table.add_row("Videos", str(count if count >= 0 else len(video_ids)))
        table.add_row("Resolvable videos", str(len(video_ids)))
        table.add_row("Cached", f"{cached_count}/{len(video_ids)} processed")
        console.print(Panel(table, title="Playlist Info", border_style="cyan"))
        return

    if parsed.video_id is None:
        raise ValueError("The URL does not include a resolvable YouTube video id.")

    source_url = (
        url
        if url.startswith(("http://", "https://"))
        else f"https://www.youtube.com/watch?v={parsed.video_id}"
    )
    video_data = await get_video_details(parsed.video_id, cookie_file)
    cached = repository.get_video(parsed.video_id) if repository is not None else None

    table = Table(box=None, show_header=False, padding=(0, 1))
    table.add_column("Item", style="bold cyan", no_wrap=True)
    table.add_column("Value")
    table.add_row("Type", "Video")
    table.add_row("Video ID", parsed.video_id)
    title = str(video_data.get("title") or parsed.video_id).strip()
    table.add_row("Title", title or parsed.video_id)
    uploader = str(
        video_data.get("uploader") or video_data.get("channel") or ""
    ).strip()
    if uploader:
        table.add_row("Channel", uploader)
    table.add_row("Source", source_url)
    duration = _coerce_int(video_data.get("duration"))
    table.add_row("Duration", _format_duration(duration))
    chapters = video_data.get("chapters") or []
    table.add_row("Chapters", str(len(chapters)))
    subtitles = sorted((video_data.get("subtitles") or {}).keys())
    automatic_captions = sorted((video_data.get("automatic_captions") or {}).keys())
    if subtitles:
        table.add_row("Subtitles", ", ".join(str(item) for item in subtitles))
    if automatic_captions:
        table.add_row(
            "Auto captions",
            ", ".join(str(item) for item in automatic_captions),
        )
    view_count = _coerce_int(video_data.get("view_count"), default=-1)
    if view_count >= 0:
        table.add_row("Views", f"{view_count:,}")
    table.add_row(
        "Cached",
        _format_datetime(cached.cached_at) if cached is not None else "No",
    )
    console.print(Panel(table, title="Video Info", border_style="cyan"))


def render_doctor(console: Console) -> None:
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    settings = app_settings
    state_dir = get_state_dir()
    config_path = state_dir / CONFIG_FILENAME
    db_path = get_cache_db_path()
    log_dir = get_log_dir(state_dir)

    required_key_name = settings.get_api_key_name_for_model(settings.default_model)
    required_key_value = (
        os.environ.get(required_key_name) if required_key_name is not None else None
    )

    output_dir = Path(settings.default_output_dir).expanduser()
    output_writable = True
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        probe = output_dir / ".yt-study-write-check"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        output_writable = False

    db_status = "Not created yet"
    db_ok = True
    if db_path.exists():
        try:
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute("PRAGMA quick_check")
            db_status = f"{db_path} ({_human_size(db_path.stat().st_size)})"
        except sqlite3.Error as error:
            db_ok = False
            db_status = f"{db_path} ({error})"
    else:
        db_status = f"{db_path} (not created yet)"

    log_files = (
        sorted(
            log_dir.glob("*.log"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if log_dir.exists()
        else []
    )
    latest_log = get_session_log_path() or (log_files[0] if log_files else None)

    rows = Table(box=None, show_header=False, padding=(0, 1))
    rows.add_column("Status", no_wrap=True)
    rows.add_column("Check", style="bold cyan", no_wrap=True)
    rows.add_column("Details")
    rows.add_row(
        "OK" if config_path.exists() else "WARN",
        "Config file",
        str(config_path),
    )
    rows.add_row(
        "OK" if required_key_value else "FAIL",
        "API key",
        f"{required_key_name or 'N/A'} {'set' if required_key_value else 'not set'}",
    )
    rows.add_row(
        "OK" if output_writable else "FAIL",
        "Output dir",
        f"{output_dir} ({'writable' if output_writable else 'not writable'})",
    )
    rows.add_row("OK" if db_ok else "FAIL", "Cache DB", db_status)
    rows.add_row(
        "OK",
        "Log dir",
        f"{log_dir} ({len(log_files)} files)",
    )
    if latest_log is not None:
        rows.add_row("OK", "Latest log", str(latest_log))

    overall_ready = (
        config_path.exists()
        and (required_key_name is None or bool(required_key_value))
        and output_writable
        and db_ok
    )
    footer = Text(
        "Ready" if overall_ready else "Needs attention",
        style="bold green" if overall_ready else "bold yellow",
    )
    console.print(
        Panel(
            rows,
            title="yt-study Doctor",
            subtitle=footer,
            border_style="cyan",
        )
    )


def render_cache_info(console: Console) -> None:
    from rich.panel import Panel
    from rich.table import Table

    repository, db_path = _load_repository()
    if repository is None:
        console.print(f"[yellow]No cache database found at {db_path}.[/yellow]")
        return

    summary = repository.get_cache_summary()
    size = db_path.stat().st_size if db_path.exists() else 0
    table = Table(box=None, show_header=False, padding=(0, 1))
    table.add_column("Item", style="bold cyan", no_wrap=True)
    table.add_column("Value")
    table.add_row("Location", str(db_path))
    table.add_row("Size", _human_size(size))
    table.add_row("Videos", f"{summary.total_videos:,}")
    table.add_row("Transcripts", f"{summary.total_transcripts:,}")
    table.add_row("Runs", f"{summary.total_runs:,}")
    table.add_row("Exports", f"{summary.total_exports:,}")
    table.add_row("Oldest", _format_datetime(summary.oldest_cached_at))
    table.add_row("Newest", _format_datetime(summary.newest_cached_at))
    console.print(Panel(table, title="Cache Info", border_style="cyan"))


def render_cache_entry(console: Console, *, video_id: str) -> None:
    from rich.panel import Panel
    from rich.table import Table

    repository, db_path = _load_repository()
    if repository is None:
        console.print(f"[yellow]No cache database found at {db_path}.[/yellow]")
        return

    video = repository.get_video(video_id)
    transcript = repository.get_transcript(video_id)
    run_stats = repository.get_run_stats(video_id)
    exports = repository.get_export_records(video_id)
    if video is None:
        console.print(f"[yellow]No cached record found for {video_id}.[/yellow]")
        return

    latest_run = run_stats[-1] if run_stats else None
    table = Table(box=None, show_header=False, padding=(0, 1))
    table.add_column("Item", style="bold cyan", no_wrap=True)
    table.add_column("Value")
    table.add_row("Video ID", video.id)
    table.add_row("Title", video.title)
    table.add_row("Duration", _format_duration(video.duration))
    table.add_row("Cached at", _format_datetime(video.cached_at))
    table.add_row("Transcript", "Yes" if transcript is not None else "No")
    table.add_row("Run count", str(len(run_stats)))
    table.add_row("Exports", str(len(exports)))
    if latest_run is not None:
        table.add_row("Latest model", latest_run.model)
        table.add_row("Latest cost", f"${latest_run.cost_usd:.4f}")
    console.print(Panel(table, title="Cached Video", border_style="cyan"))


def clear_cache(console: Console) -> None:
    db_path = get_cache_db_path()
    if not db_path.exists():
        console.print(f"[yellow]No cache database found at {db_path}.[/yellow]")
        return

    from yt_study.storage.repository import DatabaseRepository

    DatabaseRepository.close_instance(db_path)
    removed = []
    candidates = (
        db_path,
        db_path.with_suffix(f"{db_path.suffix}-shm"),
        db_path.with_suffix(f"{db_path.suffix}-wal"),
    )
    for candidate in candidates:
        if candidate.exists():
            candidate.unlink()
            removed.append(candidate)
    console.print(f"[green]Removed {len(removed)} cache file(s).[/green]")


def prune_cache(console: Console, *, older_than_days: int) -> None:
    repository, db_path = _load_repository()
    if repository is None:
        console.print(f"[yellow]No cache database found at {db_path}.[/yellow]")
        return
    deleted = repository.prune_old_entries(older_than_days=older_than_days)
    console.print(
        "[green]Pruned "
        f"{deleted} cache entr{'y' if deleted == 1 else 'ies'} "
        f"older than {older_than_days} day(s).[/green]"
    )


def render_logs(
    console: Console,
    *,
    tail: int | None = None,
    open_dir: bool = False,
) -> None:
    from rich.panel import Panel
    from rich.table import Table

    log_dir = get_log_dir(get_state_dir())
    log_files = (
        sorted(
            log_dir.glob("*.log"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if log_dir.exists()
        else []
    )

    if open_dir:
        _open_with_system_app(log_dir)
        console.print(f"[green]Opened {log_dir}.[/green]")

    if tail is not None:
        latest = log_files[0] if log_files else None
        if latest is None:
            console.print("[yellow]No log files found.[/yellow]")
            return
        lines = latest.read_text(encoding="utf-8", errors="replace").splitlines()
        console.print(
            Panel(
                "\n".join(lines[-max(1, tail) :]) or "(empty log)",
                title=f"Latest Log Tail • {latest.name}",
                border_style="cyan",
            )
        )
        return

    total_size = sum(path.stat().st_size for path in log_files)
    table = Table(title="Session Logs", border_style="cyan")
    table.add_column("File", style="cyan")
    table.add_column("Size", justify="right")
    table.add_column("Modified", style="dim")
    for path in log_files[:5]:
        table.add_row(
            path.name,
            _human_size(path.stat().st_size),
            datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        )
    console.print(f"[dim]Directory:[/dim] {log_dir}")
    console.print(
        f"[dim]Total:[/dim] {len(log_files)} file(s) • {_human_size(total_size)}"
    )
    if log_files:
        console.print(table)
    else:
        console.print("[yellow]No log files found.[/yellow]")


def clean_logs(console: Console, *, all_logs: bool, older_than_days: int) -> None:
    log_dir = get_log_dir(get_state_dir())
    if not log_dir.exists():
        console.print(f"[yellow]No log directory found at {log_dir}.[/yellow]")
        return

    if not all_logs:
        deleted = prune_log_files(
            older_than_days=older_than_days,
            state_dir=get_state_dir(),
        )
        console.print(
            "[green]Removed "
            f"{deleted} log file(s) older than {older_than_days} day(s).[/green]"
        )
        return

    active_log = get_session_log_path()
    deleted = 0
    for path in log_dir.glob("*.log"):
        if active_log is not None and path.resolve() == active_log.resolve():
            continue
        path.unlink()
        deleted += 1
    console.print(f"[green]Removed {deleted} log file(s).[/green]")


def edit_config(console: Console) -> None:
    config_path = get_state_dir() / CONFIG_FILENAME
    if not config_path.exists():
        console.print(
            f"[yellow]No configuration found yet at {config_path}.[/yellow]\n"
            "[dim]Run `yt-study setup` first, then use this command to edit it.[/dim]"
        )
        return
    _open_in_editor(config_path)
    console.print(f"[green]Opened {config_path}.[/green]")
