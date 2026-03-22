"""Integration coverage for cache repository lifecycle helpers."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest

from yt_study.storage.repository import DatabaseRepository


def test_legacy_cache_db_is_upgraded_to_latest_schema_version(tmp_path):
    """Legacy DBs should gain both additive migrations and schema version state."""
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

    db = DatabaseRepository.get_instance(db_path)
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
        version = connection.execute(
            "SELECT version FROM schema_version LIMIT 1"
        ).fetchone()
        video_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(video)").fetchall()
        }
        runstats_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(runstats)").fetchall()
        }

    assert version == (2,)
    assert "cached_at" in video_columns
    assert {
        "prompt_tokens",
        "completion_tokens",
        "cost_usd",
        "transcript_seconds",
        "generation_seconds",
    }.issubset(runstats_columns)


def test_cached_at_is_set_and_refreshed_on_upsert(tmp_path):
    """Each cache write should stamp a fresh cached_at timestamp on the video row."""
    db = DatabaseRepository.get_instance(tmp_path / "cache.db")
    db.upsert_video_cache(
        video_id="video-1",
        title="Video One",
        duration=120,
        transcript_content="hello world transcript",
        language="en",
        tokens_used=42,
        model="gemini/gemini-2.5-flash",
    )
    first = db.get_video("video-1")
    assert first is not None
    assert first.cached_at is not None

    stale_time = datetime.now(timezone.utc) - timedelta(days=10)
    with closing(sqlite3.connect(tmp_path / "cache.db")) as connection:
        connection.execute(
            "UPDATE video SET cached_at = ? WHERE id = ?",
            (stale_time.isoformat(sep=" "), "video-1"),
        )
        connection.commit()

    db.upsert_video_cache(
        video_id="video-1",
        title="Video One Updated",
        duration=240,
        transcript_content="updated transcript",
        language="en",
        tokens_used=99,
        model="gemini/gemini-2.5-flash",
    )
    second = db.get_video("video-1")
    assert second is not None
    assert second.cached_at is not None
    assert second.cached_at.replace(tzinfo=timezone.utc) > stale_time


def test_get_recent_videos_returns_latest_runs_first(tmp_path):
    """History helper should join each video with its latest run metadata."""
    db_path = tmp_path / "cache.db"
    db = DatabaseRepository.get_instance(db_path)
    db.upsert_video_cache(
        video_id="video-1",
        title="First",
        duration=100,
        transcript_content="first",
        language="en",
        tokens_used=10,
        cost_usd=0.1,
        model="model-a",
    )
    db.upsert_video_cache(
        video_id="video-2",
        title="Second",
        duration=200,
        transcript_content="second",
        language="en",
        tokens_used=20,
        cost_usd=0.2,
        model="model-b",
    )

    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute(
            "UPDATE runstats SET timestamp = ? WHERE video_id = ?",
            ("2026-03-20 11:00:00+00:00", "video-1"),
        )
        connection.execute(
            "UPDATE runstats SET timestamp = ? WHERE video_id = ?",
            ("2026-03-21 11:00:00+00:00", "video-2"),
        )
        connection.commit()

    recent = db.get_recent_videos(limit=2)

    assert [row.id for row in recent] == ["video-2", "video-1"]
    assert recent[0].model == "model-b"
    assert recent[0].cost_usd == 0.2


def test_get_stats_returns_totals_and_model_breakdown(tmp_path):
    """Stats helper should aggregate totals and grouped model summaries."""
    db = DatabaseRepository.get_instance(tmp_path / "cache.db")
    db.upsert_video_cache(
        video_id="video-1",
        title="One",
        duration=100,
        transcript_content="one",
        language="en",
        tokens_used=10,
        prompt_tokens=6,
        completion_tokens=4,
        cost_usd=0.1,
        model="model-a",
        transcript_seconds=1.0,
        generation_seconds=2.0,
    )
    db.upsert_video_cache(
        video_id="video-2",
        title="Two",
        duration=200,
        transcript_content="two",
        language="en",
        tokens_used=20,
        prompt_tokens=12,
        completion_tokens=8,
        cost_usd=0.2,
        model="model-b",
        transcript_seconds=2.0,
        generation_seconds=3.0,
    )
    db.upsert_video_cache(
        video_id="video-1",
        title="One",
        duration=100,
        transcript_content="one again",
        language="en",
        tokens_used=30,
        prompt_tokens=18,
        completion_tokens=12,
        cost_usd=0.3,
        model="model-a",
        transcript_seconds=4.0,
        generation_seconds=5.0,
    )

    stats = db.get_stats()

    assert stats.total_videos_processed == 2
    assert stats.total_runs == 3
    assert stats.total_tokens_used == 60
    assert stats.total_cost_usd == pytest.approx(0.6)
    assert [row.model for row in stats.models] == ["model-a", "model-b"]
    assert stats.models[0].videos_processed == 1
    assert stats.models[0].run_count == 2
    assert stats.models[0].total_tokens_used == 40


def test_prune_old_entries_removes_only_stale_cache_rows(tmp_path):
    """Pruning should delete only stale videos and cascade their child records."""
    db_path = tmp_path / "cache.db"
    db = DatabaseRepository.get_instance(db_path)
    for video_id in ("old-video", "new-video"):
        db.upsert_video_cache(
            video_id=video_id,
            title=video_id,
            duration=100,
            transcript_content=video_id,
            language="en",
            tokens_used=10,
            model="model-a",
        )

    old_time = datetime.now(timezone.utc) - timedelta(days=45)
    new_time = datetime.now(timezone.utc) - timedelta(days=2)
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute(
            "UPDATE video SET cached_at = ? WHERE id = ?",
            (old_time.isoformat(sep=" "), "old-video"),
        )
        connection.execute(
            "UPDATE video SET cached_at = ? WHERE id = ?",
            (new_time.isoformat(sep=" "), "new-video"),
        )
        connection.commit()

    deleted = db.prune_old_entries(older_than_days=30)

    assert deleted == 1
    assert db.get_video("old-video") is None
    assert db.get_transcript("old-video") is None
    assert db.get_run_stats("old-video") == []
    assert db.get_video("new-video") is not None


def test_get_cache_summary_reports_counts_and_bounds(tmp_path):
    """Cache summary should expose counts and oldest/newest cached timestamps."""
    db_path = tmp_path / "cache.db"
    db = DatabaseRepository.get_instance(db_path)
    db.upsert_video_cache(
        video_id="video-1",
        title="One",
        duration=100,
        transcript_content="one",
        language="en",
        tokens_used=10,
        model="model-a",
    )
    db.upsert_video_cache(
        video_id="video-2",
        title="Two",
        duration=200,
        transcript_content="two",
        language="en",
        tokens_used=20,
        model="model-b",
    )
    db.add_export_record(
        video_id="video-1",
        format="txt",
        output_path=str(tmp_path / "video-1.txt"),
    )

    older = datetime.now(timezone.utc) - timedelta(days=10)
    newer = datetime.now(timezone.utc) - timedelta(days=1)
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute(
            "UPDATE video SET cached_at = ? WHERE id = ?",
            (older.isoformat(sep=" "), "video-1"),
        )
        connection.execute(
            "UPDATE video SET cached_at = ? WHERE id = ?",
            (newer.isoformat(sep=" "), "video-2"),
        )
        connection.commit()

    summary = db.get_cache_summary()

    assert summary.total_videos == 2
    assert summary.total_transcripts == 2
    assert summary.total_runs == 2
    assert summary.total_exports == 1
    assert summary.oldest_cached_at is not None
    assert summary.newest_cached_at is not None
    assert summary.oldest_cached_at < summary.newest_cached_at
