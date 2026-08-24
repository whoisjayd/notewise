"""OAuth token persistence coverage for notewise's OAuth login flows.

Scope note (audit gap #4): notewise never reads, writes, or refreshes OAuth
token files itself. All token-file IO and expiry/refresh logic lives inside
LiteLLM; ``src/notewise/ui/oauth_flow.py`` only points LiteLLM at
NOTEWISE_HOME-derived directories by pre-creating them and exporting
``CHATGPT_TOKEN_DIR`` / ``GITHUB_COPILOT_TOKEN_DIR``
(``notewise/config.py::configure_oauth_token_storage``, lines 116-130).

import notewise.logging as logging_module
from notewise.llm.provider import summarize_provider_error
 from notewise.logging import configure_logging
     providers (exact path asserted via the exported env var + mkdir).
  2. Provider dirs are created when missing and reused non-destructively;
     the flow leaves no *.tmp artifacts behind.
  5. Failing flows render only redacted summarizer output and leak no secret
     substrings to rendered console output or the structlog session log.
  6. Explicit CHATGPT_TOKEN_DIR / GITHUB_COPILOT_TOKEN_DIR overrides are
     honored verbatim over the NOTEWISE_HOME-derived defaults.

Not pinnable at this layer (documented per the skip-gracefully clause):
audit behaviors #3 (refresh when stored expiry <= now) and #4 (reuse of a
valid unexpired token without refresh). oauth_flow.py has no token-expiry
or refresh code path — it awaits LiteLLM's aresponses/acompletion
unconditionally regardless of stored token state (oauth_flow.py:85-108), so
there is no notewise-side refresh function to assert against. Those
behaviors belong to LiteLLM's internal OAuth handling and would require
faking a litellm-internal contract that this repo does not own.
"""

from __future__ import annotations

import logging
import os
from unittest.mock import MagicMock

import pytest

import notewise.logging as logging_module
from notewise.llm.provider import summarize_provider_error
from notewise.logging import configure_logging
from notewise.ui.oauth_flow import run_oauth_login


TOKEN_DIR_ENV_VARS = {
    "chatgpt": "CHATGPT_TOKEN_DIR",
    "github_copilot": "GITHUB_COPILOT_TOKEN_DIR",
}


@pytest.fixture(autouse=True)
def _isolated_token_env(monkeypatch, tmp_path):
    """Point NOTEWISE_HOME at tmp_path and clear managed env overrides."""
    monkeypatch.setenv("NOTEWISE_HOME", str(tmp_path))
    for env_var in TOKEN_DIR_ENV_VARS.values():
        monkeypatch.delenv(env_var, raising=False)
    yield


def _mock_litellm(mocker):
    mocker.patch("litellm.aresponses", new_callable=mocker.AsyncMock)
    mocker.patch("litellm.acompletion", new_callable=mocker.AsyncMock)


@pytest.mark.parametrize("provider", ["chatgpt", "github_copilot"])
def test_default_token_dir_lands_under_notewise_home_provider_dir(
    tmp_path, provider, mocker
):
    """Each provider's token dir must be exactly <NOTEWISE_HOME>/oauth/<name>."""
    _mock_litellm(mocker)
    console = MagicMock()

    expected_dir = tmp_path / "oauth" / provider

    assert run_oauth_login(provider, console=console) is True

    assert expected_dir.is_dir(), "flow must pre-create the provider token dir"
    assert os.environ[TOKEN_DIR_ENV_VARS[provider]] == str(expected_dir)


@pytest.mark.parametrize("provider", ["chatgpt", "github_copilot"])
def test_missing_token_dirs_are_created_and_reused_without_tmp_artifacts(
    tmp_path, provider, mocker
):
    """Dirs appear on first run, survive re-runs untouched, no .tmp leftovers."""
    _mock_litellm(mocker)
    console = MagicMock()
    oauth_root = tmp_path / "oauth"
    provider_dir = oauth_root / provider
    marker = provider_dir / "existing-marker.txt"

    assert run_oauth_login(provider, console=console) is True
    assert provider_dir.is_dir()

    marker.write_text("keep me", encoding="utf-8")
    assert run_oauth_login(provider, console=console) is True

    # Reconfiguration must reuse the dir non-destructively (mkdir exist_ok).
    assert marker.read_text(encoding="utf-8") == "keep me"

    # notewise itself never writes token files, so its persistence step must
    # leave no temporary artifacts anywhere in the storage tree.
    tmp_files = list(oauth_root.rglob("*.tmp"))
    assert tmp_files == []


@pytest.mark.parametrize("provider", ["chatgpt", "github_copilot"])
def test_explicit_token_dir_overrides_honored_verbatim(
    tmp_path, monkeypatch, provider, mocker
):
    """User-set token dir env vars beat the NOTEWISE_HOME-derived default."""
    _mock_litellm(mocker)
    console = MagicMock()
    override_dir = tmp_path / f"custom-{provider}-tokens"
    override_dir.mkdir()
    monkeypatch.setenv(TOKEN_DIR_ENV_VARS[provider], str(override_dir))

    assert run_oauth_login(provider, console=console) is True

    assert os.environ[TOKEN_DIR_ENV_VARS[provider]] == str(override_dir)
    assert override_dir.is_dir()


@pytest.mark.parametrize("provider", ["chatgpt", "github_copilot"])
def test_failing_flow_leaks_no_secrets_to_console_or_logs(
    tmp_path, provider, mocker, caplog
):
    """Failure rendering must use redacted summarizer output only."""
    secret_token = "sk-oauth-persist-secret-9f2c4a"
    failing_error = RuntimeError(
        f"device auth failed api_key={secret_token} authorization=Bearer {secret_token}"
    )
    if provider == "chatgpt":
        mocker.patch(
            "litellm.aresponses",
            new_callable=mocker.AsyncMock,
            side_effect=failing_error,
        )
        mocker.patch("litellm.acompletion", new_callable=mocker.AsyncMock)
    else:
        mocker.patch(
            "litellm.acompletion",
            new_callable=mocker.AsyncMock,
            side_effect=failing_error,
        )
        mocker.patch("litellm.aresponses", new_callable=mocker.AsyncMock)

    summarizer_spy = mocker.patch(
        "notewise.ui.oauth_flow.summarize_provider_error",
        wraps=summarize_provider_error,
    )
    console = MagicMock()

    # Attach the project's structlog capture around the failing flow so any
    # logged record is observable in the session log file.
    logging_module._SESSION_LOG_PATH = None
    logging_module._LOGGING_CONFIGURED = False
    try:
        state_dir = tmp_path / "log-state"
        log_path = configure_logging(state_dir=state_dir)

        with caplog.at_level(logging.DEBUG):
            assert run_oauth_login(provider, console=console) is False

        rendered = "".join(str(call.args[0]) for call in console.print.call_args_list)
        assert "OAuth login failed" in rendered
        # The failure text must come from the redacted summarizer pipeline...
        summarizer_spy.assert_called_once()
        assert summarize_provider_error(failing_error) in rendered
        # ...and neither the raw error nor the secret survives anywhere.
        assert secret_token not in rendered
        assert "[REDACTED]" in rendered or "api_key" not in rendered

        if log_path is not None:
            log_text = log_path.read_text(encoding="utf-8")
            assert secret_token not in log_text
        for record in caplog.records:
            assert secret_token not in record.getMessage()
    finally:
        root_logger = logging_module.logging.getLogger()
        for handler in list(root_logger.handlers):
            handler.close()
        root_logger.handlers.clear()
        logging_module._SESSION_LOG_PATH = None
        logging_module._LOGGING_CONFIGURED = False
