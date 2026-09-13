"""Atomic settings storage backed by SQLite (config.db).

This is intentionally separate from ``repository.py``'s ``DatabaseRepository``:
config.db holds durable user settings (API keys, defaults, custom endpoint
profiles), while cache.db holds prunable video/transcript/run-stats data that
`notewise cache clear/prune` operates on. Keeping them in different files
means clearing the cache can never touch a user's configuration.

Three tables, one per concern rather than one blob-shaped key-value store:
- ``settings``: generic scalar config keys (DEFAULT_MODEL, OUTPUT_DIR,
  TEMPERATURE, etc.).
- ``api_keys``: one row per provider API key (GEMINI_API_KEY,
  OPENAI_API_KEY, ...), keyed by the env-var name LiteLLM expects.
- ``custom_endpoints``: one row per saved OpenAI-compatible endpoint
  (name/base_url/api_key), instead of cramming a serialized profile list into
  a single settings value -- this lets `notewise inference add/update/delete`
  mutate one endpoint atomically without touching anything else.

This module uses the stdlib ``sqlite3`` directly rather than the SQLAlchemy
ORM used for the cache database: a handful of small tables touched
infrequently (CLI startup, `setup`/`config`/`inference` commands) don't need
engine pooling built for the cache DB's concurrent video-processing workload.
Every write happens in one transaction -- often started with ``BEGIN
IMMEDIATE`` to hold SQLite's write lock across a read-modify-write cycle --
which is what makes it atomic and race-free, unlike the old config.env
approach (a temp-file-plus-rename swap avoids a torn write, but not a lost
update between two concurrent writers).
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING

from notewise._constants import (
    CONFIG_API_KEY_ENV_KEYS,
    CONFIG_API_KEYS_TABLE_NAME,
    CONFIG_ENDPOINTS_TABLE_NAME,
    CONFIG_SETTINGS_TABLE_NAME,
    CUSTOM_LLM_ENDPOINTS_ENV_VAR,
)
from notewise.llm.custom_endpoint import (
    CustomEndpointProfile,
    parse_custom_endpoint_profiles,
    serialize_custom_endpoint_profiles,
)


if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


def _ensure_secure_db_file(db_path: Path) -> None:
    """Ensure db_path is an owner-only regular file, never a followed symlink.

    A planted symlink must never be followed -- sqlite3.connect() would
    happily open (and rewrite) whatever it points to, and the credentials in
    this database make that a real path-traversal/exposure risk, not just a
    correctness one. On POSIX, O_NOFOLLOW makes the initial open atomic
    against a symlink swap: if one is already there the open fails and we
    remove it and retry once, so there is no separate check-then-unlink
    window for an attacker to race. Windows has no O_NOFOLLOW; planting a
    symlink there already requires privileges this local-attacker model
    doesn't assume, so a plain check-then-create is an acceptable fallback.
    """
    flags = os.O_RDWR | os.O_CREAT
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(db_path, flags | nofollow, 0o600)
    except OSError:
        if not db_path.is_symlink():
            raise
        db_path.unlink()
        fd = os.open(db_path, flags | nofollow, 0o600)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
    finally:
        os.close(fd)


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        db_path.parent.chmod(0o700)
    _ensure_secure_db_file(db_path)
    connection = sqlite3.connect(db_path, timeout=30, isolation_level="DEFERRED")
    connection.execute(
        f"CREATE TABLE IF NOT EXISTS {CONFIG_SETTINGS_TABLE_NAME} "
        "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    connection.execute(
        f"CREATE TABLE IF NOT EXISTS {CONFIG_API_KEYS_TABLE_NAME} "
        "(provider TEXT PRIMARY KEY, api_key TEXT NOT NULL)"
    )
    connection.execute(
        f"CREATE TABLE IF NOT EXISTS {CONFIG_ENDPOINTS_TABLE_NAME} "
        "(name TEXT PRIMARY KEY, base_url TEXT NOT NULL, api_key TEXT NOT NULL)"
    )
    return connection


def _select_endpoint_profiles(
    connection: sqlite3.Connection,
) -> tuple[CustomEndpointProfile, ...]:
    rows = connection.execute(
        f"SELECT name, base_url, api_key FROM {CONFIG_ENDPOINTS_TABLE_NAME} "  # nosec B608 -- table name is a module constant, not user input
        "ORDER BY rowid"
    ).fetchall()
    return tuple(
        CustomEndpointProfile(name=name, base_url=base_url, api_key=api_key)
        for name, base_url, api_key in rows
    )


def config_db_is_empty(db_path: Path) -> bool:
    """Return whether config.db has no stored settings, keys, or endpoints yet."""
    if not db_path.exists():
        return True
    with closing(_connect(db_path)) as connection:
        for table_name in (
            CONFIG_SETTINGS_TABLE_NAME,
            CONFIG_API_KEYS_TABLE_NAME,
            CONFIG_ENDPOINTS_TABLE_NAME,
        ):
            if connection.execute(f"SELECT 1 FROM {table_name} LIMIT 1").fetchone():  # nosec B608 -- table name is a module constant, not user input
                return False
    return True


def _read_merged_config(connection: sqlite3.Connection) -> dict[str, str]:
    """Read the merged settings view within the caller's open transaction."""
    values = dict(
        connection.execute(
            f"SELECT key, value FROM {CONFIG_SETTINGS_TABLE_NAME}"  # nosec B608 -- table name is a module constant, not user input
        ).fetchall()
    )
    values.update(
        connection.execute(
            f"SELECT provider, api_key FROM {CONFIG_API_KEYS_TABLE_NAME}"  # nosec B608 -- table name is a module constant, not user input
        ).fetchall()
    )
    profiles = _select_endpoint_profiles(connection)
    if profiles:
        values[CUSTOM_LLM_ENDPOINTS_ENV_VAR] = serialize_custom_endpoint_profiles(
            profiles
        )
    return values


