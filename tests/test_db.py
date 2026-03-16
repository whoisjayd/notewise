"""Tests for SQLite cache database manager."""

import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import pytest

from yt_study.db import (
    CACHE_DB_FILENAME,
    DatabaseManager,
    build_cache_db_path,
)


@pytest.fixture(autouse=True)
def _close_db_instances():
    """Close all DatabaseManager singletons after each test."""
    yield
    DatabaseManager.close_all_instances()


def test_database_manager_singleton_for_same_path(tmp_path):
    """Same db path should return the same singleton instance."""
    db_path = tmp_path / CACHE_DB_FILENAME
    manager_one = DatabaseManager.get_instance(db_path)
    manager_two = DatabaseManager.get_instance(db_path)

    assert manager_one is manager_two


def test_build_cache_db_path_scopes_under_user_config_dir():
    """Cache DB path should be stable and stored under ~/.yt-study."""
    cache_path = build_cache_db_path()

    assert cache_path.parent == Path(os.environ["YT_STUDY_HOME"])
    assert cache_path.name == CACHE_DB_FILENAME


def test_build_cache_db_path_is_stable_across_calls():
    """Cache DB path should remain stable across repeated calls."""
    cache_one = build_cache_db_path()
    cache_two = build_cache_db_path()

    assert cache_one == cache_two


def test_database_manager_singleton_normalizes_equivalent_paths(tmp_path):
    """Equivalent paths should map to the same singleton instance."""
    normalized = tmp_path / "cache.db"
    alternate = tmp_path / "subdir" / ".." / "cache.db"

    manager_one = DatabaseManager.get_instance(normalized)
    manager_two = DatabaseManager.get_instance(alternate)

    assert manager_one is manager_two


def test_database_manager_uses_distinct_instances_per_path(tmp_path):
    """Different db paths should not share singleton instances."""
    manager_one = DatabaseManager.get_instance(tmp_path / "one.db")
    manager_two = DatabaseManager.get_instance(tmp_path / "two.db")

    assert manager_one is not manager_two


def test_database_manager_singleton_thread_safe_under_concurrency(tmp_path):
    """Concurrent get_instance calls should return the same singleton."""
    db_path = tmp_path / "threadsafe.db"

    def get_manager(_: int) -> DatabaseManager:
        return DatabaseManager.get_instance(db_path)

    with ThreadPoolExecutor(max_workers=8) as executor:
        managers = list(executor.map(get_manager, range(24)))

    first = managers[0]
    assert all(manager is first for manager in managers)


def test_upsert_video_cache_persists_video_transcript_and_run_stats(tmp_path):
    """Upsert should persist core records for a processed video."""
    db = DatabaseManager.get_instance(tmp_path / "cache.db")

    db.upsert_video_cache(
        video_id="video-1",
        title="Video One",
        duration=120,
        transcript_content="hello world transcript",
        language="en",
        tokens_used=42,
        prompt_tokens=30,
        completion_tokens=12,
        cost_usd=0.123456,
        model="gemini/gemini-2.5-flash",
        transcript_seconds=1.5,
        generation_seconds=2.5,
    )

    assert db.has_video("video-1") is True
    video = db.get_video("video-1")
    transcript = db.get_transcript("video-1")
    stats = db.get_run_stats("video-1")

    assert video is not None
    assert video.title == "Video One"
    assert video.duration == 120
    assert transcript is not None
    assert transcript.content == "hello world transcript"
    assert transcript.language == "en"
    assert len(stats) == 1
    assert stats[0].tokens_used == 42
    assert stats[0].prompt_tokens == 30
    assert stats[0].completion_tokens == 12
    assert stats[0].cost_usd == 0.123456
    assert stats[0].transcript_seconds == 1.5
    assert stats[0].generation_seconds == 2.5


