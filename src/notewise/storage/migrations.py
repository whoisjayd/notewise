"""Schema versioning and additive SQLite migrations for notewise."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import Connection
from sqlalchemy import inspect as sa_inspect

from notewise._constants import (
    CACHED_AT_COLUMN_DDL_TEMPLATE,
    CACHED_AT_COLUMN_NAME,
    LATEST_SCHEMA_VERSION,
    NORMALIZE_CACHED_AT_SQL,
    VIDEO_CACHE_TABLE_NAME,
)


Migration = Callable[[Connection], None]

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
    if not inspector.has_table(VIDEO_CACHE_TABLE_NAME):
        return
    existing = {col["name"] for col in inspector.get_columns(VIDEO_CACHE_TABLE_NAME)}
    if CACHED_AT_COLUMN_NAME in existing:
        return

    # SQLAlchemy's SQLite DATETIME round-trips naive 'YYYY-MM-DD HH:MM:SS'
    # strings only; an ISO '+00:00' suffix would be unreadable on the way out.
    default_timestamp = datetime.now(UTC).replace(microsecond=0, tzinfo=None)
    default_literal = default_timestamp.isoformat(sep=" ")
    connection.exec_driver_sql(
        CACHED_AT_COLUMN_DDL_TEMPLATE.format(default_literal=default_literal)
    )


def migration_3_normalize_cached_at_literals(connection: Connection) -> None:
    """Repair cached_at rows backfilled with an ISO '+00:00' suffix.

    Older releases generated ``DEFAULT 'YYYY-MM-DD HH:MM:SS+00:00'`` literals
    that SQLAlchemy's SQLite DATETIME type cannot parse on read. The suffix is
    always UTC (the only value ever emitted), so stripping it recovers the
    exact naive timestamp the ORM expects.
    """
    inspector = sa_inspect(connection)
    if not inspector.has_table(VIDEO_CACHE_TABLE_NAME):
        return
    existing = {col["name"] for col in inspector.get_columns(VIDEO_CACHE_TABLE_NAME)}
    if CACHED_AT_COLUMN_NAME not in existing:
        return
    connection.exec_driver_sql(NORMALIZE_CACHED_AT_SQL)


MIGRATIONS: tuple[tuple[int, Migration], ...] = (
    (1, migration_1_add_runstats_columns),
    (2, migration_2_add_video_cached_at),
    (LATEST_SCHEMA_VERSION, migration_3_normalize_cached_at_literals),
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