def load_config_db(db_path: Path) -> dict[str, str]:
    """Return the merged settings view: scalar keys, provider API keys, and a
    synthesized ``CUSTOM_LLM_ENDPOINTS`` value when any endpoints are saved.
    """
    if not db_path.exists():
        return {}
    with closing(_connect(db_path)) as connection:
        # A single explicit read transaction gives a consistent point-in-time
        # snapshot across all three tables; without it, each SELECT below
        # would run in its own autocommit-style view (isolation_level is
        # DEFERRED, which only opens a transaction before DML, not SELECT),
        # so a concurrent writer committing between queries could produce a
        # torn merge of old and new state.
        connection.execute("BEGIN")
        try:
            return _read_merged_config(connection)
        finally:
            connection.rollback()


def list_custom_endpoints(db_path: Path) -> tuple[CustomEndpointProfile, ...]:
    """Return all saved custom endpoint profiles."""
    if not db_path.exists():
        return ()
    with closing(_connect(db_path)) as connection:
        return _select_endpoint_profiles(connection)


def upsert_custom_endpoint(db_path: Path, profile: CustomEndpointProfile) -> None:
    """Atomically insert or replace one saved custom endpoint."""
    with closing(_connect(db_path)) as connection, connection:
        connection.execute(
            f"INSERT INTO {CONFIG_ENDPOINTS_TABLE_NAME} (name, base_url, api_key) "  # nosec B608 -- table name is a module constant, not user input
            "VALUES (?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET base_url = excluded.base_url, "
            "api_key = excluded.api_key",
            (profile.name, profile.base_url, profile.api_key),
        )


def delete_custom_endpoint(db_path: Path, name: str) -> bool:
    """Atomically remove one saved custom endpoint. Returns whether it existed."""
    with closing(_connect(db_path)) as connection, connection:
        cursor = connection.execute(
            f"DELETE FROM {CONFIG_ENDPOINTS_TABLE_NAME} WHERE name = ?",  # nosec B608 -- table name is a module constant, not user input
            (name,),
        )
        return cursor.rowcount > 0


def list_api_keys(db_path: Path) -> dict[str, str]:
    """Return all saved provider API keys, keyed by env-var name."""
    if not db_path.exists():
        return {}
    with closing(_connect(db_path)) as connection:
        return dict(
            connection.execute(
                f"SELECT provider, api_key FROM {CONFIG_API_KEYS_TABLE_NAME}"  # nosec B608 -- table name is a module constant, not user input
            ).fetchall()
        )


def set_api_key(db_path: Path, provider: str, api_key: str) -> None:
    """Atomically insert or replace one provider's API key."""
    with closing(_connect(db_path)) as connection, connection:
        connection.execute(
            f"INSERT INTO {CONFIG_API_KEYS_TABLE_NAME} (provider, api_key) "  # nosec B608 -- table name is a module constant, not user input
            "VALUES (?, ?) "
            "ON CONFLICT(provider) DO UPDATE SET api_key = excluded.api_key",
            (provider, api_key),
        )


