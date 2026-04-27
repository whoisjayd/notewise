"""Tests for OAuth authentication CLI commands."""

from __future__ import annotations

from typer.testing import CliRunner

from notewise.cli import app as cli_app


runner = CliRunner()


def test_auth_login_uses_provider_argument(mocker):
    """Provider arguments should dispatch to the shared OAuth login helper."""
    login = mocker.patch("notewise.cli.app.run_oauth_login", return_value=True)

    result = runner.invoke(cli_app.app, ["auth", "login", "chatgpt"])

    assert result.exit_code == 0
    login.assert_called_once_with("chatgpt", console=cli_app._get_console())


def test_auth_login_prompts_when_provider_omitted(mocker):
    """Omitted providers should be selected interactively."""
    mocker.patch("rich.prompt.Prompt.ask", return_value="2")
    login = mocker.patch("notewise.cli.app.run_oauth_login", return_value=True)

    result = runner.invoke(cli_app.app, ["auth", "login"])

    assert result.exit_code == 0
    login.assert_called_once_with("github_copilot", console=cli_app._get_console())


def test_auth_login_codex_resolves_to_chatgpt_without_prompt(mocker):
    """Codex is a compatibility alias for ChatGPT subscription login."""
    prompt = mocker.patch("rich.prompt.Prompt.ask", return_value="1")
    login = mocker.patch("notewise.cli.app.run_oauth_login", return_value=True)

    result = runner.invoke(cli_app.app, ["auth", "login", "codex"])

    assert result.exit_code == 0
    prompt.assert_not_called()
    login.assert_called_once_with("chatgpt", console=cli_app._get_console())


def test_auth_login_invalid_provider_fails_before_login(mocker):
    """Unknown providers should fail without attempting OAuth."""
    login = mocker.patch("notewise.cli.app.run_oauth_login", return_value=True)

    result = runner.invoke(cli_app.app, ["auth", "login", "openai"])

    assert result.exit_code != 0
    login.assert_not_called()
