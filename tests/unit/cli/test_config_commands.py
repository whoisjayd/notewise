"""Focused tests for the `notewise config` CRUD command group."""

from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from notewise.cli import app as cli_app
from notewise.config import (
    allowed_config_keys,
    categorize_config_keys,
    get_config_db_path,
)
from notewise.storage import config_store


runner = CliRunner()


def test_config_keys_lists_every_allowed_key():
    """`config keys` must surface every key get/set/unset will accept."""
    result = runner.invoke(cli_app.app, ["config", "keys"])

    assert result.exit_code == 0
    listed = set(result.output.split())
    assert listed == allowed_config_keys()


def test_config_set_then_get_round_trips():
    result_set = runner.invoke(
        cli_app.app, ["config", "set", "DEFAULT_MODEL", "gemini/gemini-2.5-flash"]
    )
    assert result_set.exit_code == 0

    result_get = runner.invoke(cli_app.app, ["config", "get", "DEFAULT_MODEL"])
    assert result_get.exit_code == 0
    assert "gemini/gemini-2.5-flash" in result_get.output


def test_config_get_masks_secret_keys():
    runner.invoke(cli_app.app, ["config", "set", "GEMINI_API_KEY", "gk-super-secret"])

    result = runner.invoke(cli_app.app, ["config", "get", "GEMINI_API_KEY"])

    assert result.exit_code == 0
    assert "gk-super-secret" not in result.output


def test_config_get_missing_key_exits_nonzero():
    result = runner.invoke(cli_app.app, ["config", "get", "TEMPERATURE"])

    assert result.exit_code == 1
    assert "is not set" in result.output


def test_config_set_prompts_with_hidden_input_when_value_omitted(mocker):
    """Omitting VALUE for a sensitive key must prompt rather than error, so
    the secret never has to appear in shell history.

    ``Prompt.ask(..., password=True)`` is mocked rather than driven through
    CliRunner's ``input=`` pipe: that pipe isn't a real TTY, so the actual
    hidden-input codepath falls back to a visible read and warns -- this
    test only needs to verify *that* hidden input is requested, which the
    call assertion below covers.
    """
    ask = mocker.patch("rich.prompt.Prompt.ask", return_value="gk-from-prompt")

    result = runner.invoke(cli_app.app, ["config", "set", "GEMINI_API_KEY"])

    assert result.exit_code == 0
    ask.assert_called_once_with("Enter value for GEMINI_API_KEY", password=True)
    result_get = runner.invoke(cli_app.app, ["config", "get", "GEMINI_API_KEY"])
    assert "gk-from-prompt" not in result_get.output  # masked, but round-tripped
    assert config_store.load_config_db(get_config_db_path())["GEMINI_API_KEY"] == (
        "gk-from-prompt"
    )


def test_config_set_rejects_unrecognized_key():
    result = runner.invoke(cli_app.app, ["config", "set", "NOT_A_REAL_KEY", "value"])

    assert result.exit_code == 1
    assert "config keys" in result.output


def test_config_set_surfaces_validation_errors_immediately():
    result = runner.invoke(cli_app.app, ["config", "set", "TEMPERATURE", "5.0"])

    assert result.exit_code == 1
    assert "TEMPERATURE" in result.output


def test_config_set_rejecting_invalid_value_does_not_persist_it():
    """A rejected value must never reach config.db -- otherwise it breaks
    every later AppSettings load, including the very next CLI command.
    """
    result = runner.invoke(cli_app.app, ["config", "set", "TEMPERATURE", "5.0"])

    assert result.exit_code == 1
    assert "TEMPERATURE" not in config_store.load_config_db(get_config_db_path())


def test_config_unset_removes_key():
    runner.invoke(cli_app.app, ["config", "set", "MAX_TOKENS", "1000"])

    result = runner.invoke(cli_app.app, ["config", "unset", "MAX_TOKENS"])

    assert result.exit_code == 0
    db_path = get_config_db_path()
    assert "MAX_TOKENS" not in config_store.load_config_db(db_path)