def delete_api_key(db_path: Path, provider: str) -> bool:
    """Atomically remove one provider's saved API key. Returns whether it existed."""
    with closing(_connect(db_path)) as connection, connection:
        cursor = connection.execute(
            f"DELETE FROM {CONFIG_API_KEYS_TABLE_NAME} WHERE provider = ?",  # nosec B608 -- table name is a module constant, not user input
            (provider,),
        )
        return cursor.rowcount > 0


def _classify_key(key: str) -> str:
    """Return which table a config key belongs in.

    Single source of truth for the "endpoints vs. api_keys vs. settings"
    routing rule, shared by :func:`replace_config_db`,
    :func:`remove_config_key`, and :func:`update_config_db` so a future 4th
    table only needs this one place updated.
    """
    if key == CUSTOM_LLM_ENDPOINTS_ENV_VAR:
        return CONFIG_ENDPOINTS_TABLE_NAME
    if key in CONFIG_API_KEY_ENV_KEYS:
        return CONFIG_API_KEYS_TABLE_NAME
    return CONFIG_SETTINGS_TABLE_NAME


def _partition_by_table(
    values: dict[str, str],
) -> tuple[dict[str, str], dict[str, str], str | None]:
    """Split a flat config dict into (scalar_values, api_key_values, endpoints)."""
    api_key_values: dict[str, str] = {}
    scalar_values: dict[str, str] = {}
    for key, value in values.items():
        table = _classify_key(key)
        if table == CONFIG_API_KEYS_TABLE_NAME:
            api_key_values[key] = value
        elif table == CONFIG_SETTINGS_TABLE_NAME:
            scalar_values[key] = value
    return scalar_values, api_key_values, values.get(CUSTOM_LLM_ENDPOINTS_ENV_VAR)


def _replace_config_locked(
    connection: sqlite3.Connection, values: dict[str, str]
) -> None:
    """Replace the stored config within the caller's open transaction."""
    scalar_values, api_key_values, endpoints_value = _partition_by_table(values)
    profiles = (
        parse_custom_endpoint_profiles(endpoints_value) if endpoints_value else ()
    )

    connection.execute(f"DELETE FROM {CONFIG_SETTINGS_TABLE_NAME}")  # nosec B608 -- table name is a module constant, not user input
    connection.executemany(
        f"INSERT INTO {CONFIG_SETTINGS_TABLE_NAME} (key, value) VALUES (?, ?)",  # nosec B608 -- table name is a module constant, not user input
        scalar_values.items(),
    )
    connection.execute(f"DELETE FROM {CONFIG_API_KEYS_TABLE_NAME}")  # nosec B608 -- table name is a module constant, not user input
    connection.executemany(
        f"INSERT INTO {CONFIG_API_KEYS_TABLE_NAME} (provider, api_key) "  # nosec B608 -- table name is a module constant, not user input
        "VALUES (?, ?)",
        api_key_values.items(),
    )
    connection.execute(f"DELETE FROM {CONFIG_ENDPOINTS_TABLE_NAME}")  # nosec B608 -- table name is a module constant, not user input
    connection.executemany(
        f"INSERT INTO {CONFIG_ENDPOINTS_TABLE_NAME} "  # nosec B608 -- table name is a module constant, not user input
        "(name, base_url, api_key) VALUES (?, ?, ?)",
        [(p.name, p.base_url, p.api_key) for p in profiles],
    )


def replace_config_db(db_path: Path, values: dict[str, str]) -> None:
    """Atomically replace the entire stored config with ``values``.

    Unlike :func:`update_config_db`, keys absent from ``values`` are removed
    rather than preserved -- this is what `notewise edit-config` needs, since
    a line deleted in the editor should delete that setting.
    """
    with closing(_connect(db_path)) as connection, connection:
        _replace_config_locked(connection, values)


