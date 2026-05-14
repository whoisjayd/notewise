"""Tests for OAuth/device-flow helper behavior."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

from notewise._constants import LLM_PAYLOAD_ERROR_SUMMARY
from notewise.ui.oauth_flow import run_oauth_login


def test_run_oauth_login_triggers_litellm_responses_call(mocker):
    """OAuth login should make one tiny LiteLLM request for the provider."""
    console = MagicMock()
    responses = mocker.patch("litellm.aresponses", new_callable=mocker.AsyncMock)
    completion = mocker.patch("litellm.acompletion", new_callable=mocker.AsyncMock)

    assert run_oauth_login("chatgpt", console=console) is True

    responses.assert_awaited_once()
    completion.assert_not_awaited()
    assert responses.await_args is not None
    kwargs = responses.await_args.kwargs
    assert kwargs["model"] == "chatgpt/gpt-5.2"
    assert kwargs["input"] == [{"role": "user", "content": "Reply with OK."}]
    assert kwargs["max_output_tokens"] == 4


def test_run_oauth_login_uses_chat_completion_safe_model_for_copilot(mocker):
    """GitHub Copilot login should avoid Codex models that may have no quota."""
    console = MagicMock()
    completion = mocker.patch("litellm.acompletion", new_callable=mocker.AsyncMock)
    responses = mocker.patch("litellm.aresponses", new_callable=mocker.AsyncMock)

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


def test_run_oauth_login_defaults_token_dir_to_notewise_home(
    tmp_path,
    monkeypatch,
    mocker,
):
    """The standalone auth command should store OAuth tokens under .notewise."""
    state_dir = tmp_path / ".notewise"
    monkeypatch.setenv("NOTEWISE_HOME", str(state_dir))
    monkeypatch.delenv("CHATGPT_TOKEN_DIR", raising=False)
    console = MagicMock()

    mocker.patch("litellm.aresponses", new_callable=mocker.AsyncMock)
    mocker.patch("litellm.acompletion", new_callable=mocker.AsyncMock)

    assert run_oauth_login("chatgpt", console=console) is True

    assert os.environ["CHATGPT_TOKEN_DIR"] == str(state_dir / "oauth" / "chatgpt")


def test_run_oauth_login_reports_failure_without_raising(mocker):
    """OAuth login failures should be returned to callers as a false result."""
    console = MagicMock()
    completion = mocker.patch(
        "litellm.acompletion",
        new_callable=mocker.AsyncMock,
        side_effect=RuntimeError("device auth failed"),
    )
    responses = mocker.patch("litellm.aresponses", new_callable=mocker.AsyncMock)

    assert run_oauth_login("github_copilot", console=console) is False

    completion.assert_awaited_once()
    responses.assert_not_awaited()
    rendered = "".join(str(call.args[0]) for call in console.print.call_args_list)
    assert "OAuth login failed" in rendered
    assert "device auth failed" in rendered


def test_run_oauth_login_suppresses_payload_shaped_failure_text(mocker):
    """OAuth login failures should not print provider request payload details."""
    console = MagicMock()
    secret_prompt = "SECRET_PROMPT_TEXT"
    secret_token = "sk-secret-token"
    payload_error = "complete_input_dict=" + repr(
        {
            "messages": [{"role": "user", "content": secret_prompt}],
            "input": "raw input",
            "api_key": secret_token,
        }
    )
    completion = mocker.patch(
        "litellm.acompletion",
        new_callable=mocker.AsyncMock,
        side_effect=RuntimeError(payload_error),
    )
    responses = mocker.patch("litellm.aresponses", new_callable=mocker.AsyncMock)

    assert run_oauth_login("github_copilot", console=console) is False

    completion.assert_awaited_once()
    responses.assert_not_awaited()
    rendered = "".join(str(call.args[0]) for call in console.print.call_args_list)
    assert "OAuth login failed" in rendered
    assert LLM_PAYLOAD_ERROR_SUMMARY in rendered
    assert "complete_input_dict" not in rendered
    assert "messages" not in rendered
    assert "input" not in rendered
    assert secret_prompt not in rendered
    assert secret_token not in rendered


def test_run_oauth_login_reports_unsupported_provider_without_raising(mocker):
    """Unsupported OAuth providers should use the friendly failure path."""
    console = MagicMock()
    responses = mocker.patch("litellm.aresponses", new_callable=mocker.AsyncMock)
    completion = mocker.patch("litellm.acompletion", new_callable=mocker.AsyncMock)

    assert run_oauth_login("codex", console=console) is False

    responses.assert_not_awaited()
    completion.assert_not_awaited()
    rendered = "".join(str(call.args[0]) for call in console.print.call_args_list)
    assert "OAuth login failed" in rendered
    assert "Unsupported OAuth provider" in rendered
