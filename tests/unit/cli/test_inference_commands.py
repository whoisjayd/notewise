"""Focused tests for saved inference endpoint CLI commands."""

from __future__ import annotations

from unittest.mock import AsyncMock

from typer.testing import CliRunner

from notewise.cli import app as cli_app
from notewise.config import get_config_db_path
from notewise.llm.custom_endpoint import CustomEndpointProfile
from notewise.storage import config_store
from notewise.ui.setup_wizard import save_config


runner = CliRunner()


def test_inference_add_replaces_profile_after_discovery_and_verification(
    mocker,
) -> None:
    """Adding a name replaces only that profile after the endpoint is verified."""
    db_path = get_config_db_path()
    previous = CustomEndpointProfile(
        name="office",
        base_url="https://old.example/v1",
        api_key="old-key",
    )
    config_store.upsert_custom_endpoint(db_path, previous)
    save_config({"UNRELATED_SETTING": "keep-me"})

    discover = mocker.patch(
        "notewise.llm.custom_endpoint._fetch_model_list_payload",
        return_value=[{"id": "vendor/new-model"}],
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
    discover.assert_called_once_with("https://new.example/v1", "new-secret")
    verify.assert_awaited_once_with(
        "https://new.example/v1", "new-secret", "vendor/new-model"
    )
    assert config_store.load_config_db(db_path)["UNRELATED_SETTING"] == "keep-me"
    assert config_store.list_custom_endpoints(db_path) == (
        CustomEndpointProfile(
            name="office",
            base_url="https://new.example/v1",
            api_key="new-secret",
        ),
    )
    assert "office/vendor/new-model" in result.output
    assert "new-secret" not in result.output


def test_inference_add_accepts_short_flag_aliases(mocker) -> None:
    """-b/-k/-m should behave identically to --base-url/--api-key/--model."""
    db_path = get_config_db_path()
    discover = mocker.patch(
        "notewise.llm.custom_endpoint._fetch_model_list_payload",
        return_value=[{"id": "vendor/new-model"}],
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
            "-b",
            "https://new.example/",
            "-k",
            "new-secret",
            "-m",
            "vendor/new-model",
        ],
    )

    assert result.exit_code == 0
    discover.assert_called_once_with("https://new.example/v1", "new-secret")
    verify.assert_awaited_once_with(
        "https://new.example/v1", "new-secret", "vendor/new-model"
    )
    assert config_store.list_custom_endpoints(db_path) == (
        CustomEndpointProfile(
            name="office",
            base_url="https://new.example/v1",
            api_key="new-secret",
        ),
    )


def test_inference_add_prompts_for_missing_arguments(mocker) -> None:
    """Omitted add arguments should be collected via interactive prompts."""
    db_path = get_config_db_path()

    discover = mocker.patch(
        "notewise.llm.custom_endpoint._fetch_model_list_payload",
        return_value=[{"id": "vendor/new-model"}],
    )
    verify = mocker.patch(
        "notewise.llm.custom_endpoint.verify_openai_compatible_model",
        new_callable=AsyncMock,
    )
    mocker.patch(
        "notewise.ui.setup_wizard._select_or_enter_model",
        return_value="vendor/new-model",
    )
    mocker.patch(
        "rich.prompt.Prompt.ask",
        side_effect=["office", "https://new.example/", "new-secret"],
    )

    result = runner.invoke(cli_app.app, ["inference", "add"])

    assert result.exit_code == 0
    discover.assert_called_once_with("https://new.example/v1", "new-secret")
    verify.assert_awaited_once_with(
        "https://new.example/v1", "new-secret", "vendor/new-model"
    )
    assert config_store.list_custom_endpoints(db_path) == (
        CustomEndpointProfile(
            name="office",
            base_url="https://new.example/v1",
            api_key="new-secret",
        ),
    )
    assert "new-secret" not in result.output


