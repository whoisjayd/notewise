"""Tests for the setup wizard."""

from unittest.mock import MagicMock, mock_open, patch

import pytest

from notewise.errors import ConfigurationError
from notewise.ui.setup_wizard import (
    get_api_key,
    get_available_models,
    get_config_path,
    load_config,
    run_setup_wizard,
    save_config,
    select_model,
    select_provider,
    show_current_config,
)
from notewise.utils import strip_wrapped_quotes


# Mock config content
MOCK_CONFIG_CONTENT = """
GEMINI_API_KEY=old_gemini_key
DEFAULT_MODEL=gemini/old-model
"""


class TestConfigIO:
    """Test configuration loading and saving."""

    def test_load_config_exists(self):
        """Test loading config when file exists."""
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.open", mock_open(read_data=MOCK_CONFIG_CONTENT)),
        ):
            config = load_config()
            assert config["GEMINI_API_KEY"] == "old_gemini_key"
            assert config["DEFAULT_MODEL"] == "gemini/old-model"

    def test_load_config_not_exists(self):
        """Test loading config when file does not exist."""
        with patch("pathlib.Path.exists", return_value=False):
            config = load_config()
            assert config == {}

    def test_load_config_corrupted(self):
        """Test loading corrupted config file."""
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "pathlib.Path.open",
                mock_open(read_data="junk data without equals sign"),
            ),
        ):
            config = load_config()
            assert config == {}

    def test_load_config_strips_wrapped_quotes(self):
        """Quoted env-style values should load without their wrapper quotes."""
        quoted_config = (
            'GEMINI_API_KEY="quoted-key"\n'
            "OUTPUT_DIR='/tmp/notes'\n"
            "DEFAULT_MODEL=gemini/gemini-2.5-flash\n"
        )

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.open", mock_open(read_data=quoted_config)),
        ):
            config = load_config()

        assert config["GEMINI_API_KEY"] == "quoted-key"
        assert config["OUTPUT_DIR"] == "/tmp/notes"
        assert config["DEFAULT_MODEL"] == "gemini/gemini-2.5-flash"

    def test_load_config_read_failure_raises_configuration_error(self, mocker):
        """Config read failures should use the project error hierarchy."""
        mocker.patch("pathlib.Path.exists", return_value=True)
        mocker.patch("pathlib.Path.open", side_effect=OSError("denied"))

        with (
            pytest.raises(
                ConfigurationError,
                match="Failed to read configuration",
            ),
        ):
            load_config()

    def test_load_config_does_not_hide_unexpected_errors(self, mocker):
        """Unexpected parser/runtime failures should remain visible."""
        mocker.patch("pathlib.Path.exists", return_value=True)
        mocker.patch("pathlib.Path.open", side_effect=RuntimeError("bug"))

        with pytest.raises(RuntimeError, match="bug"):
            load_config()

    def test_save_config(self):
        """Test saving configuration merges with existing."""
        from pathlib import Path

        mock_path = Path("dummy_path")
        with (
            patch(
                "notewise.ui.setup_wizard.load_config",
                return_value={"OLD_KEY": "old_val"},
            ),
            patch("pathlib.Path.open", mock_open()) as mock_file,
            patch("notewise.ui.setup_wizard.get_config_path", return_value=mock_path),
        ):
            new_config = {"NEW_KEY": "new_val", "DEFAULT_MODEL": "new_model"}
            save_config(new_config)

            # Verify file write operations
            handle = mock_file()
            # We expect multiple write calls. Let's check if the keys are written.
            # We can construct the written string
            written_content = "".join(
                call.args[0] for call in handle.write.call_args_list
            )

            assert "OLD_KEY=old_val" in written_content
            assert "NEW_KEY=new_val" in written_content
            assert "DEFAULT_MODEL=new_model" in written_content

    def test_save_config_strips_legacy_youtube_auth_keys(self):
        """Saving config should remove legacy OAuth and cookie-era auth keys."""
        from pathlib import Path

        mock_path = Path("dummy_path")
        with (
            patch(
                "notewise.ui.setup_wizard.load_config",
                return_value={
                    "YOUTUBE_USE_OAUTH": "true",
                    "YOUTUBE_SAVE_OAUTH_TOKEN": "true",
                    "YOUTUBE_OAUTH_TOKEN_FILE": "/tmp/token.json",
                    "YOUTUBE_AUTO_REFRESH_OAUTH_TOKEN": "false",
                    "OLD_KEY": "old_val",
                },
            ),
            patch("pathlib.Path.open", mock_open()) as mock_file,
            patch("notewise.ui.setup_wizard.get_config_path", return_value=mock_path),
        ):
            save_config({"DEFAULT_MODEL": "new_model"})

            written_content = "".join(
                call.args[0] for call in mock_file().write.call_args_list
            )

        assert "OLD_KEY=old_val" in written_content
        assert "DEFAULT_MODEL=new_model" in written_content
        assert "YOUTUBE_USE_OAUTH" not in written_content
        assert "YOUTUBE_SAVE_OAUTH_TOKEN" not in written_content
        assert "YOUTUBE_OAUTH_TOKEN_FILE" not in written_content
        assert "YOUTUBE_AUTO_REFRESH_OAUTH_TOKEN" not in written_content

    def test_show_current_config_masks_api_keys(self):
        """Read-only config display should mask secret values."""
        console = MagicMock()
        with (
            patch(
                "notewise.ui.setup_wizard.load_config",
                return_value={
                    "DEFAULT_MODEL": "gemini/gemini-2.5-flash",
                    "GEMINI_API_KEY": "secret-api-key-value",
                },
            ),
            patch(
                "notewise.ui.setup_wizard.get_config_path",
                return_value=get_config_path(),
            ),
        ):
            current = show_current_config(console=console)

        assert current["GEMINI_API_KEY"] == "secret-api-key-value"
        rendered = "".join(str(call.args[0]) for call in console.print.call_args_list)
        assert "secret-api-key-value" not in rendered
        assert console.print.call_count >= 2

    def test_show_current_config_handles_missing_config(self):
        """Read-only config display should report missing config cleanly."""
        console = MagicMock()
        with patch("notewise.ui.setup_wizard.load_config", return_value={}):
            current = show_current_config(console=console)

        assert current == {}
        rendered = "".join(str(call.args[0]) for call in console.print.call_args_list)
        assert "No configuration found" in rendered

    def test_strip_wrapped_quotes_handles_python_raw_string_prefix(self):
        """Displayed config values should normalize r\"...\" path literals."""
        assert strip_wrapped_quotes('r"D:\\tmp\\out"') == "D:\\tmp\\out"

    def test_setup_wizard_can_run_oauth_login_for_oauth_provider(self):
        """OAuth providers should offer the same login flow during setup."""
        console = MagicMock()
        with (
            patch("notewise.ui.setup_wizard.load_config", return_value={}),
            patch(
                "notewise.ui.setup_wizard.get_available_models",
                return_value={"chatgpt": ["chatgpt/gpt-5.2"]},
            ),
            patch("notewise.ui.setup_wizard.select_provider", return_value="chatgpt"),
            patch(
                "notewise.ui.setup_wizard.select_model",
                return_value="chatgpt/gpt-5.2",
            ),
            patch("rich.prompt.Confirm.ask", return_value=True),
            patch("rich.prompt.Prompt.ask", return_value="./output"),
            patch("notewise.ui.setup_wizard._prompt_positive_int", return_value="5"),
            patch("notewise.ui.setup_wizard.save_config"),
            patch(
                "notewise.ui.setup_wizard.run_oauth_login",
                return_value=True,
            ) as login,
        ):
            run_setup_wizard(force=True, console=console)

        login.assert_called_once_with("chatgpt", console=console)

    def test_setup_wizard_stops_when_oauth_login_fails(self):
        """Failed OAuth setup should not save a new OAuth-only model config."""
        console = MagicMock()
        current_config = {"DEFAULT_MODEL": "gemini/gemini-2.5-flash"}
        with (
            patch("notewise.ui.setup_wizard.load_config", return_value=current_config),
            patch(
                "notewise.ui.setup_wizard.get_available_models",
                return_value={"chatgpt": ["chatgpt/gpt-5.2"]},
            ),
            patch("notewise.ui.setup_wizard.select_provider", return_value="chatgpt"),
            patch(
                "notewise.ui.setup_wizard.select_model",
                return_value="chatgpt/gpt-5.2",
            ),
            patch("rich.prompt.Confirm.ask", return_value=True),
            patch("notewise.ui.setup_wizard.save_config") as save_config_mock,
            patch(
                "notewise.ui.setup_wizard.run_oauth_login",
                return_value=False,
            ) as login,
        ):
            result = run_setup_wizard(force=True, console=console)

        assert result == current_config
        login.assert_called_once_with("chatgpt", console=console)
        save_config_mock.assert_not_called()

    def test_show_current_config_reports_read_errors(self):
        """Unreadable config files should not be misreported as missing config."""
        console = MagicMock()
        with patch(
            "notewise.ui.setup_wizard.load_config",
            side_effect=ConfigurationError("Failed to read configuration"),
        ):
            current = show_current_config(console=console)

        assert current == {}
        rendered = "".join(str(call.args[0]) for call in console.print.call_args_list)
        assert "Failed to read configuration" in rendered


