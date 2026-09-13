"""Focused tests for the `notewise config` CRUD command group."""

from __future__ import annotations

from typer.testing import CliRunner

from notewise.cli import app as cli_app
from notewise.config import allowed_config_keys, get_config_db_path
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


def test_config_set_rejects_unrecognized_key():
    result = runner.invoke(cli_app.app, ["config", "set", "NOT_A_REAL_KEY", "value"])

    assert result.exit_code == 1
    assert "config keys" in result.output


def test_config_set_surfaces_validation_errors_immediately():
    result = runner.invoke(cli_app.app, ["config", "set", "TEMPERATURE", "5.0"])

    assert result.exit_code == 1
    assert "TEMPERATURE" in result.output


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