def test_inference_update_accepts_short_flag_aliases(mocker) -> None:
    """-b/-k/-m should behave identically to --base-url/--api-key/--model."""
    db_path = get_config_db_path()
    office = CustomEndpointProfile(
        name="office",
        base_url="https://office.example/v1",
        api_key="old-secret",
    )
    config_store.upsert_custom_endpoint(db_path, office)
    mocker.patch(
        "notewise.llm.custom_endpoint._fetch_model_list_payload",
        return_value=[{"id": "vendor/new-model"}],
    )
    verify = mocker.patch(
        "notewise.llm.custom_endpoint.verify_openai_compatible_model",
        new_callable=AsyncMock,
    )

    result = runner.invoke(
        cli_app.app,
        [
            "inference",
            "update",
            "office",
            "-b",
            "https://new.example/",
            "-k",
            "new-secret",
            "-m",
            "vendor/new-model",
        ],
    )

    assert result.exit_code == 0
    verify.assert_awaited_once_with(
        "https://new.example/v1", "new-secret", "vendor/new-model"
    )
    assert config_store.list_custom_endpoints(db_path) == (
        CustomEndpointProfile(
            name="office",
            base_url="https://new.example/v1",
            api_key="new-secret",
        ),
    )


def test_inference_add_rejects_model_missing_from_live_discovery(mocker) -> None:
    """A supplied model must be present in the endpoint's live model list."""
    db_path = get_config_db_path()
    mocker.patch(
        "notewise.llm.custom_endpoint._fetch_model_list_payload",
        return_value=[{"id": "available-model"}],
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
    assert config_store.list_custom_endpoints(db_path) == ()
    assert "missing-model" in result.output
    assert "unrendered-secret" not in result.output


def test_inference_update_uses_current_default_model_and_preserves_other_profiles(
    mocker,
) -> None:
    """Updating credentials uses the selected default's suffix for verification."""
    db_path = get_config_db_path()
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
    config_store.upsert_custom_endpoint(db_path, office)
    config_store.upsert_custom_endpoint(db_path, home)
    save_config(
        {
            "DEFAULT_MODEL": "OFFICE/vendor/current-model",
            "UNRELATED_SETTING": "keep-me",
        }
    )

    discover = mocker.patch(
        "notewise.llm.custom_endpoint._fetch_model_list_payload",
        return_value=[{"id": "vendor/current-model"}],
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
    saved_profiles = config_store.list_custom_endpoints(db_path)
    assert set(saved_profiles) == {
        CustomEndpointProfile(
            name="office",
            base_url="https://office.example/v1",
            api_key="replacement-secret",
        ),
        home,
    }
    saved_config = config_store.load_config_db(db_path)
    assert saved_config["DEFAULT_MODEL"] == "OFFICE/vendor/current-model"
    assert saved_config["UNRELATED_SETTING"] == "keep-me"
    assert "replacement-secret" not in result.output


def test_inference_update_requires_key_when_replacing_endpoint_origin(mocker) -> None:
    """Changing an endpoint URL cannot reuse its key with a different origin."""
    db_path = get_config_db_path()
    office = CustomEndpointProfile(
        name="office",
        base_url="https://office.example/v1",
        api_key="old-secret",
    )
    config_store.upsert_custom_endpoint(db_path, office)
    save_config({"DEFAULT_MODEL": "office/vendor/model"})
    discover = mocker.patch("notewise.llm.custom_endpoint._fetch_model_list_payload")

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
    assert config_store.list_custom_endpoints(db_path) == (office,)


def test_inference_update_requires_endpoint_change_before_io(mocker) -> None:
    """Updating only a model is rejected before loading or saving configuration."""
    discover = mocker.patch("notewise.llm.custom_endpoint._fetch_model_list_payload")

    result = runner.invoke(
        cli_app.app,
        ["inference", "update", "office", "--model", "vendor/model"],
    )

    assert result.exit_code == 2
    discover.assert_not_called()


def test_inference_update_prompts_when_name_is_omitted(mocker) -> None:
    """Omitting the name should list saved endpoints and prompt for an index."""
    db_path = get_config_db_path()
    office = CustomEndpointProfile(
        name="office",
        base_url="https://office.example/v1",
        api_key="old-secret",
    )
    config_store.upsert_custom_endpoint(db_path, office)

    discover = mocker.patch(
        "notewise.llm.custom_endpoint._fetch_model_list_payload",
        return_value=[{"id": "vendor/model"}],
    )
    verify = mocker.patch(
        "notewise.llm.custom_endpoint.verify_openai_compatible_model",
        new_callable=AsyncMock,
    )
    mocker.patch(
        "notewise.ui.setup_wizard._select_or_enter_model",
        return_value="vendor/model",
    )
    mocker.patch("rich.prompt.Prompt.ask", side_effect=["1", "", ""])

    result = runner.invoke(cli_app.app, ["inference", "update"])

    assert result.exit_code == 0
    discover.assert_called_once_with("https://office.example/v1", "old-secret")
    verify.assert_awaited_once_with(
        "https://office.example/v1", "old-secret", "vendor/model"
    )
    assert config_store.list_custom_endpoints(db_path) == (office,)


def test_inference_delete_refuses_normalized_default_endpoint(mocker) -> None:
    """Deletion is blocked when DEFAULT_MODEL selects the endpoint by case variant."""
    db_path = get_config_db_path()
    office = CustomEndpointProfile(
        name="office",
        base_url="https://office.example/v1",
        api_key="hidden-secret",
    )
    config_store.upsert_custom_endpoint(db_path, office)
    save_config({"DEFAULT_MODEL": "OFFICE/vendor/model"})

    result = runner.invoke(cli_app.app, ["inference", "delete", "Office"])

    assert result.exit_code == 1
    assert config_store.list_custom_endpoints(db_path) == (office,)
    assert "DEFAULT_MODEL" in result.output
    assert "hidden-secret" not in result.output


def test_inference_delete_rejects_invalid_default_model_prefix(mocker) -> None:
    """An invalid default model cannot bypass endpoint deletion protection."""
    db_path = get_config_db_path()
    office = CustomEndpointProfile(
        name="office",
        base_url="https://office.example/v1",
        api_key="hidden-secret",
    )
    config_store.upsert_custom_endpoint(db_path, office)
    save_config({"DEFAULT_MODEL": "invalid%prefix/vendor/model"})

    result = runner.invoke(cli_app.app, ["inference", "delete", "office"])

    assert result.exit_code == 1
    assert "Custom endpoint name" in result.output
    assert config_store.list_custom_endpoints(db_path) == (office,)


def test_inference_delete_prompts_when_name_is_omitted(mocker) -> None:
    """Omitting the name should list saved endpoints and prompt for an index."""
    db_path = get_config_db_path()
    office = CustomEndpointProfile(
        name="office",
        base_url="https://office.example/v1",
        api_key="hidden-secret",
    )
    config_store.upsert_custom_endpoint(db_path, office)

    result = runner.invoke(cli_app.app, ["inference", "delete"], input="1\n")

    assert result.exit_code == 0
    assert config_store.list_custom_endpoints(db_path) == ()
    assert "office" in result.output
    assert "hidden-secret" not in result.output


def test_inference_list_and_delete_never_render_api_keys(mocker) -> None:
    """Listing and deleting endpoint profiles expose names and URLs, never keys."""
    db_path = get_config_db_path()
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
    config_store.upsert_custom_endpoint(db_path, office)
    config_store.upsert_custom_endpoint(db_path, home)

    listed = runner.invoke(cli_app.app, ["inference", "list"])

    assert listed.exit_code == 0
    assert "office" in listed.output
    assert "https://office.example/v1" in listed.output
    assert "private-office-key" not in listed.output
    assert "private-home-key" not in listed.output

    save_config({"DEFAULT_MODEL": "builtin/model", "UNRELATED_SETTING": "keep-me"})
    deleted = runner.invoke(cli_app.app, ["inference", "delete", "office"])

    assert deleted.exit_code == 0
    saved_config = config_store.load_config_db(db_path)
    assert saved_config["UNRELATED_SETTING"] == "keep-me"
    assert config_store.list_custom_endpoints(db_path) == (home,)
    assert "private-home-key" not in deleted.output