class TestModelFetching:
    """Test fetching models from LiteLLM."""

    def test_get_available_models_uses_bundled_snapshot(self):
        """Bundled snapshot data should short-circuit the live LiteLLM fetch."""
        bundled_models = {
            "gemini": ["gemini/gemini-2.5-pro"],
            "openrouter": ["openrouter/google/gemini-2.5-flash"],
        }

        with patch(
            "notewise.ui.setup_wizard._load_bundled_model_snapshot",
            return_value=bundled_models,
        ):
            models = get_available_models()

        assert models == bundled_models

    def test_get_available_models_success(self):
        """Test successful fetch from litellm."""
        mock_models = [
            "gpt-4",
            "gpt-3.5-turbo",
            "claude-3-opus",
            "gemini/gemini-pro",
            "unknown-provider/model",
        ]

        with (
            patch(
                "notewise.ui.setup_wizard._load_bundled_model_snapshot",
                return_value={},
            ),
            patch("litellm.model_list", mock_models, create=True),
        ):
            models = get_available_models()

            assert "openai" in models
            assert "gpt-4" in models["openai"]
            assert "anthropic" in models
            assert "gemini" in models
            # Unknown provider should be ignored
            assert "unknown-provider" not in models

    def test_get_available_models_failure(self):
        """Absent bundled snapshot and LiteLLM metadata should return no models."""
        # Simulate import error or exception accessing model_list
        with (
            patch(
                "notewise.ui.setup_wizard._load_bundled_model_snapshot",
                return_value={},
            ),
            patch.dict("sys.modules", {"litellm": None}),
        ):
            models = get_available_models()

            assert models == {}

    def test_get_available_models_filters_only_deprecated_gateway_and_non_text(self):
        """Setup should keep preview models while still hiding deprecated ones."""
        mock_models = [
            "gpt-4o-mini",
            "o3-mini",
            "o4-mini",
            "azure/gpt-4o",
            "gpt-4o-mini-preview",
            "gemini/gemini-2.5-flash",
            "gemini/gemini-3-flash-preview",
            "gemini/gemini-3.1-pro-preview",
            "gemini/gemini-2.5-flash",
            "gemini/imagen-4.0-generate-001",
            "replicate/black-forest-labs/flux-1.1-pro",
            "openrouter/rekaai/reka-flash-3",
            "openrouter/rekaai/reka-flash-3:free",
            "openrouter/rekaai/rolm-ocr",
            "openrouter/google/gemini-2.5-flash",
            "claude-sonnet-4-5-20250929",
        ]
        mock_cost = {
            "gpt-4o-mini": {"litellm_provider": "openai", "mode": "chat"},
            "o3-mini": {"litellm_provider": "openai", "mode": "chat"},
            "o4-mini": {"litellm_provider": "openai", "mode": "chat"},
            "azure/gpt-4o": {"litellm_provider": "azure", "mode": "chat"},
            "gpt-4o-mini-preview": {"litellm_provider": "openai", "mode": "chat"},
            "gemini/gemini-2.5-flash": {"litellm_provider": "gemini", "mode": "chat"},
            "gemini/gemini-3-flash-preview": {
                "litellm_provider": "gemini",
                "mode": "chat",
            },
            "gemini/gemini-3.1-pro-preview": {
                "litellm_provider": "gemini",
                "mode": "chat",
            },
            "gemini/imagen-4.0-generate-001": {
                "litellm_provider": "gemini",
                "mode": "image_generation",
            },
            "replicate/black-forest-labs/flux-1.1-pro": {
                "litellm_provider": "replicate",
                "mode": "image_generation",
            },
            "openrouter/rekaai/reka-flash-3": {
                "litellm_provider": "openrouter",
                "mode": "chat",
            },
            "openrouter/rekaai/reka-flash-3:free": {
                "litellm_provider": "openrouter",
                "mode": "chat",
            },
            "openrouter/rekaai/rolm-ocr": {
                "litellm_provider": "openrouter",
                "mode": "chat",
            },
            "openrouter/google/gemini-2.5-flash": {
                "litellm_provider": "openrouter",
                "mode": "chat",
            },
            "claude-sonnet-4-5-20250929": {
                "litellm_provider": "anthropic",
                "mode": "chat",
            },
        }

        with (
            patch(
                "notewise.ui.setup_wizard._load_bundled_model_snapshot",
                return_value={},
            ),
            patch("litellm.model_list", mock_models, create=True),
            patch("litellm.model_cost", mock_cost, create=True),
        ):
            models = get_available_models()

        assert models["openai"] == [
            "gpt-4o-mini",
            "gpt-4o-mini-preview",
            "o3-mini",
            "o4-mini",
        ]
        assert models["gemini"] == [
            "gemini/gemini-2.5-flash",
            "gemini/gemini-3-flash-preview",
            "gemini/gemini-3.1-pro-preview",
        ]
        assert "openrouter/rekaai/reka-flash-3" in models["openrouter"]
        assert "openrouter/rekaai/reka-flash-3:free" in models["openrouter"]
        assert "openrouter/rekaai/rolm-ocr" not in models["openrouter"]
        assert "replicate/black-forest-labs/flux-1.1-pro" not in str(models)
        assert models["anthropic"] == ["claude-sonnet-4-5-20250929"]
        assert "mistral" not in models

    def test_get_available_models_includes_model_cost_only_response_models(self):
        """Models present only in LiteLLM metadata should still appear in setup."""
        mock_cost = {
            "chatgpt/gpt-5.4": {
                "litellm_provider": "chatgpt",
                "mode": "responses",
            },
            "chatgpt/gpt-5.4-pro": {
                "litellm_provider": "chatgpt",
                "mode": "responses",
            },
            "chatgpt/gpt-5.1-codex-mini": {
                "litellm_provider": "chatgpt",
                "mode": "responses",
            },
            "chatgpt/gpt-5.1-codex-max": {
                "litellm_provider": "chatgpt",
                "mode": "responses",
            },
            "openai/gpt-4o-audio-preview": {
                "litellm_provider": "openai",
                "mode": "chat",
            },
        }

        with (
            patch(
                "notewise.ui.setup_wizard._load_bundled_model_snapshot",
                return_value={},
            ),
            patch("litellm.model_list", [], create=True),
            patch("litellm.model_cost", mock_cost, create=True),
        ):
            models = get_available_models()

        assert "chatgpt/gpt-5.4" in models["chatgpt"]
        assert "chatgpt/gpt-5.4-pro" in models["chatgpt"]
        assert "chatgpt/gpt-5.1-codex-mini" not in models["chatgpt"]
        assert "chatgpt/gpt-5.1-codex-max" not in models["chatgpt"]
        assert "openai" not in models

    def test_get_available_models_applies_provider_exclusions_to_unprefixed_models(
        self,
    ):
        """Provider metadata should exclude unsafe unprefixed model names."""
        mock_models = ["gpt-5.1-codex"]
        mock_cost = {
            "gpt-5.1-codex": {
                "litellm_provider": "chatgpt",
                "mode": "chat",
            },
        }

        with (
            patch(
                "notewise.ui.setup_wizard._load_bundled_model_snapshot",
                return_value={},
            ),
            patch("litellm.model_list", mock_models, create=True),
            patch("litellm.model_cost", mock_cost, create=True),
        ):
            models = get_available_models()

        assert "chatgpt" not in models