def test_upsert_video_cache_updates_existing_video_and_transcript(tmp_path):
    """Upsert should update metadata/transcript while appending run stats."""
    db = DatabaseManager.get_instance(tmp_path / "cache.db")

    db.upsert_video_cache(
        video_id="video-1",
        title="Old Title",
        duration=100,
        transcript_content="old transcript",
        language="en",
        tokens_used=10,
        prompt_tokens=7,
        completion_tokens=3,
        cost_usd=0.01,
        model="old-model",
        transcript_seconds=0.5,
        generation_seconds=1.0,
    )
    db.upsert_video_cache(
        video_id="video-1",
        title="New Title",
        duration=220,
        transcript_content="new transcript",
        language="hi",
        tokens_used=30,
        prompt_tokens=20,
        completion_tokens=10,
        cost_usd=0.02,
        model="new-model",
        transcript_seconds=0.7,
        generation_seconds=1.4,
    )

    video = db.get_video("video-1")
    transcript = db.get_transcript("video-1")
    stats = db.get_run_stats("video-1")

    assert video is not None
    assert video.title == "New Title"
    assert video.duration == 220
    assert transcript is not None
    assert transcript.content == "new transcript"
    assert transcript.language == "hi"
    assert len(stats) == 2
    assert any(row.model == "new-model" for row in stats)
    assert any(row.prompt_tokens == 20 for row in stats)
    assert any(row.completion_tokens == 10 for row in stats)
    assert any(row.cost_usd == 0.02 for row in stats)


def test_upsert_video_cache_thread_safe_under_concurrency(tmp_path):
    """Concurrent upserts should remain consistent and avoid race failures."""
    db = DatabaseManager.get_instance(tmp_path / "concurrent.db")

    def write_row(index: int) -> None:
        db.upsert_video_cache(
            video_id="shared-video-id",
            title=f"Title {index}",
            duration=100 + index,
            transcript_content=f"transcript {index}",
            language="en",
            tokens_used=index + 1,
            model="mock-model",
        )

    with ThreadPoolExecutor(max_workers=10) as executor:
        list(executor.map(write_row, range(30)))

    video = db.get_video("shared-video-id")
    transcript = db.get_transcript("shared-video-id")
    stats = db.get_run_stats("shared-video-id")

    assert video is not None
    assert transcript is not None
    assert video.title.startswith("Title ")
    assert transcript.content.startswith("transcript ")
    assert len(stats) == 30


def test_database_manager_close_instance_evicts_singleton(tmp_path):
    """close_instance should dispose and recreate singleton cleanly."""
    db_path = tmp_path / "cache.db"
    manager_one = DatabaseManager.get_instance(db_path)

    DatabaseManager.close_instance(db_path)
    manager_two = DatabaseManager.get_instance(db_path)

    assert manager_one is not manager_two


def test_database_manager_repairs_older_runstats_schema_in_place(tmp_path):
    """Older cache DBs should be upgraded before new metric writes occur."""
    db_path = tmp_path / "legacy-cache.db"
    with closing(sqlite3.connect(db_path)) as connection:
        connection.executescript(
            """
            CREATE TABLE video (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                duration INTEGER NOT NULL
            );
            CREATE TABLE transcript (
                id INTEGER PRIMARY KEY,
                video_id TEXT NOT NULL UNIQUE,
                content TEXT NOT NULL,
                language TEXT NOT NULL
            );
            CREATE TABLE runstats (
                id INTEGER PRIMARY KEY,
                video_id TEXT NOT NULL,
                tokens_used INTEGER NOT NULL,
                model TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            """
        )

    db = DatabaseManager.get_instance(db_path)
    db.upsert_video_cache(
        video_id="video-legacy",
        title="Legacy Video",
        duration=90,
        transcript_content="legacy transcript",
        language="en",
        tokens_used=12,
        prompt_tokens=7,
        completion_tokens=5,
        cost_usd=0.5,
        model="gemini/gemini-2.5-flash",
        transcript_seconds=1.25,
        generation_seconds=2.75,
    )

    with closing(sqlite3.connect(db_path)) as connection:
        columns = {
            row[1]: row[4]
            for row in connection.execute("PRAGMA table_info(runstats)").fetchall()
        }

    assert columns["prompt_tokens"] == "0"
    assert columns["completion_tokens"] == "0"
    assert columns["cost_usd"] == "0.0"
    assert columns["transcript_seconds"] == "0.0"
    assert columns["generation_seconds"] == "0.0"

    stats = db.get_run_stats("video-legacy")
    assert len(stats) == 1
    assert stats[0].prompt_tokens == 7
    assert stats[0].completion_tokens == 5
    assert stats[0].cost_usd == 0.5
    assert stats[0].transcript_seconds == 1.25
    assert stats[0].generation_seconds == 2.75


