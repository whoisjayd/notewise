"""Integration coverage for OAuth token directory hardening."""

from __future__ import annotations

import os

import pytest

from notewise import config as config_module
from notewise.config import AppSettings as Config


@pytest.mark.integration
@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits only")
def test_oauth_token_dirs_enforce_mode_on_existing_permissive_dir(
    tmp_path, monkeypatch
):
    """A pre-existing permissive token dir gets its mode tightened to 0o700."""
    import stat

    state_dir = tmp_path / ".notewise"
    monkeypatch.setenv("NOTEWISE_HOME", str(state_dir))
    monkeypatch.delenv("CHATGPT_TOKEN_DIR", raising=False)
    monkeypatch.delenv("GITHUB_COPILOT_TOKEN_DIR", raising=False)

    chatgpt_dir = state_dir / "oauth" / "chatgpt"
    chatgpt_dir.mkdir(parents=True)
    chatgpt_dir.chmod(0o777)

    Config()

    assert stat.S_IMODE(chatgpt_dir.stat().st_mode) == 0o700


@pytest.mark.integration
def test_oauth_token_dirs_skip_symlinked_directory(tmp_path, monkeypatch, mocker):
    """Symlinked token dirs are skipped and their env var stays unset."""
    from notewise._constants import OAUTH_TOKEN_DIR_SYMLINK_SKIPPED_EVENT

    state_dir = tmp_path / ".notewise"
    victim_dir = tmp_path / "victim-tokens"
    victim_dir.mkdir()
    (state_dir / "oauth").mkdir(parents=True)
    chatgpt_link = state_dir / "oauth" / "chatgpt"
    try:
        chatgpt_link.symlink_to(victim_dir, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is not available on this platform")
    monkeypatch.setenv("NOTEWISE_HOME", str(state_dir))
    monkeypatch.delenv("CHATGPT_TOKEN_DIR", raising=False)
    monkeypatch.delenv("GITHUB_COPILOT_TOKEN_DIR", raising=False)
    warn = mocker.patch.object(config_module.logger, "warning")

    Config()

    warn.assert_called_once_with(
        OAUTH_TOKEN_DIR_SYMLINK_SKIPPED_EVENT,
        provider="chatgpt",
        token_dir=str(chatgpt_link),
    )
    assert "CHATGPT_TOKEN_DIR" not in os.environ
