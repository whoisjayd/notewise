"""Unit tests for administrative CLI helpers."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from rich.console import Console

from notewise.cli import _admin as admin


def _console() -> Console:
    return Console(record=True, width=120)


def _text(console: Console) -> str:
    return console.export_text()


def test_helper_formatting_functions() -> None:
    now = datetime.now(UTC)
    naive_now = datetime(2026, 3, 22, 12, 0, 0)

    assert admin._human_size(0) == "0 B"
    assert admin._human_size(2048) == "2.0 KB"
    assert admin._format_duration(3661) == "1h 1m 1s"
    assert admin._format_datetime(None) == "Never"
    assert admin._format_datetime(now)
    assert admin._format_datetime(naive_now)
    assert admin._format_age(None) == "Never"
    assert admin._format_age(now) == "today"
    assert admin._format_age(now - timedelta(days=1)) == "1 day ago"
    assert admin._format_age(naive_now - timedelta(days=3)).endswith("days ago")
    assert admin._parse_since_days("30d") == 30
    with pytest.raises(ValueError, match="positive integer"):
        admin._parse_since_days("-1")


def test_open_with_system_app_uses_startfile_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[Path] = []
    fake_os = SimpleNamespace(
        name="nt",
        startfile=lambda path: opened.append(path),
    )
    monkeypatch.setattr(admin, "os", fake_os)

    admin._open_with_system_app(Path("example.txt"))

    assert opened == [Path("example.txt")]


def test_open_with_system_app_uses_platform_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    fake_os = SimpleNamespace(name="posix")
    fake_sys = SimpleNamespace(platform="darwin")
    monkeypatch.setattr(admin, "os", fake_os)
    monkeypatch.setattr(admin, "sys", fake_sys)

    def _record_run(args: list[str], check: bool) -> None:
        del check
        calls.append(args)

    monkeypatch.setattr(admin.subprocess, "run", _record_run)

    admin._open_with_system_app(Path("example.txt"))
    fake_sys.platform = "linux"
    admin._open_with_system_app(Path("example.txt"))

    assert calls == [["open", "example.txt"], ["xdg-open", "example.txt"]]


def test_open_in_editor_prefers_editor_env(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setenv("EDITOR", "code")

    def _record_run(args: list[str], check: bool) -> None:
        del check
        calls.append(args)

    monkeypatch.setattr(admin.subprocess, "run", _record_run)

    admin._open_in_editor(Path("config.env"))

    assert calls == [["code", "config.env"]]


def test_open_in_editor_platform_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    fake_os = SimpleNamespace(name="nt", environ={})
    fake_sys = SimpleNamespace(platform="darwin")
    monkeypatch.setattr(admin, "os", fake_os)
    monkeypatch.setattr(admin, "sys", fake_sys)

    def _record_run(args: list[str], check: bool) -> None:
        del check
        calls.append(args)

    monkeypatch.setattr(admin.subprocess, "run", _record_run)

    admin._open_in_editor(Path("config.env"))

    fake_os.name = "posix"
    fake_sys.platform = "darwin"
    admin._open_in_editor(Path("config.env"))

    fake_sys.platform = "linux"
    admin._open_in_editor(Path("config.env"))

    assert calls == [
        ["notepad", "config.env"],
        ["open", "-t", "config.env"],
        ["nano", "config.env"],
    ]


def test_load_repository_without_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "cache.db"
    monkeypatch.setattr(admin, "get_cache_db_path", lambda: db_path)

    repository, resolved = admin._load_repository()

    assert repository is None
    assert resolved == db_path


def test_load_repository_with_existing_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "cache.db"
    db_path.write_text("", encoding="utf-8")
    repository = object()

    monkeypatch.setattr(admin, "get_cache_db_path", lambda: db_path)
    monkeypatch.setattr(
        "notewise.storage.repository.DatabaseRepository.get_instance",
        lambda path: repository if path == db_path else None,
    )

    loaded, resolved = admin._load_repository()

    assert loaded is repository
    assert resolved == db_path


def test_render_stats_handles_empty_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    console = _console()
    monkeypatch.setattr(admin, "_load_repository", lambda: (None, Path("cache.db")))

    admin.render_stats(console, since=None, model=None)

    assert "No cache database found yet" in _text(console)


def test_render_stats_renders_summary_and_breakdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    console = _console()
    stats = SimpleNamespace(
        total_videos_processed=2,
        total_runs=4,
        total_tokens_used=1234,
        total_prompt_tokens=456,
        total_completion_tokens=778,
        total_cost_usd=1.2345,
        total_transcript_seconds=12,
        total_generation_seconds=90,
        models=[
            SimpleNamespace(
                model="gemini/gemini-2.5-flash",
                videos_processed=2,
                run_count=4,
                total_tokens_used=1234,
                total_cost_usd=1.2345,
            )
        ],
    )

    def _get_stats(*, since_days: int | None, model: str | None):
        del since_days, model
        return stats

    repository = SimpleNamespace(get_stats=_get_stats)
    monkeypatch.setattr(
        admin, "_load_repository", lambda: (repository, Path("cache.db"))
    )

    admin.render_stats(console, since="7d", model="gemini/gemini-2.5-flash")

    output = _text(console)
    assert "Processing Statistics" in output
    assert "Model Breakdown" in output
    assert "gemini/gemini-2.5-flash" in output


def test_render_history_handles_empty_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    console = _console()

    def _get_recent_videos(limit: int):
        del limit
        return []

    repository = SimpleNamespace(get_recent_videos=_get_recent_videos)
    monkeypatch.setattr(
        admin, "_load_repository", lambda: (repository, Path("cache.db"))
    )

    admin.render_history(console, limit=5)

    assert "No processed video history found yet" in _text(console)


def test_render_history_renders_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    console = _console()

    def _get_recent_videos(limit: int):
        del limit
        return [
            SimpleNamespace(
                title="Video One",
                model="gemini/gemini-2.5-flash",
                cost_usd=0.25,
                last_run_at=datetime(2026, 3, 22, tzinfo=UTC),
            )
        ]

    repository = SimpleNamespace(get_recent_videos=_get_recent_videos)
    monkeypatch.setattr(
        admin, "_load_repository", lambda: (repository, Path("cache.db"))
    )

    admin.render_history(console, limit=5)

    output = _text(console)
    assert "Recent Videos" in output
    assert "Video One" in output


def test_render_runtime_info(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    console = _console()
    settings = SimpleNamespace(
        default_output_dir=tmp_path / "output",
        default_model="gemini/gemini-2.5-flash",
        default_languages=["en", "hi"],
        max_concurrent_videos=3,
        max_concurrent_chapters=2,
        youtube_requests_per_minute=10,
        youtube_cookie_file=None,
    )
    monkeypatch.setattr(admin, "app_settings", settings)
    monkeypatch.setattr(admin, "get_state_dir", lambda: tmp_path)
    monkeypatch.setattr(admin, "get_cache_db_path", lambda: tmp_path / "cache.db")

    admin.render_runtime_info(console)

    output = _text(console)
    assert "notewise Info" in output
    assert "gemini/gemini-2.5-flash" in output
    assert "en, hi" in output


@pytest.mark.asyncio
async def test_render_source_info_renders_playlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    console = _console()
    repository = SimpleNamespace(get_cached_video_ids=lambda _video_ids: {"a"})
    monkeypatch.setattr(
        admin, "_load_repository", lambda: (repository, Path("cache.db"))
    )

    def _parse_playlist_url(_url: str):
        return SimpleNamespace(
            url_type="playlist",
            playlist_id="PL123",
            video_id=None,
        )

    await admin.render_source_info(
        console,
        url="PL123",
        parse_youtube_url=_parse_playlist_url,
        get_video_details=AsyncMock(),
        get_source_metadata=AsyncMock(
            return_value={
                "title": "Playlist Title",
                "data": {"playlist_count": 3, "uploader": "Playlist Channel"},
            }
        ),
        get_playlist_info=AsyncMock(),
        extract_playlist_videos=AsyncMock(return_value=["a", "a", "b"]),
        cookie_file=None,
    )

    output = _text(console)
    assert "Playlist Info" in output
    assert "Resolvable videos" in output
    assert "1/2 processed" in output


@pytest.mark.asyncio
async def test_render_source_info_uses_bulk_cache_lookup_for_playlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    console = _console()
    bulk_lookup = Mock(return_value={"a", "c"})
    repository = SimpleNamespace(
        get_cached_video_ids=bulk_lookup,
        has_video=Mock(side_effect=AssertionError("has_video should not be called")),
    )
    monkeypatch.setattr(
        admin, "_load_repository", lambda: (repository, Path("cache.db"))
    )

    await admin.render_source_info(
        console,
        url="PL123",
        parse_youtube_url=lambda _url: SimpleNamespace(
            url_type="playlist",
            playlist_id="PL123",
            video_id=None,
        ),
        get_video_details=AsyncMock(),
        get_source_metadata=AsyncMock(
            return_value={
                "title": "Playlist Title",
                "data": {"playlist_count": 4},
            }
        ),
        get_playlist_info=AsyncMock(),
        extract_playlist_videos=AsyncMock(return_value=["a", "a", "b", "c"]),
        cookie_file=None,
    )

    bulk_lookup.assert_called_once_with(["a", "b", "c"])
    repository.has_video.assert_not_called()
    assert "2/3 processed" in _text(console)


@pytest.mark.asyncio
async def test_render_source_info_renders_video(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    console = _console()
    cached_video = SimpleNamespace(cached_at=datetime(2026, 3, 22, tzinfo=UTC))

    def _get_video(video_id: str):
        del video_id
        return cached_video

    repository = SimpleNamespace(get_video=_get_video)
    monkeypatch.setattr(
        admin, "_load_repository", lambda: (repository, Path("cache.db"))
    )

    await admin.render_source_info(
        console,
        url="dfH5KSMzj00",
        parse_youtube_url=lambda url: SimpleNamespace(url_type="video", video_id=url),
        get_video_details=AsyncMock(
            return_value={
                "title": "Bit Manipulation",
                "uploader": "Jaydeep",
                "duration": 62,
                "chapters": [{"title": "Intro"}],
                "subtitles": {"en": {}},
                "automatic_captions": {"hi": {}},
                "view_count": "42",
            }
        ),
        get_source_metadata=AsyncMock(),
        get_playlist_info=AsyncMock(),
        extract_playlist_videos=AsyncMock(),
        cookie_file=None,
    )

    output = _text(console)
    assert "Video Info" in output
    assert "Bit Manipulation" in output
    assert "Jaydeep" in output
    assert "42" in output


@pytest.mark.asyncio
async def test_render_source_info_rejects_unresolvable_video(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    console = _console()
    monkeypatch.setattr(admin, "_load_repository", lambda: (None, Path("cache.db")))

    def _parse_invalid_video(_url: str):
        return SimpleNamespace(url_type="video", video_id=None)

    with pytest.raises(ValueError, match="resolvable YouTube video id"):
        await admin.render_source_info(
            console,
            url="invalid",
            parse_youtube_url=_parse_invalid_video,
            get_video_details=AsyncMock(),
            get_source_metadata=AsyncMock(),
            get_playlist_info=AsyncMock(),
            extract_playlist_videos=AsyncMock(),
            cookie_file=None,
        )


def test_render_doctor_ready(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    console = _console()
    config_path = tmp_path / admin.CONFIG_FILENAME
    config_path.write_text("DEFAULT_MODEL=x\n", encoding="utf-8")
    db_path = tmp_path / "cache.db"
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute("CREATE TABLE test (id INTEGER)")
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    latest_log = log_dir / "latest.log"
    latest_log.write_text("log", encoding="utf-8")

    def _api_key_name(_model: str) -> str:
        return "GEMINI_API_KEY"

    def _log_dir(_state_dir: Path) -> Path:
        return log_dir

    settings = SimpleNamespace(
        default_model="gemini/gemini-2.5-flash",
        default_output_dir=tmp_path / "out",
        get_api_key_name_for_model=_api_key_name,
    )
    monkeypatch.setattr(admin, "app_settings", settings)
    monkeypatch.setattr(admin, "get_state_dir", lambda: tmp_path)
    monkeypatch.setattr(admin, "get_cache_db_path", lambda: db_path)
    monkeypatch.setattr(admin, "get_log_dir", _log_dir)
    monkeypatch.setattr(admin, "get_session_log_path", lambda: latest_log)
    monkeypatch.setenv("GEMINI_API_KEY", "secret")

    admin.render_doctor(console)

    output = _text(console)
    assert "notewise Doctor" in output
    assert "Ready" in output
    assert "Latest log" in output


def test_render_cache_info_and_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    console = _console()
    summary = SimpleNamespace(
        total_videos=2,
        total_transcripts=2,
        total_runs=3,
        total_exports=1,
        oldest_cached_at=datetime(2026, 3, 20, tzinfo=UTC),
        newest_cached_at=datetime(2026, 3, 22, tzinfo=UTC),
    )
    repository = SimpleNamespace(
        get_cache_summary=lambda: summary,
        get_video=lambda video_id: SimpleNamespace(
            id=video_id,
            title="Video One",
            duration=75,
            cached_at=datetime(2026, 3, 22, tzinfo=UTC),
        ),
        get_transcript=lambda _video_id: object(),
        get_run_stats=lambda _video_id: [
            SimpleNamespace(model="gemini/gemini-2.5-flash", cost_usd=0.25)
        ],
        get_export_records=lambda _video_id: ["notes.md"],
    )
    monkeypatch.setattr(
        admin,
        "_load_repository",
        lambda: (repository, Path(__file__)),
    )

    admin.render_cache_info(console)
    admin.render_cache_entry(console, video_id="abc123")

    output = _text(console)
    assert "Cache Info" in output
    assert "Cached Video" in output
    assert "Video One" in output


def test_clear_cache_and_prune_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    console = _console()
    db_path = tmp_path / "cache.db"
    shm_path = tmp_path / "cache.db-shm"
    wal_path = tmp_path / "cache.db-wal"
    for path in (db_path, shm_path, wal_path):
        path.write_text("x", encoding="utf-8")

    close_instance = MagicMock()
    monkeypatch.setattr(admin, "get_cache_db_path", lambda: db_path)
    monkeypatch.setattr(
        "notewise.storage.repository.DatabaseRepository.close_instance",
        close_instance,
    )

    admin.clear_cache(console)

    def _prune_old_entries(*, older_than_days: int) -> int:
        del older_than_days
        return 3

    prune_repository = SimpleNamespace(prune_old_entries=_prune_old_entries)
    monkeypatch.setattr(
        admin,
        "_load_repository",
        lambda: (prune_repository, db_path),
    )
    admin.prune_cache(console, older_than_days=7)

    output = _text(console)
    assert "Removed 3 cache file(s)." in output
    assert "Pruned 3 cache entries older than 7 day(s)." in output
    close_instance.assert_called_once_with(db_path)


def test_render_logs_listing_and_tail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    console = _console()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    older = log_dir / "older.log"
    older.write_text("older\n", encoding="utf-8")
    latest = log_dir / "latest.log"
    latest.write_text("line1\nline2\nline3\n", encoding="utf-8")

    def _log_dir(_state_dir: Path) -> Path:
        return log_dir

    monkeypatch.setattr(admin, "get_state_dir", lambda: tmp_path)
    monkeypatch.setattr(admin, "get_log_dir", _log_dir)

    admin.render_logs(console, tail=None, open_dir=False)
    admin.render_logs(console, tail=2, open_dir=False)

    output = _text(console)
    assert "Session Logs" in output
    assert "Latest Log Tail" in output
    assert "line2" in output
    assert "line3" in output


def test_render_logs_open_dir_and_clean_logs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    console = _console()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    keep = log_dir / "active.log"
    keep.write_text("active", encoding="utf-8")
    drop = log_dir / "drop.log"
    drop.write_text("old", encoding="utf-8")
    opened: list[Path] = []

    def _log_dir(_state_dir: Path) -> Path:
        return log_dir

    def _prune_log_files(*, older_than_days: int, state_dir: Path) -> int:
        del older_than_days, state_dir
        return 4

    monkeypatch.setattr(admin, "get_state_dir", lambda: tmp_path)
    monkeypatch.setattr(admin, "get_log_dir", _log_dir)
    monkeypatch.setattr(
        admin, "_open_with_system_app", lambda path: opened.append(path)
    )
    monkeypatch.setattr(admin, "get_session_log_path", lambda: keep)

    admin.render_logs(console, tail=None, open_dir=True)
    admin.clean_logs(console, all_logs=False, older_than_days=30)
    monkeypatch.setattr(admin, "prune_log_files", _prune_log_files)
    admin.clean_logs(console, all_logs=False, older_than_days=30)
    admin.clean_logs(console, all_logs=True, older_than_days=30)

    output = _text(console)
    assert opened == [log_dir]
    assert "Opened" in output
    assert "Removed 4 log file(s) older than 30 day(s)." in output
    assert "Removed 1 log file(s)." in output
    assert keep.exists()
    assert not drop.exists()


def test_edit_config_handles_missing_and_existing_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    console = _console()
    config_path = tmp_path / admin.CONFIG_FILENAME
    opened: list[Path] = []
    monkeypatch.setattr(admin, "get_state_dir", lambda: tmp_path)
    monkeypatch.setattr(admin, "_open_in_editor", lambda path: opened.append(path))

    admin.edit_config(console)
    config_path.write_text("DEFAULT_MODEL=x\n", encoding="utf-8")
    admin.edit_config(console)

    output = _text(console)
    normalized_output = output.replace("\n", "").replace("\r", "")
    assert "Run `notewise setup` first" in output
    assert "Opened" in output
    assert str(config_path) in normalized_output
    assert opened == [config_path]


def test_render_stats_handles_empty_model_breakdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    console = _console()
    repository = SimpleNamespace(
        get_stats=lambda **_: SimpleNamespace(
            total_videos_processed=0,
            total_runs=0,
            total_tokens_used=0,
            total_prompt_tokens=0,
            total_completion_tokens=0,
            total_cost_usd=0.0,
            total_transcript_seconds=0.0,
            total_generation_seconds=0.0,
            models=[],
        )
    )
    monkeypatch.setattr(
        admin, "_load_repository", lambda: (repository, Path("cache.db"))
    )

    admin.render_stats(console, since=None, model=None)

    assert "No model-specific runs found for that filter." in _text(console)


def test_render_doctor_reports_output_and_db_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    console = _console()
    config_path = tmp_path / admin.CONFIG_FILENAME
    config_path.write_text("DEFAULT_MODEL=x\n", encoding="utf-8")
    db_path = tmp_path / "cache.db"
    db_path.write_text("broken", encoding="utf-8")

    settings = SimpleNamespace(
        default_model="gemini/gemini-2.5-flash",
        default_output_dir=tmp_path / "out",
        get_api_key_name_for_model=lambda _model: "GEMINI_API_KEY",
    )
    monkeypatch.setattr(admin, "app_settings", settings)
    monkeypatch.setattr(admin, "get_state_dir", lambda: tmp_path)
    monkeypatch.setattr(admin, "get_cache_db_path", lambda: db_path)
    monkeypatch.setattr(admin, "get_log_dir", lambda _state_dir: tmp_path / "missing")
    monkeypatch.setattr(admin, "get_session_log_path", lambda: None)

    def _raise_readonly(*_args, **_kwargs):
        raise OSError("readonly")

    monkeypatch.setattr(Path, "write_text", _raise_readonly)

    admin.render_doctor(console)

    output = _text(console)
    assert "Needs attention" in output
    assert "not writable" in output
    assert "FAIL" in output


def test_render_cache_info_and_entry_handle_missing_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    console = _console()
    monkeypatch.setattr(admin, "_load_repository", lambda: (None, Path("cache.db")))

    admin.render_cache_info(console)
    admin.render_cache_entry(console, video_id="abc123")

    repository = SimpleNamespace(
        get_video=lambda _video_id: None,
        get_transcript=lambda _video_id: None,
        get_run_stats=lambda _video_id: [],
        get_export_records=lambda _video_id: [],
    )
    monkeypatch.setattr(
        admin, "_load_repository", lambda: (repository, Path("cache.db"))
    )
    admin.render_cache_entry(console, video_id="abc123")

    output = _text(console)
    assert "No cache database found at cache.db." in output
    assert "No cached record found for abc123." in output


def test_clear_cache_and_prune_cache_handle_missing_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    console = _console()
    monkeypatch.setattr(admin, "get_cache_db_path", lambda: Path("cache.db"))
    monkeypatch.setattr(admin, "_load_repository", lambda: (None, Path("cache.db")))

    admin.clear_cache(console)
    admin.prune_cache(console, older_than_days=7)

    assert _text(console).count("No cache database found at cache.db.") == 2


def test_render_logs_tail_and_clean_logs_handle_missing_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    console = _console()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setattr(admin, "get_state_dir", lambda: tmp_path)
    monkeypatch.setattr(admin, "get_log_dir", lambda _state_dir: log_dir)

    admin.render_logs(console, tail=5, open_dir=False)

    missing_dir = tmp_path / "missing"
    monkeypatch.setattr(admin, "get_log_dir", lambda _state_dir: missing_dir)
    admin.clean_logs(console, all_logs=False, older_than_days=30)

    output = _text(console)
    normalized_output = output.replace("\n", "").replace("\r", "")
    assert "No log files found." in output
    assert "No log directory found at" in output
    assert str(missing_dir) in normalized_output