def test_config_set_rejects_malformed_custom_endpoints_json():
    result = runner.invoke(
        cli_app.app, ["config", "set", "CUSTOM_LLM_ENDPOINTS", "not-json"]
    )

    assert result.exit_code == 1
    assert "must be a valid JSON array" in result.output
    assert (
        config_store.load_config_db(get_config_db_path()).get("CUSTOM_LLM_ENDPOINTS")
        is None
    )


def test_config_unset_missing_key_exits_nonzero():
    result = runner.invoke(cli_app.app, ["config", "unset", "MAX_TOKENS"])

    assert result.exit_code == 1
    assert "is not set" in result.output


def test_categorize_config_keys_covers_every_allowed_key_exactly_once():
    """Every key `config keys` lists must land in exactly one category."""
    categories = categorize_config_keys()
    seen: set[str] = set()
    for keys in categories.values():
        overlap = seen & set(keys)
        assert not overlap, f"keys assigned to multiple categories: {overlap}"
        seen.update(keys)

    assert seen == allowed_config_keys()


def test_config_edit_lists_categories_then_exits():
    with patch("rich.prompt.Prompt.ask", side_effect=["q"]):
        result = runner.invoke(cli_app.app, ["config", "edit"])

    assert result.exit_code == 0
    assert "Configuration Categories" in result.output
    assert "Model & Generation" in result.output
    assert "Exiting config editor" in result.output


def test_config_edit_can_set_a_value():
    with patch("rich.prompt.Prompt.ask", side_effect=["1", "2", "s", "0.3", "q", "q"]):
        result = runner.invoke(cli_app.app, ["config", "edit"])

    assert result.exit_code == 0
    assert config_store.load_config_db(get_config_db_path())["TEMPERATURE"] == "0.3"


def test_config_edit_set_rejects_invalid_value_without_persisting():
    # Note: this only asserts the behavioral guarantee (nothing persisted),
    # not the exact rendered message -- Click 8.2+'s CliRunner has a known
    # flush-timing issue (pallets/click #2913/#2682) that can drop
    # mid-invocation Rich console output from a *second* CliRunner.invoke()
    # call in the same test process, unrelated to notewise's own behavior.
    # The exact message text is covered reliably by
    # test_run_config_editor_set_shows_clean_validation_message in
    # test_setup_wizard.py, which calls run_config_editor() directly
    # instead of through CliRunner.
    with patch(
        "rich.prompt.Prompt.ask", side_effect=["1", "2", "s", "5.0", "c", "q", "q"]
    ):
        result = runner.invoke(cli_app.app, ["config", "edit"])

    assert result.exit_code == 0
    assert "TEMPERATURE" not in config_store.load_config_db(get_config_db_path())


def test_config_edit_can_unset_a_value():
    runner.invoke(cli_app.app, ["config", "set", "MAX_TOKENS", "1000"])

    with patch("rich.prompt.Prompt.ask", side_effect=["1", "3", "u", "q", "q"]):
        result = runner.invoke(cli_app.app, ["config", "edit"])

    assert result.exit_code == 0
    assert "Removed MAX_TOKENS" in result.output
    assert "MAX_TOKENS" not in config_store.load_config_db(get_config_db_path())


def test_config_edit_masks_secret_values_in_table():
    runner.invoke(cli_app.app, ["config", "set", "GEMINI_API_KEY", "gk-super-secret"])

    with patch("rich.prompt.Prompt.ask", side_effect=["6", "q", "q"]):
        result = runner.invoke(cli_app.app, ["config", "edit"])

    assert result.exit_code == 0
    assert "gk-super-secret" not in result.output


def test_config_edit_handles_invalid_category_and_key_choices():
    with patch("rich.prompt.Prompt.ask", side_effect=["nope", "1", "nope", "b", "q"]):
        result = runner.invoke(cli_app.app, ["config", "edit"])

    assert result.exit_code == 0
    assert "Invalid choice. Enter a category number or 'q'." in result.output
    assert "Invalid choice. Enter a key number, 'b', or 'q'." in result.output
