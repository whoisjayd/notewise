"""Unit tests for schema versioned SQLite migrations."""

from __future__ import annotations

from sqlalchemy import create_engine

from yt_study.storage.migrations import run_migrations


def test_run_migrations_is_idempotent_and_reaches_latest_schema(tmp_path):
    """Running migrations repeatedly should settle at schema version 2."""
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE video (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    duration INTEGER NOT NULL
                )
                """
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE runstats (
                    id INTEGER PRIMARY KEY,
                    video_id TEXT NOT NULL,
                    tokens_used INTEGER NOT NULL,
                    model TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
                """
            )

            assert run_migrations(connection) == 2
            assert run_migrations(connection) == 2

            version = connection.exec_driver_sql(
                "SELECT version FROM schema_version LIMIT 1"
            ).fetchone()
            video_columns = {
                row[1] for row in connection.exec_driver_sql("PRAGMA table_info(video)")
            }
            runstats_columns = {
                row[1]
                for row in connection.exec_driver_sql("PRAGMA table_info(runstats)")
            }
    finally:
        engine.dispose()

    assert version == (2,)
    assert "cached_at" in video_columns
    assert "prompt_tokens" in runstats_columns
    assert "generation_seconds" in runstats_columns
    engine.dispose()
