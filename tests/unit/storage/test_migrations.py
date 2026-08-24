"""Unit tests for schema versioned SQLite migrations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from notewise.storage.migrations import run_migrations
from notewise.storage.models import VideoRecord


LATEST_SCHEMA_VERSION = 3


def _create_legacy_schema(connection) -> None:
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


def test_run_migrations_is_idempotent_and_reaches_latest_schema(tmp_path):
    """Running migrations repeatedly should settle at the latest version."""
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    try:
        with engine.begin() as connection:
            _create_legacy_schema(connection)

            assert run_migrations(connection) == LATEST_SCHEMA_VERSION
            assert run_migrations(connection) == LATEST_SCHEMA_VERSION

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

    assert version == (LATEST_SCHEMA_VERSION,)
    assert "cached_at" in video_columns
    assert "prompt_tokens" in runstats_columns
    assert "generation_seconds" in runstats_columns


def test_backfilled_cached_at_is_readable_via_orm_roundtrip(tmp_path):
    """The migration_2 DEFAULT literal must round-trip through the ORM."""
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    try:
        with engine.begin() as connection:
            _create_legacy_schema(connection)
            connection.exec_driver_sql(
                "INSERT INTO video (id, title, duration) VALUES ('vid1', 'One', 10)"
            )

            assert run_migrations(connection) == LATEST_SCHEMA_VERSION

            raw = connection.exec_driver_sql(
                "SELECT cached_at FROM video WHERE id = 'vid1'"
            ).fetchone()[0]

        with Session(engine) as session:
            record = session.execute(
                select(VideoRecord).where(VideoRecord.id == "vid1")
            ).scalar_one()
            cached_at = record.cached_at
    finally:
        engine.dispose()

    assert isinstance(raw, str)
    assert not raw.endswith("+00:00")
    assert isinstance(cached_at, datetime)
    assert cached_at.tzinfo is None


def test_migration_3_repairs_legacy_utc_suffixed_rows(tmp_path):
    """Rows backfilled by older releases with '+00:00' literals are repaired."""
    engine = create_engine(f"sqlite:///{tmp_path / 'broken.db'}")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE video (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    duration INTEGER NOT NULL,
                    cached_at DATETIME NOT NULL DEFAULT '2020-01-01 00:00:00+00:00'
                )
                """
            )
            connection.exec_driver_sql(
                "INSERT INTO video (id, title, duration) VALUES ('vid1', 'One', 10)"
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE schema_version (version INTEGER NOT NULL)
                """
            )
            connection.exec_driver_sql(
                "INSERT INTO schema_version (version) VALUES (2)"
            )

            assert run_migrations(connection) == LATEST_SCHEMA_VERSION

            raw = connection.exec_driver_sql(
                "SELECT cached_at FROM video WHERE id = 'vid1'"
            ).fetchone()[0]

        with Session(engine) as session:
            record = session.execute(
                select(VideoRecord).where(VideoRecord.id == "vid1")
            ).scalar_one()
            cached_at = record.cached_at
    finally:
        engine.dispose()

    assert raw == "2020-01-01 00:00:00"
    assert cached_at == datetime(2020, 1, 1, 0, 0, 0)


def test_migrate_then_re_migrate_keeps_version_stable_and_rows_readable(tmp_path):
    """A migrate -> re-migrate cycle must not rewrite or corrupt cached_at."""
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    try:
        with engine.begin() as connection:
            _create_legacy_schema(connection)
            connection.exec_driver_sql(
                "INSERT INTO video (id, title, duration) VALUES ('vid1', 'One', 10)"
            )

            first_version = run_migrations(connection)
            first_raw = connection.exec_driver_sql(
                "SELECT cached_at FROM video WHERE id = 'vid1'"
            ).fetchone()[0]

            second_version = run_migrations(connection)
            second_raw = connection.exec_driver_sql(
                "SELECT cached_at FROM video WHERE id = 'vid1'"
            ).fetchone()[0]

        with Session(engine) as session:
            record = session.execute(
                select(VideoRecord).where(VideoRecord.id == "vid1")
            ).scalar_one()
            cached_at = record.cached_at
    finally:
        engine.dispose()

    assert first_version == LATEST_SCHEMA_VERSION
    assert second_version == LATEST_SCHEMA_VERSION
    assert first_raw == second_raw
    assert isinstance(cached_at, datetime)
    age = datetime.now(UTC).replace(tzinfo=None) - cached_at
    assert timedelta(0) <= age < timedelta(days=1)