def test_get_run_stats_orders_rows_chronologically(tmp_path):
    """Run stats should be returned oldest-first for stable latest-row access."""
    db_path = tmp_path / "ordered-cache.db"
    db = DatabaseManager.get_instance(db_path)

    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute(
            "INSERT INTO video (id, title, duration) VALUES (?, ?, ?)",
            ("video-1", "Video One", 120),
        )
        connection.execute(
            """
            INSERT INTO runstats (
                video_id,
                tokens_used,
                prompt_tokens,
                completion_tokens,
                cost_usd,
                model,
                transcript_seconds,
                generation_seconds,
                timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "video-1",
                20,
                12,
                8,
                0.2,
                "model-newer",
                1.0,
                2.0,
                "2026-03-13 12:00:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO runstats (
                video_id,
                tokens_used,
                prompt_tokens,
                completion_tokens,
                cost_usd,
                model,
                transcript_seconds,
                generation_seconds,
                timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "video-1",
                10,
                6,
                4,
                0.1,
                "model-older",
                0.5,
                1.5,
                "2026-03-13 11:00:00+00:00",
            ),
        )
        connection.commit()

    stats = db.get_run_stats("video-1")

    assert [row.model for row in stats] == ["model-older", "model-newer"]


# ---------------------------------------------------------------------------
# ExportRecord tests
# ---------------------------------------------------------------------------


def test_add_export_record_txt(tmp_path):
    """add_export_record persists a txt export record."""
    db = DatabaseManager.get_instance(tmp_path / "cache.db")

    # First create the video
    db.upsert_video_cache(
        video_id="video-1",
        title="Test Video",
        duration=120,
        transcript_content="test transcript",
        language="en",
        tokens_used=10,
        model="test-model",
    )

    db.add_export_record(
        video_id="video-1",
        format="txt",
        output_path="/output/Test Video_transcript.txt",
    )

    records = db.get_export_records("video-1")
    assert len(records) == 1
    assert records[0].format == "txt"
    assert records[0].output_path == "/output/Test Video_transcript.txt"


def test_add_export_record_json(tmp_path):
    """add_export_record persists a json export record."""
    db = DatabaseManager.get_instance(tmp_path / "cache.db")

    db.upsert_video_cache(
        video_id="video-2",
        title="Test Video 2",
        duration=120,
        transcript_content="test transcript",
        language="en",
        tokens_used=10,
        model="test-model",
    )

    db.add_export_record(
        video_id="video-2",
        format="json",
        output_path="/output/Test Video 2_transcript.json",
    )

    records = db.get_export_records("video-2")
    assert len(records) == 1
    assert records[0].format == "json"


def test_get_export_records_multiple(tmp_path):
    """get_export_records returns all export records for a video."""
    db = DatabaseManager.get_instance(tmp_path / "cache.db")

    db.upsert_video_cache(
        video_id="video-3",
        title="Test Video 3",
        duration=120,
        transcript_content="test transcript",
        language="en",
        tokens_used=10,
        model="test-model",
    )

    db.add_export_record(video_id="video-3", format="txt", output_path="/path/1.txt")
    db.add_export_record(video_id="video-3", format="json", output_path="/path/2.json")

    records = db.get_export_records("video-3")
    assert len(records) == 2
    formats = [r.format for r in records]
    assert "txt" in formats
    assert "json" in formats


def test_get_export_records_empty(tmp_path):
    """get_export_records returns empty list for video with no exports."""
    db = DatabaseManager.get_instance(tmp_path / "cache.db")

    db.upsert_video_cache(
        video_id="video-4",
        title="Test Video 4",
        duration=120,
        transcript_content="test transcript",
        language="en",
        tokens_used=10,
        model="test-model",
    )

    records = db.get_export_records("video-4")
    assert len(records) == 0
