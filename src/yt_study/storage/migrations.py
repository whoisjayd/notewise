"""Additive schema migrations for older SQLite cache files."""

from __future__ import annotations

from sqlalchemy import Connection
from sqlalchemy import inspect as sa_inspect


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


def repair_runstats_schema(connection: Connection) -> None:
    """Add newer RunStats columns to older SQLite cache files that predate them."""
    insp = sa_inspect(connection)
    if not insp.has_table("runstats"):
        return
    existing = {col["name"] for col in insp.get_columns("runstats")}
    for col_name, ddl in _RUNSTATS_ADDITIVE_COLUMNS.items():
        if col_name not in existing:
            connection.exec_driver_sql(ddl)
