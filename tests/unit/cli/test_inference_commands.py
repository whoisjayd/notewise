"""Focused tests for saved inference endpoint CLI commands."""

from __future__ import annotations

from unittest.mock import AsyncMock

from typer.testing import CliRunner

from notewise.cli import app as cli_app
from notewise.llm.custom_endpoint import (
    CustomEndpointProfile,
    parse_custom_endpoint_profiles,
    serialize_custom_endpoint_profiles,
)


runner = CliRunner()


def _registry(*profiles: CustomEndpointProfile) -> str:
    """Serialize profiles for the persisted endpoint registry fixture."""
    return serialize_custom_endpoint_profiles(profiles)


def test_inference_add_replaces_profile_after_discovery_and_verification(
    mocker,
) -> None:
    """Adding a name replaces only that profile after the endpoint is verified."""
    previous = CustomEndpointProfile(
        name="office",
        base_url="https://old.example/v1",
        api_key="old-key",
    )
    config = {
        "UNRELATED_SETTING": "keep-me",
        "CUSTOM_LLM_ENDPOINTS": _registry(previous),
    }
    load_config = mocker.patch(
        "notewise.ui.setup_wizard.load_config", return_value=config
    )
    save_config = mocker.patch("notewise.ui.setup_wizard.save_config")
    discover = mocker.patch(
        "notewise.llm.custom_endpoint.discover_openai_compatible_models",
        return_value=["vendor/new-model"],
    )
    verify = mocker.patch(
        "notewise.llm.custom_endpoint.verify_openai_compatible_model",
        new_callable=AsyncMock,
    )

    result = runner.invoke(
        cli_app.app,
        [
            "inference",
            "add",
            "Office",
            "--base-url",
            "https://new.example/",
            "--api-key",
            "new-secret",
            "--model",
            "vendor/new-model",
        ],
    )

    assert result.exit_code == 0
    load_config.assert_called_once_with()
    discover.assert_called_once_with("https://new.example/v1", "new-secret")
    verify.assert_awaited_once_with(
        "https://new.example/v1", "new-secret", "vendor/new-model"
    )
    save_config.assert_called_once()
    saved_config = save_config.call_args.args[0]
    assert saved_config is config
    assert saved_config["UNRELATED_SETTING"] == "keep-me"
    assert parse_custom_endpoint_profiles(saved_config["CUSTOM_LLM_ENDPOINTS"]) == (
        CustomEndpointProfile(
            name="office",
            base_url="https://new.example/v1",
            api_key="new-secret",
        ),
    )
    assert "office/vendor/new-model" in result.output
    assert "new-secret" not in result.output


def test_inference_add_rejects_model_missing_from_live_discovery(mocker) -> None:
    """A supplied model must be present in the endpoint's live model list."""
    config = {"CUSTOM_LLM_ENDPOINTS": "[]"}
    mocker.patch("notewise.ui.setup_wizard.load_config", return_value=config)
    save_config = mocker.patch("notewise.ui.setup_wizard.save_config")
    mocker.patch(
        "notewise.llm.custom_endpoint.discover_openai_compatible_models",
        return_value=["available-model"],
    )
    verify = mocker.patch(
        "notewise.llm.custom_endpoint.verify_openai_compatible_model",
        new_callable=AsyncMock,
    )

    result = runner.invoke(
        cli_app.app,
        [
            "inference",
            "add",
            "office",
            "--base-url",
            "https://office.example",
            "--api-key",
            "unrendered-secret",
            "--model",
            "missing-model",
        ],
    )

    assert result.exit_code == 1
    verify.assert_not_awaited()
    save_config.assert_not_called()
    assert "missing-model" in result.output
    assert "unrendered-secret" not in result.output


def test_inference_update_uses_current_default_model_and_preserves_other_profiles(
    mocker,
) -> None:
    """Updating credentials uses the selected default's suffix for verification."""
    office = CustomEndpointProfile(
        name="office",
        base_url="https://office.example/v1",
        api_key="old-secret",
    )
    home = CustomEndpointProfile(
        name="home",
        base_url="https://home.example/v1",
        api_key="home-secret",
    )
    config = {
        "DEFAULT_MODEL": "OFFICE/vendor/current-model",
        "UNRELATED_SETTING": "keep-me",
        "CUSTOM_LLM_ENDPOINTS": _registry(office, home),
    }
    mocker.patch("notewise.ui.setup_wizard.load_config", return_value=config)
    save_config = mocker.patch("notewise.ui.setup_wizard.save_config")
    discover = mocker.patch(
        "notewise.llm.custom_endpoint.discover_openai_compatible_models",
        return_value=["vendor/current-model"],
    )
    verify = mocker.patch(
        "notewise.llm.custom_endpoint.verify_openai_compatible_model",
        new_callable=AsyncMock,
    )

    result = runner.invoke(
        cli_app.app,
        ["inference", "update", "Office", "--api-key", "replacement-secret"],
    )

    assert result.exit_code == 0
    discover.assert_called_once_with("https://office.example/v1", "replacement-secret")
    verify.assert_awaited_once_with(
        "https://office.example/v1", "replacement-secret", "vendor/current-model"
    )
    save_config.assert_called_once()
    saved_profiles = parse_custom_endpoint_profiles(
        save_config.call_args.args[0]["CUSTOM_LLM_ENDPOINTS"]
    )
    assert saved_profiles == (
        CustomEndpointProfile(
            name="office",
            base_url="https://office.example/v1",
            api_key="replacement-secret",
        ),
        home,
    )
    assert config["DEFAULT_MODEL"] == "OFFICE/vendor/current-model"
    assert config["UNRELATED_SETTING"] == "keep-me"
    assert "replacement-secret" not in result.output