class TestInteractiveFlow:
    """Test interactive prompts."""

    def test_select_provider(self):
        """Test provider selection."""
        # Mock Prompt.ask to return '1' (first in list)
        # Note: dict ordering is insertion ordered in modern python.
        # The function sorts providers_list based on keys in
        # PROVIDER_CONFIG order check.
        # PROVIDER_CONFIG is defined in module. "gemini" is usually first.

        # Let's patch PROVIDER_CONFIG to have deterministic order for test
        test_config = {
            "p1": {"name": "P1", "keywords": []},
            "p2": {"name": "P2", "keywords": []},
        }

        with (
            patch("notewise.ui.setup_wizard.PROVIDER_CONFIG", test_config),
            patch("rich.prompt.Prompt.ask", return_value="2"),
        ):
            result = select_provider({"p1": [], "p2": []})
            assert result == "p2"

    def test_select_model_pagination(self):
        """Test model selection with pagination."""
        # Create list of 25 models
        models = {"p1": [f"model-{i}" for i in range(25)]}

        # Sequence of inputs: 'n' (next page), 'p' (prev page), '1'
        # (select first model 'model-0')
        inputs = ["n", "p", "1"]

        with (
            patch("notewise.ui.setup_wizard.PROVIDER_CONFIG", {"p1": {"name": "P1"}}),
            patch("rich.prompt.Prompt.ask", side_effect=inputs),
        ):
            selected = select_model("p1", models)
            assert selected == "model-0"

    def test_select_model_gemini_prefix(self):
        """Test Gemini prefix addition."""
        models = {"gemini": ["gemini-1.5-pro"]}

        with (
            patch(
                "notewise.ui.setup_wizard.PROVIDER_CONFIG",
                {"gemini": {"name": "Google"}},
            ),
            patch("rich.prompt.Prompt.ask", return_value="1"),
        ):
            selected = select_model("gemini", models)
            assert selected == "gemini/gemini-1.5-pro"

    def test_select_model_invalid_input_is_visible(self):
        """Unexpected model input should print guidance and re-prompt."""
        mock_console = MagicMock()
        models = {"p1": ["model-0"]}

        with (
            patch("notewise.ui.setup_wizard.PROVIDER_CONFIG", {"p1": {"name": "P1"}}),
            patch("rich.prompt.Prompt.ask", side_effect=["wat", "1"]),
        ):
            selected = select_model("p1", models, console=mock_console)

        assert selected == "model-0"
        mock_console.print.assert_any_call(
            "[red]Invalid choice. Enter a model number or use n/p to navigate.[/red]"
        )

    def test_get_api_key_new(self):
        """Test entering a new API key."""
        with (
            patch("rich.prompt.Confirm.ask", return_value=False),
            patch("rich.prompt.Prompt.ask", return_value="sk-new-valid-key-12345"),
        ):
            key = get_api_key("openai", existing_key="old-key")
            assert key == "sk-new-valid-key-12345"

    def test_get_api_key_existing(self):
        """Test using existing API key."""
        with patch("rich.prompt.Confirm.ask", return_value=True):
            key = get_api_key("openai", existing_key="old-key")
            assert key == "old-key"

    def test_get_api_key_retry(self):
        """Test retry on invalid key."""
        # First return invalid (short), then valid
        inputs = ["short", "sk-valid-length-key-12345"]

        with (
            patch("rich.prompt.Confirm.ask", return_value=False),
            patch("rich.prompt.Prompt.ask", side_effect=inputs),
        ):
            key = get_api_key("openai")
            assert key == "sk-valid-length-key-12345"