def compare_and_replace_config_db(
    db_path: Path, expected: dict[str, str], values: dict[str, str]
) -> bool:
    """Atomically replace the stored config with ``values`` iff it still
    equals ``expected``. Returns whether the replacement happened.

    `edit-config` loads the current config, waits on an external editor that
    can stay open for minutes, then must recheck nothing else committed in
    the meantime before overwriting -- otherwise it would silently discard a
    concurrent `config set`/`inference add`. Doing the compare and the
    replace inside one ``BEGIN IMMEDIATE`` transaction (rather than a
    separate read-then-write pair, however carefully app-level-compared)
    closes the window where another process commits between the two.
    """
    connection = _connect(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        if _read_merged_config(connection) != expected:
            connection.rollback()
            return False
        _replace_config_locked(connection, values)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
    return True


def remove_config_key(db_path: Path, key: str) -> bool:
    """Atomically remove one key, whichever table it lives in.

    Returns whether the key existed. A single-row DELETE against the right
    table is what `notewise config unset` needs -- unlike a
    load-mutate-:func:`replace_config_db` round trip, this never risks
    clobbering a concurrent writer's unrelated change.
    """
    table = _classify_key(key)
    if table == CONFIG_ENDPOINTS_TABLE_NAME:
        with closing(_connect(db_path)) as connection, connection:
            cursor = connection.execute(f"DELETE FROM {CONFIG_ENDPOINTS_TABLE_NAME}")  # nosec B608 -- table name is a module constant, not user input
            return cursor.rowcount > 0
    if table == CONFIG_API_KEYS_TABLE_NAME:
        return delete_api_key(db_path, key)
    with closing(_connect(db_path)) as connection, connection:
        cursor = connection.execute(
            f"DELETE FROM {CONFIG_SETTINGS_TABLE_NAME} WHERE key = ?",  # nosec B608 -- table name is a module constant, not user input
            (key,),
        )
        return cursor.rowcount > 0


def update_config_db(
    db_path: Path,
    updates: dict[str, str],
    *,
    drop_keys: Iterable[str] = (),
) -> dict[str, str]:
    """Atomically merge ``updates`` into stored settings and return the result.

    ``CUSTOM_LLM_ENDPOINTS`` in ``updates`` is parsed and replaces the full
    ``custom_endpoints`` table; keys in ``CONFIG_API_KEY_ENV_KEYS`` are routed
    to the ``api_keys`` table; everything else merges into ``settings``. All
    of it happens in one transaction (``BEGIN IMMEDIATE``), so two concurrent
    callers -- e.g. two `notewise inference add` invocations, or a `setup`
    run racing a manual `config set` -- cannot silently clobber each other's
    change.
    """
    scalar_updates, api_key_updates, endpoints_update = _partition_by_table(updates)

    connection = _connect(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        current = dict(
            connection.execute(
                f"SELECT key, value FROM {CONFIG_SETTINGS_TABLE_NAME}"  # nosec B608 -- table name is a module constant, not user input
            ).fetchall()
        )
        current.update(scalar_updates)
        for key in drop_keys:
            current.pop(key, None)
        connection.execute(f"DELETE FROM {CONFIG_SETTINGS_TABLE_NAME}")  # nosec B608 -- table name is a module constant, not user input
        connection.executemany(
            f"INSERT INTO {CONFIG_SETTINGS_TABLE_NAME} (key, value) VALUES (?, ?)",  # nosec B608 -- table name is a module constant, not user input
            current.items(),
        )

        for provider, api_key in api_key_updates.items():
            connection.execute(
                f"INSERT INTO {CONFIG_API_KEYS_TABLE_NAME} (provider, api_key) "  # nosec B608 -- table name is a module constant, not user input
                "VALUES (?, ?) "
                "ON CONFLICT(provider) DO UPDATE SET api_key = excluded.api_key",
                (provider, api_key),
            )
        current_api_keys = dict(
            connection.execute(
                f"SELECT provider, api_key FROM {CONFIG_API_KEYS_TABLE_NAME}"  # nosec B608 -- table name is a module constant, not user input
            ).fetchall()
        )

        if endpoints_update is not None:
            profiles = parse_custom_endpoint_profiles(endpoints_update)
            connection.execute(f"DELETE FROM {CONFIG_ENDPOINTS_TABLE_NAME}")  # nosec B608 -- table name is a module constant, not user input
            connection.executemany(
                f"INSERT INTO {CONFIG_ENDPOINTS_TABLE_NAME} "  # nosec B608 -- table name is a module constant, not user input
                "(name, base_url, api_key) VALUES (?, ?, ?)",
                [(p.name, p.base_url, p.api_key) for p in profiles],
            )
        profiles = _select_endpoint_profiles(connection)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()

    current.update(current_api_keys)
    if profiles:
        current[CUSTOM_LLM_ENDPOINTS_ENV_VAR] = serialize_custom_endpoint_profiles(
            profiles
        )
    return current