def test_inference_update_requires_key_when_replacing_endpoint_origin(mocker) -> None:
    """Changing an endpoint URL cannot reuse its key with a different origin."""
    office = CustomEndpointProfile(
        name="office",
        base_url="https://office.example/v1",
        api_key="old-secret",
    )
    mocker.patch(
        "notewise.ui.setup_wizard.load_config",
        return_value={
            "DEFAULT_MODEL": "office/vendor/model",
            "CUSTOM_LLM_ENDPOINTS": _registry(office),
        },
    )
    discover = mocker.patch(
        "notewise.llm.custom_endpoint.discover_openai_compatible_models"
    )
    save_config = mocker.patch("notewise.ui.setup_wizard.save_config")

    result = runner.invoke(
        cli_app.app,
        [
            "inference",
            "update",
            "office",
            "--base-url",
            "https://replacement.example",
        ],
    )

    assert result.exit_code == 1
    assert "api-key" in result.output
    discover.assert_not_called()
    save_config.assert_not_called()


def test_inference_update_requires_endpoint_change_before_io(mocker) -> None:
    """Updating only a model is rejected before loading or saving configuration."""
    load_config = mocker.patch("notewise.ui.setup_wizard.load_config")
    save_config = mocker.patch("notewise.ui.setup_wizard.save_config")

    result = runner.invoke(
        cli_app.app,
        ["inference", "update", "office", "--model", "vendor/model"],
    )

    assert result.exit_code == 2
    load_config.assert_not_called()
    save_config.assert_not_called()


def test_inference_delete_refuses_normalized_default_endpoint(mocker) -> None:
    """Deletion is blocked when DEFAULT_MODEL selects the endpoint by case variant."""
    office = CustomEndpointProfile(
        name="office",
        base_url="https://office.example/v1",
        api_key="hidden-secret",
    )
    mocker.patch(
        "notewise.ui.setup_wizard.load_config",
        return_value={
            "DEFAULT_MODEL": "OFFICE/vendor/model",
            "CUSTOM_LLM_ENDPOINTS": _registry(office),
        },
    )
    save_config = mocker.patch("notewise.ui.setup_wizard.save_config")

    result = runner.invoke(cli_app.app, ["inference", "delete", "Office"])

    assert result.exit_code == 1
    save_config.assert_not_called()
    assert "DEFAULT_MODEL" in result.output
    assert "hidden-secret" not in result.output


def test_inference_delete_rejects_invalid_default_model_prefix(mocker) -> None:
    """An invalid default model cannot bypass endpoint deletion protection."""
    office = CustomEndpointProfile(
        name="office",
        base_url="https://office.example/v1",
        api_key="hidden-secret",
    )
    mocker.patch(
        "notewise.ui.setup_wizard.load_config",
        return_value={
            "DEFAULT_MODEL": "invalid%prefix/vendor/model",
            "CUSTOM_LLM_ENDPOINTS": _registry(office),
        },
    )
    save_config = mocker.patch("notewise.ui.setup_wizard.save_config")

    result = runner.invoke(cli_app.app, ["inference", "delete", "office"])

    assert result.exit_code == 1
    assert "Custom endpoint name" in result.output
    save_config.assert_not_called()


def test_inference_list_and_delete_never_render_api_keys(mocker) -> None:
    """Listing and deleting endpoint profiles expose names and URLs, never keys."""
    office = CustomEndpointProfile(
        name="office",
        base_url="https://office.example/v1",
        api_key="private-office-key",
    )
    home = CustomEndpointProfile(
        name="home",
        base_url="https://home.example/v1",
        api_key="private-home-key",
    )
    list_config = {"CUSTOM_LLM_ENDPOINTS": _registry(office, home)}
    load_config = mocker.patch(
        "notewise.ui.setup_wizard.load_config", return_value=list_config
    )
    save_config = mocker.patch("notewise.ui.setup_wizard.save_config")

    listed = runner.invoke(cli_app.app, ["inference", "list"])

    assert listed.exit_code == 0
    assert "office" in listed.output
    assert "https://office.example/v1" in listed.output
    assert "private-office-key" not in listed.output
    assert "private-home-key" not in listed.output
    save_config.assert_not_called()

    delete_config = {
        "DEFAULT_MODEL": "builtin/model",
        "UNRELATED_SETTING": "keep-me",
        "CUSTOM_LLM_ENDPOINTS": _registry(office, home),
    }
    load_config.return_value = delete_config
    deleted = runner.invoke(cli_app.app, ["inference", "delete", "office"])

    assert deleted.exit_code == 0
    save_config.assert_called_once()
    saved_config = save_config.call_args.args[0]
    assert saved_config is delete_config
    assert saved_config["UNRELATED_SETTING"] == "keep-me"
    assert parse_custom_endpoint_profiles(saved_config["CUSTOM_LLM_ENDPOINTS"]) == (
        home,
    )
    assert "private-office-key" not in deleted.output
    assert "private-home-key" not in deleted.output