class TestWizardOrchestration:
    """Test the main wizard flow."""

    def test_run_setup_wizard_full_flow(self):
        """Test full setup flow."""
        # Mocks
        with (
            patch("notewise.ui.setup_wizard.load_config", return_value={}),
            patch(
                "notewise.ui.setup_wizard.get_available_models",
                return_value={"gemini": ["gemini-pro"]},
            ),
            patch("notewise.ui.setup_wizard.select_provider", return_value="gemini"),
            patch(
                "notewise.ui.setup_wizard.select_model",
                return_value="gemini/gemini-pro",
            ),
            patch("notewise.ui.setup_wizard.get_api_key", return_value="new-key"),
            patch("rich.prompt.Prompt.ask", side_effect=["/custom/out", "10"]),
            patch("notewise.ui.setup_wizard.save_config") as mock_save,
        ):
            config = run_setup_wizard(force=True)

            assert config["DEFAULT_MODEL"] == "gemini/gemini-pro"
            assert config["GEMINI_API_KEY"] == "new-key"
            assert config["OUTPUT_DIR"] == "/custom/out"
            assert config["MAX_CONCURRENT_VIDEOS"] == "10"

            mock_save.assert_called_once()

    def test_run_setup_wizard_stops_when_model_catalog_empty(self):
        """Wizard should stop before provider prompts when no models are available."""
        console = MagicMock()
        current_config = {"DEFAULT_MODEL": "gemini/gemini-pro"}

        with (
            patch("notewise.ui.setup_wizard.load_config", return_value=current_config),
            patch("notewise.ui.setup_wizard.get_available_models", return_value={}),
            patch("notewise.ui.setup_wizard.select_provider") as mock_provider,
            patch("notewise.ui.setup_wizard.save_config") as mock_save,
        ):
            result = run_setup_wizard(force=True, console=console)

        assert result == current_config
        mock_provider.assert_not_called()
        mock_save.assert_not_called()
        rendered = "".join(str(call.args[0]) for call in console.print.call_args_list)
        assert "No setup-safe model catalog is available right now." in rendered

    def test_run_setup_wizard_skips_api_key_for_oauth_provider(self):
        """OAuth/device-flow providers should not prompt for static API keys."""
        with (
            patch("notewise.ui.setup_wizard.load_config", return_value={}),
            patch(
                "notewise.ui.setup_wizard.get_available_models",
                return_value={"chatgpt": ["chatgpt/gpt-5-codex"]},
            ),
            patch("notewise.ui.setup_wizard.select_provider", return_value="chatgpt"),
            patch(
                "notewise.ui.setup_wizard.select_model",
                return_value="chatgpt/gpt-5-codex",
            ),
            patch("notewise.ui.setup_wizard.get_api_key") as mock_api_key,
            patch("rich.prompt.Confirm.ask", return_value=False),
            patch("rich.prompt.Prompt.ask", side_effect=["/custom/out", "4"]),
            patch("notewise.ui.setup_wizard.run_oauth_login") as mock_login,
            patch("notewise.ui.setup_wizard.save_config") as mock_save,
        ):
            config = run_setup_wizard(force=True)

        assert config == {
            "DEFAULT_MODEL": "chatgpt/gpt-5-codex",
            "OUTPUT_DIR": "/custom/out",
            "MAX_CONCURRENT_VIDEOS": "4",
        }
        mock_api_key.assert_not_called()
        mock_login.assert_not_called()
        mock_save.assert_called_once()
        assert mock_save.call_args.args[0] == config

    def test_run_setup_wizard_reprompts_for_invalid_concurrency(self):
        """Wizard should reject invalid concurrency input before saving config."""
        with (
            patch("notewise.ui.setup_wizard.load_config", return_value={}),
            patch(
                "notewise.ui.setup_wizard.get_available_models",
                return_value={"gemini": ["gemini-pro"]},
            ),
            patch("notewise.ui.setup_wizard.select_provider", return_value="gemini"),
            patch(
                "notewise.ui.setup_wizard.select_model",
                return_value="gemini/gemini-pro",
            ),
            patch("notewise.ui.setup_wizard.get_api_key", return_value="new-key"),
            patch(
                "rich.prompt.Prompt.ask",
                side_effect=["/custom/out", "zero", "0", "7"],
            ),
            patch("notewise.ui.setup_wizard.save_config") as mock_save,
        ):
            config = run_setup_wizard(force=True)

        assert config["MAX_CONCURRENT_VIDEOS"] == "7"
        mock_save.assert_called_once()

    def test_run_setup_wizard_strips_existing_legacy_auth_settings(self):
        """Returned config should drop removed YouTube auth keys."""
        existing_config = {
            "DEFAULT_MODEL": "gemini/gemini-pro",
            "GEMINI_API_KEY": "old-key",
            "OUTPUT_DIR": "/existing/out",
            "MAX_CONCURRENT_VIDEOS": "4",
            "YOUTUBE_USE_OAUTH": "true",
            "YOUTUBE_SAVE_OAUTH_TOKEN": "true",
            "YOUTUBE_OAUTH_TOKEN_FILE": "/existing/token.json",
            "YOUTUBE_AUTO_REFRESH_OAUTH_TOKEN": "false",
        }

        with (
            patch("notewise.ui.setup_wizard.load_config", return_value=existing_config),
            patch(
                "notewise.ui.setup_wizard.get_available_models",
                return_value={"gemini": ["gemini-pro"]},
            ),
            patch("notewise.ui.setup_wizard.select_provider", return_value="gemini"),
            patch(
                "notewise.ui.setup_wizard.select_model",
                return_value="gemini/gemini-pro",
            ),
            patch("notewise.ui.setup_wizard.get_api_key", return_value="existing-key"),
            patch("rich.prompt.Prompt.ask", side_effect=["/custom/out", "10"]),
            patch("notewise.ui.setup_wizard.save_config") as mock_save,
        ):
            config = run_setup_wizard(force=True)

        assert "YOUTUBE_USE_OAUTH" not in config
        assert "YOUTUBE_SAVE_OAUTH_TOKEN" not in config
        assert "YOUTUBE_OAUTH_TOKEN_FILE" not in config
        assert "YOUTUBE_AUTO_REFRESH_OAUTH_TOKEN" not in config
        mock_save.assert_called_once()

    def test_run_setup_wizard_skip_existing(self):
        """Test skipping setup if config exists."""
        with (
            patch(
                "notewise.ui.setup_wizard.load_config",
                return_value={"exists": "true"},
            ),
            patch("rich.prompt.Confirm.ask", return_value=False),
        ):  # Do not reconfigure
            config = run_setup_wizard(force=False)
            assert config == {"exists": "true"}

    def test_run_setup_wizard_uses_injected_console(self):
        """Wizard should thread an injected console through helper calls."""
        mock_console = MagicMock()

        with (
            patch("notewise.ui.setup_wizard.load_config", return_value={}),
            patch(
                "notewise.ui.setup_wizard.get_available_models",
                return_value={"gemini": ["gemini-pro"]},
            ) as mock_models,
            patch(
                "notewise.ui.setup_wizard.select_provider",
                return_value="gemini",
            ) as mock_provider,
            patch(
                "notewise.ui.setup_wizard.select_model",
                return_value="gemini/gemini-pro",
            ) as mock_model,
            patch(
                "notewise.ui.setup_wizard.get_api_key",
                return_value="new-key",
            ) as mock_api_key,
            patch("rich.prompt.Prompt.ask", side_effect=["/custom/out", "10"]),
            patch("notewise.ui.setup_wizard.save_config") as mock_save,
        ):
            config = run_setup_wizard(force=True, console=mock_console)

        assert config["DEFAULT_MODEL"] == "gemini/gemini-pro"
        mock_models.assert_called_once_with(console=mock_console)
        mock_provider.assert_called_once_with(
            {"gemini": ["gemini-pro"]},
            console=mock_console,
        )
        mock_model.assert_called_once_with(
            "gemini",
            {"gemini": ["gemini-pro"]},
            console=mock_console,
        )
        mock_api_key.assert_called_once_with(
            "gemini",
            None,
            console=mock_console,
        )
        mock_save.assert_called_once_with(
            {
                "DEFAULT_MODEL": "gemini/gemini-pro",
                "GEMINI_API_KEY": "new-key",
                "OUTPUT_DIR": "/custom/out",
                "MAX_CONCURRENT_VIDEOS": "10",
            },
            console=mock_console,
        )
