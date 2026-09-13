"""Tests for the SQLite-backed config store (config.db)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from notewise.llm.custom_endpoint import CustomEndpointProfile
from notewise.storage import config_store


def test_config_db_is_empty_when_no_file(tmp_path):
    db_path = tmp_path / "config.db"

    assert config_store.config_db_is_empty(db_path)
    assert config_store.load_config_db(db_path) == {}


def test_update_config_db_merges_and_drops_legacy_keys(tmp_path):
    db_path = tmp_path / "config.db"

    config_store.update_config_db(db_path, {"DEFAULT_MODEL": "a", "KEEP_ME": "1"})
    config_store.update_config_db(
        db_path,
        {"DEFAULT_MODEL": "b", "DROP_ME": "x"},
        drop_keys=frozenset({"DROP_ME"}),
    )

    result = config_store.load_config_db(db_path)
    assert result["DEFAULT_MODEL"] == "b"
    assert result["KEEP_ME"] == "1"
    assert "DROP_ME" not in result
    assert not config_store.config_db_is_empty(db_path)


def test_update_config_db_routes_api_keys_to_their_own_table(tmp_path):
    db_path = tmp_path / "config.db"

    config_store.update_config_db(
        db_path, {"DEFAULT_MODEL": "x", "GEMINI_API_KEY": "gk-123"}
    )

    merged = config_store.load_config_db(db_path)
    assert merged["GEMINI_API_KEY"] == "gk-123"
    assert config_store.list_api_keys(db_path) == {"GEMINI_API_KEY": "gk-123"}


def test_update_config_db_replaces_full_endpoint_registry(tmp_path):
    db_path = tmp_path / "config.db"
    profile = CustomEndpointProfile(
        name="office", base_url="https://office.example/v1", api_key="old"
    )
    config_store.upsert_custom_endpoint(db_path, profile)

    config_store.update_config_db(
        db_path,
        {
            "CUSTOM_LLM_ENDPOINTS": (
                '[{"name":"home","base_url":"https://home.example/v1","api_key":"new"}]'
            )
        },
    )

    endpoints = config_store.list_custom_endpoints(db_path)
    assert endpoints == (
        CustomEndpointProfile(
            name="home", base_url="https://home.example/v1", api_key="new"
        ),
    )


def test_upsert_and_delete_custom_endpoint(tmp_path):
    db_path = tmp_path / "config.db"
    profile = CustomEndpointProfile(
        name="office", base_url="https://office.example/v1", api_key="secret"
    )

    config_store.upsert_custom_endpoint(db_path, profile)
    assert config_store.list_custom_endpoints(db_path) == (profile,)

    replacement = CustomEndpointProfile(
        name="office", base_url="https://new.example/v1", api_key="new-secret"
    )
    config_store.upsert_custom_endpoint(db_path, replacement)
    assert config_store.list_custom_endpoints(db_path) == (replacement,)

    assert config_store.delete_custom_endpoint(db_path, "office") is True
    assert config_store.delete_custom_endpoint(db_path, "office") is False
    assert config_store.list_custom_endpoints(db_path) == ()


def test_set_and_delete_api_key(tmp_path):
    db_path = tmp_path / "config.db"

    config_store.set_api_key(db_path, "GEMINI_API_KEY", "first")
    config_store.set_api_key(db_path, "GEMINI_API_KEY", "second")
    assert config_store.list_api_keys(db_path) == {"GEMINI_API_KEY": "second"}

    assert config_store.delete_api_key(db_path, "GEMINI_API_KEY") is True
    assert config_store.delete_api_key(db_path, "GEMINI_API_KEY") is False


def test_replace_config_db_drops_omitted_keys(tmp_path):
    db_path = tmp_path / "config.db"
    config_store.update_config_db(
        db_path,
        {"DEFAULT_MODEL": "a", "GEMINI_API_KEY": "gk-1"},
    )
    config_store.upsert_custom_endpoint(
        db_path,
        CustomEndpointProfile(name="ep", base_url="https://x.test/v1", api_key="k"),
    )

    config_store.replace_config_db(db_path, {"DEFAULT_MODEL": "b"})

    result = config_store.load_config_db(db_path)
    assert result == {"DEFAULT_MODEL": "b"}
    assert config_store.list_api_keys(db_path) == {}
    assert config_store.list_custom_endpoints(db_path) == ()


def test_remove_config_key_routes_to_settings_table(tmp_path):
    db_path = tmp_path / "config.db"
    config_store.update_config_db(db_path, {"DEFAULT_MODEL": "a"})

    assert config_store.remove_config_key(db_path, "DEFAULT_MODEL") is True
    assert config_store.remove_config_key(db_path, "DEFAULT_MODEL") is False
    assert "DEFAULT_MODEL" not in config_store.load_config_db(db_path)


def test_remove_config_key_routes_to_api_keys_table(tmp_path):
    db_path = tmp_path / "config.db"
    config_store.set_api_key(db_path, "GEMINI_API_KEY", "gk-1")

    assert config_store.remove_config_key(db_path, "GEMINI_API_KEY") is True
    assert config_store.list_api_keys(db_path) == {}


def test_remove_config_key_routes_to_endpoints_table(tmp_path):
    db_path = tmp_path / "config.db"
    config_store.upsert_custom_endpoint(
        db_path,
        CustomEndpointProfile(name="ep", base_url="https://x.test/v1", api_key="k"),
    )

    assert config_store.remove_config_key(db_path, "CUSTOM_LLM_ENDPOINTS") is True
    assert config_store.list_custom_endpoints(db_path) == ()


def test_remove_config_key_leaves_unrelated_keys_intact(tmp_path):
    """A single-key removal must not disturb any other stored value."""
    db_path = tmp_path / "config.db"
    config_store.update_config_db(
        db_path,
        {"DEFAULT_MODEL": "a", "GEMINI_API_KEY": "gk-1"},
    )
    config_store.upsert_custom_endpoint(
        db_path,
        CustomEndpointProfile(name="ep", base_url="https://x.test/v1", api_key="k"),
    )

    config_store.remove_config_key(db_path, "DEFAULT_MODEL")

    result = config_store.load_config_db(db_path)
    assert "DEFAULT_MODEL" not in result
    assert result["GEMINI_API_KEY"] == "gk-1"
    assert config_store.list_custom_endpoints(db_path) != ()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits only")
def test_connect_creates_owner_only_directory_and_file(tmp_path):
    """Credentials in config.db must not be group/world-readable, even under
    a permissive umask.
    """
    db_path = tmp_path / "state" / "config.db"
    previous_umask = os.umask(0)
    try:
        config_store.update_config_db(db_path, {"DEFAULT_MODEL": "a"})
    finally:
        os.umask(previous_umask)

    dir_mode = stat.S_IMODE(db_path.parent.stat().st_mode)
    file_mode = stat.S_IMODE(db_path.stat().st_mode)
    assert dir_mode == 0o700
    assert file_mode == 0o600


@pytest.mark.skipif(os.name == "nt", reason="symlink creation is not available")
def test_connect_replaces_a_symlink_swapped_in_after_unlink(tmp_path, monkeypatch):
    """A symlink planted back into db_path's slot during the retry-open must
    not be silently followed either.
    """
    victim = tmp_path / "victim.env"
    victim.write_text("VICTIM=keep-me\n", encoding="utf-8")
    db_path = tmp_path / "state" / "config.db"
    db_path.parent.mkdir(parents=True)
    db_path.symlink_to(victim)

    real_unlink = Path.unlink

    def swap_and_unlink(self: Path, *args: object, **kwargs: object) -> None:
        real_unlink(self, *args, **kwargs)
        self.symlink_to(victim)

    monkeypatch.setattr(Path, "unlink", swap_and_unlink)

    with pytest.raises(OSError):
        config_store.update_config_db(db_path, {"DEFAULT_MODEL": "a"})

    assert victim.read_text(encoding="utf-8") == "VICTIM=keep-me\n"


def test_compare_and_replace_config_db_replaces_on_match(tmp_path):
    db_path = tmp_path / "config.db"
    config_store.update_config_db(db_path, {"DEFAULT_MODEL": "a"})
    snapshot = config_store.load_config_db(db_path)

    replaced = config_store.compare_and_replace_config_db(
        db_path, snapshot, {"DEFAULT_MODEL": "b"}
    )

    assert replaced is True
    assert config_store.load_config_db(db_path) == {"DEFAULT_MODEL": "b"}


def test_compare_and_replace_config_db_aborts_on_concurrent_change(tmp_path):
    """A snapshot taken before a concurrent writer commits must not be used
    to blindly overwrite that writer's change.
    """
    db_path = tmp_path / "config.db"
    config_store.update_config_db(db_path, {"DEFAULT_MODEL": "a"})
    stale_snapshot = config_store.load_config_db(db_path)

    config_store.update_config_db(db_path, {"MAX_TOKENS": "500"})

    replaced = config_store.compare_and_replace_config_db(
        db_path, stale_snapshot, {"DEFAULT_MODEL": "b"}
    )

    assert replaced is False
    current = config_store.load_config_db(db_path)
    assert current["DEFAULT_MODEL"] == "a"
    assert current["MAX_TOKENS"] == "500"
