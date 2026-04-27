"""Tests for OAuth/device-flow helper behavior."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

from notewise.ui.oauth_flow import run_oauth_login


def test_run_oauth_login_triggers_litellm_responses_call():
    """OAuth login should make one tiny LiteLLM request for the provider."""
    console = MagicMock()
    with patch("litellm.aresponses", new_callable=AsyncMock) as responses:
        assert run_oauth_login("chatgpt", console=console) is True

    responses.assert_awaited_once()
    assert responses.await_args is not None
    kwargs = responses.await_args.kwargs
    assert kwargs["model"] == "chatgpt/gpt-5.3-codex"
    assert kwargs["input"] == [{"role": "user", "content": "Reply with OK."}]
    assert kwargs["max_output_tokens"] == 4


def test_run_oauth_login_uses_chat_completion_safe_model_for_copilot():
    """GitHub Copilot login should avoid Codex models that may have no quota."""
    console = MagicMock()
    with (
        patch("litellm.acompletion", new_callable=AsyncMock) as completion,
        patch("litellm.aresponses", new_callable=AsyncMock) as responses,
    ):
        assert run_oauth_login("github_copilot", console=console) is True

    responses.assert_not_awaited()
    completion.assert_awaited_once()
    assert completion.await_args is not None
    kwargs = completion.await_args.kwargs
    assert kwargs["model"] == "github_copilot/gpt-5-mini"
    assert kwargs["messages"] == [
        {"role": "system", "content": "You are validating OAuth login for notewise."},
        {"role": "user", "content": "Reply with OK."},
    ]
    assert kwargs["max_tokens"] == 4


def test_run_oauth_login_defaults_token_dir_to_notewise_home(tmp_path, monkeypatch):
    """The standalone auth command should store OAuth tokens under .notewise."""
    state_dir = tmp_path / ".notewise"
    monkeypatch.setenv("NOTEWISE_HOME", str(state_dir))
    monkeypatch.delenv("CHATGPT_TOKEN_DIR", raising=False)
    console = MagicMock()

    with patch("litellm.aresponses", new_callable=AsyncMock):
        assert run_oauth_login("chatgpt", console=console) is True

    assert os.environ["CHATGPT_TOKEN_DIR"] == str(state_dir / "oauth" / "chatgpt")


def test_run_oauth_login_reports_failure_without_raising():
    """OAuth login failures should be returned to callers as a false result."""
    console = MagicMock()
    with patch(
        "litellm.acompletion",
        new_callable=AsyncMock,
        side_effect=RuntimeError("device auth failed"),
    ):
        assert run_oauth_login("github_copilot", console=console) is False

    rendered = "".join(str(call.args[0]) for call in console.print.call_args_list)
    assert "OAuth login failed" in rendered
    assert "device auth failed" in rendered
