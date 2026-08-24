"""Integration coverage for setup_wizard filesystem security behavior."""

from __future__ import annotations

import pytest

from notewise.ui.setup_wizard import get_config_path, save_config


def test_save_config_does_not_truncate_symlink_target(tmp_path, monkeypatch):
    """save_config must swap a planted symlink, not truncate its victim."""
    monkeypatch.setenv("NOTEWISE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv("DEFAULT_MODEL", raising=False)

    victim = tmp_path / "victim.env"
    victim.write_text("VICTIM=keep-me\n", encoding="utf-8")
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        config_path.symlink_to(victim)
    except OSError:
        pytest.skip("symlink creation is not available on this platform")

    save_config({"DEFAULT_MODEL": "gemini/gemini-2.5-flash"})

    assert victim.read_text(encoding="utf-8") == "VICTIM=keep-me\n"
    assert "DEFAULT_MODEL=gemini/gemini-2.5-flash" in config_path.read_text(
        encoding="utf-8"
    )
    assert config_path.is_symlink() is False
