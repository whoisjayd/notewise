"""Schema versioning and additive SQLite migrations for notewise."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import Connection
from sqlalchemy import inspect as sa_inspect


Migration = Callable[[Connection], None]
LATEST_SCHEMA_VERSION = 2

_RUNSTATS_ADDITIVE_COLUMNS: dict[str, str] = {
    "prompt_tokens": (
        "ALTER TABLE runstats ADD COLUMN prompt_tokens INTEGER NOT NULL DEFAULT 0"
    ),
    "completion_tokens": (
        "ALTER TABLE runstats ADD COLUMN completion_tokens INTEGER NOT NULL DEFAULT 0"
    ),
    "cost_usd": "ALTER TABLE runstats ADD COLUMN cost_usd FLOAT NOT NULL DEFAULT 0.0",
    "transcript_seconds": (
        "ALTER TABLE runstats ADD COLUMN transcript_seconds FLOAT NOT NULL DEFAULT 0.0"
    ),
    "generation_seconds": (
        "ALTER TABLE runstats ADD COLUMN generation_seconds FLOAT NOT NULL DEFAULT 0.0"
    ),
}


def _ensure_schema_version_table(connection: Connection) -> None:
    """Create the schema version table if it does not exist."""
    connection.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL
        )
        """
    )
    row = connection.exec_driver_sql(
        "SELECT version FROM schema_version LIMIT 1"
    ).fetchone()
    if row is None:
        connection.exec_driver_sql("INSERT INTO schema_version (version) VALUES (0)")


def _get_schema_version(connection: Connection) -> int:
    """Return the current schema version stored in SQLite."""
    _ensure_schema_version_table(connection)
    row = connection.exec_driver_sql(
        "SELECT version FROM schema_version LIMIT 1"
    ).fetchone()
    if row is None:
        return 0
    return int(row[0])


def _set_schema_version(connection: Connection, version: int) -> None:
    """Persist the latest applied schema version."""
    _ensure_schema_version_table(connection)
    connection.exec_driver_sql("UPDATE schema_version SET version = ?", (version,))


def _add_missing_columns(
    connection: Connection,
    table_name: str,
    columns: dict[str, str],
) -> None:
    """Apply additive column DDL only for columns that are still missing."""
    inspector = sa_inspect(connection)
    if not inspector.has_table(table_name):
        return
    existing = {col["name"] for col in inspector.get_columns(table_name)}
    for column_name, ddl in columns.items():
        if column_name not in existing:
            connection.exec_driver_sql(ddl)


def migration_1_add_runstats_columns(connection: Connection) -> None:
    """Backfill newer runstats metrics columns into older SQLite caches."""
    _add_missing_columns(connection, "runstats", _RUNSTATS_ADDITIVE_COLUMNS)


def migration_2_add_video_cached_at(connection: Connection) -> None:
    """Add the cached_at freshness timestamp to cached video rows."""
    inspector = sa_inspect(connection)
    if not inspector.has_table("video"):
        return
    existing = {col["name"] for col in inspector.get_columns("video")}
    if "cached_at" in existing:
        return

    default_timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    default_literal = default_timestamp.isoformat(sep=" ")
    connection.exec_driver_sql(
        "ALTER TABLE video ADD COLUMN cached_at DATETIME "
        f"NOT NULL DEFAULT '{default_literal}'"
    )


MIGRATIONS: tuple[tuple[int, Migration], ...] = (
    (1, migration_1_add_runstats_columns),
    (2, migration_2_add_video_cached_at),
)


def run_migrations(connection: Connection) -> int:
    """Run additive migrations in order and return the final schema version."""
    current_version = _get_schema_version(connection)
    for version, migration in MIGRATIONS:
        if version <= current_version:
            continue
        migration(connection)
        _set_schema_version(connection, version)
        current_version = version
    return current_version
