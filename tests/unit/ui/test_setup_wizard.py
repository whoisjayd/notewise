"""Tests for the setup wizard."""

from unittest.mock import ANY, AsyncMock, MagicMock, patch

from notewise.errors import ConfigurationError, CustomEndpointError
from notewise.llm.custom_endpoint import (
    CustomEndpointProfile,
    parse_custom_endpoint_profiles,
    serialize_custom_endpoint_profiles,
)
from notewise.ui.setup_wizard import (
    get_api_key,
    get_available_models,
    get_config_path,
    load_config,
    run_custom_endpoint_manager,
    run_setup_wizard,
    save_config,
    select_config_category,
    select_model,
    select_provider,
    show_current_config,
)
from notewise.utils import strip_wrapped_quotes


class TestConfigIO:
    """Test configuration loading and saving against the config.db backend."""

    def test_load_config_not_exists(self, tmp_path, monkeypatch):
        """Loading config with no config.db yet should return an empty dict."""
        monkeypatch.setenv("NOTEWISE_HOME", str(tmp_path / ".notewise"))

        assert load_config() == {}

    def test_config_path_points_at_config_db(self, tmp_path, monkeypatch):
        """get_config_path should resolve to config.db under NOTEWISE_HOME."""
        home = tmp_path / ".notewise"
        monkeypatch.setenv("NOTEWISE_HOME", str(home))

        assert get_config_path() == home / "config.db"

    def test_save_and_load_config_round_trip(self, tmp_path, monkeypatch):
        """Saved keys should be readable afterward, merged with prior keys."""
        monkeypatch.setenv("NOTEWISE_HOME", str(tmp_path / ".notewise"))

        save_config({"OLD_KEY": "old_val"})
        save_config({"NEW_KEY": "new_val", "DEFAULT_MODEL": "new_model"})

        config = load_config()
        assert config["OLD_KEY"] == "old_val"
        assert config["NEW_KEY"] == "new_val"
        assert config["DEFAULT_MODEL"] == "new_model"

    def test_save_config_strips_legacy_youtube_auth_keys(self, tmp_path, monkeypatch):
        """Saving config should remove legacy OAuth and cookie-era auth keys."""
        monkeypatch.setenv("NOTEWISE_HOME", str(tmp_path / ".notewise"))

        save_config(
            {
                "YOUTUBE_USE_OAUTH": "true",
                "YOUTUBE_SAVE_OAUTH_TOKEN": "true",
                "YOUTUBE_OAUTH_TOKEN_FILE": "/tmp/token.json",
                "YOUTUBE_AUTO_REFRESH_OAUTH_TOKEN": "false",
                "OLD_KEY": "old_val",
            }
        )
        save_config({"DEFAULT_MODEL": "new_model"})

        config = load_config()
        assert config["OLD_KEY"] == "old_val"
        assert config["DEFAULT_MODEL"] == "new_model"
        assert "YOUTUBE_USE_OAUTH" not in config
        assert "YOUTUBE_SAVE_OAUTH_TOKEN" not in config
        assert "YOUTUBE_OAUTH_TOKEN_FILE" not in config
        assert "YOUTUBE_AUTO_REFRESH_OAUTH_TOKEN" not in config

    def test_save_config_creates_config_db(self, tmp_path, monkeypatch):
        """save_config should create config.db under NOTEWISE_HOME."""
        monkeypatch.setenv("NOTEWISE_HOME", str(tmp_path / "state"))
        monkeypatch.delenv("DEFAULT_MODEL", raising=False)

        save_config({"DEFAULT_MODEL": "gemini/gemini-2.5-flash"})

        config_path = get_config_path()
        assert config_path.exists()
        assert load_config()["DEFAULT_MODEL"] == "gemini/gemini-2.5-flash"

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

    def test_show_current_config_masks_lowercase_secret_keys(self):
        """Lowercase secret keys (first-class in config.env) must be masked too."""
        console = MagicMock()
        with (
            patch(
                "notewise.ui.setup_wizard.load_config",
                return_value={"gemini_api_key": "AIzaExample123456789"},
            ),
            patch(
                "notewise.ui.setup_wizard.get_config_path",
                return_value=get_config_path(),
            ),
        ):
            show_current_config(console=console)

        rendered = "".join(str(call.args[0]) for call in console.print.call_args_list)
        assert "AIzaExample123456789" not in rendered

    def test_show_current_config_masks_mixed_case_secret_keys(self):
        """Mixed-case secret keys must be gated case-insensitively."""
        console = MagicMock()
        with (
            patch(
                "notewise.ui.setup_wizard.load_config",
                return_value={"Api_Key": "mixed-case-secret-value"},
            ),
            patch(
                "notewise.ui.setup_wizard.get_config_path",
                return_value=get_config_path(),
            ),
        ):
            show_current_config(console=console)

        rendered = "".join(str(call.args[0]) for call in console.print.call_args_list)
        assert "mixed-case-secret-value" not in rendered

    def test_show_current_config_displays_benign_keys_raw(self):
        """Benign non-secret keys should still display their raw values."""
        import io

        from rich.console import Console

        buffer = io.StringIO()
        console = Console(file=buffer, force_terminal=False, width=200)
        with (
            patch(
                "notewise.ui.setup_wizard.load_config",
                return_value={"OUTPUT_DIR": "/tmp/notes"},
            ),
            patch(
                "notewise.ui.setup_wizard.get_config_path",
                return_value=get_config_path(),
            ),
        ):
            show_current_config(console=console)

        assert "/tmp/notes" in buffer.getvalue()

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
        mock_model_cost = {
            "gpt-4": {"litellm_provider": "openai", "mode": "chat"},
            "gpt-3.5-turbo": {"litellm_provider": "openai", "mode": "chat"},
            "claude-3-opus": {"litellm_provider": "anthropic", "mode": "chat"},
            "gemini/gemini-pro": {"litellm_provider": "gemini", "mode": "chat"},
        }

        with (
            patch(
                "notewise.ui.setup_wizard._load_bundled_model_snapshot",
                return_value={},
            ),
            patch("litellm.model_list", mock_models, create=True),
            patch("litellm.model_cost", mock_model_cost),
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

    def test_select_provider_lists_saved_custom_endpoint_before_add_action(self):
        """Saved endpoints are visible provider choices ahead of the add action."""
        from rich.console import Console

        console = Console(record=True, force_terminal=False, width=100)
        profile = CustomEndpointProfile(
            name="office",
            base_url="https://office.example/v1",
            api_key="office-key",
        )
        with (
            patch(
                "notewise.ui.setup_wizard.PROVIDER_CONFIG",
                {"p1": {"name": "P1", "keywords": []}},
            ),
            patch("rich.prompt.Prompt.ask", return_value="2"),
        ):
            result = select_provider(
                {"p1": []},
                custom_profiles=(profile,),
                console=console,
            )

        assert result == "office"
        rendered = console.export_text()
        assert "office" in rendered
        assert "Custom endpoint" in rendered
        assert rendered.index("office") < rendered.index(
            "Add custom OpenAI-compatible endpoint"
        )

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
        """Blank input should print guidance and re-prompt."""
        mock_console = MagicMock()
        models = {"p1": ["model-0"]}

        with (
            patch("notewise.ui.setup_wizard.PROVIDER_CONFIG", {"p1": {"name": "P1"}}),
            patch("rich.prompt.Prompt.ask", side_effect=["", "1"]),
        ):
            selected = select_model("p1", models, console=mock_console)

        assert selected == "model-0"
        mock_console.print.assert_any_call(
            "[red]Invalid choice. Enter a model number, search text, "
            "or n/p to navigate.[/red]"
        )

    def test_select_model_search_filters_by_substring(self):
        """Typing non-numeric text should filter the list before selecting."""
        models = {"p1": ["gemini-2.5-flash", "gemini-2.5-pro", "gpt-4o-mini", "gpt-4o"]}

        with (
            patch("notewise.ui.setup_wizard.PROVIDER_CONFIG", {"p1": {"name": "P1"}}),
            patch("rich.prompt.Prompt.ask", side_effect=["gemini", "2"]),
        ):
            selected = select_model("p1", models)

        assert selected == "gemini-2.5-pro"

    def test_select_model_search_with_no_matches_reprompts(self):
        """A search with no matches should warn and keep the prior list."""
        mock_console = MagicMock()
        models = {"p1": ["model-0", "model-1"]}

        with (
            patch("notewise.ui.setup_wizard.PROVIDER_CONFIG", {"p1": {"name": "P1"}}),
            patch("rich.prompt.Prompt.ask", side_effect=["zzz-no-match", "1"]),
        ):
            selected = select_model("p1", models, console=mock_console)

        assert selected == "model-0"
        assert any(
            "No models match" in str(call.args[0])
            for call in mock_console.print.call_args_list
        )

    def test_select_model_search_clear_restores_full_list(self):
        """'c' after a search should restore the unfiltered model list."""
        models = {"p1": ["model-0", "model-1", "other-2"]}

        with (
            patch("notewise.ui.setup_wizard.PROVIDER_CONFIG", {"p1": {"name": "P1"}}),
            patch("rich.prompt.Prompt.ask", side_effect=["model", "c", "3"]),
        ):
            selected = select_model("p1", models)

        assert selected == "other-2"

    def test_select_config_category_returns_chosen_name(self):
        categories = {
            "Model & Generation": ("DEFAULT_MODEL",),
            "Output": ("OUTPUT_DIR",),
        }

        with patch("rich.prompt.Prompt.ask", return_value="2"):
            selected = select_config_category(categories)

        assert selected == "Output"

    def test_select_config_category_quit_returns_none(self):
        categories = {"Model & Generation": ("DEFAULT_MODEL",)}

        with patch("rich.prompt.Prompt.ask", return_value="q"):
            selected = select_config_category(categories)

        assert selected is None

    def test_select_config_category_invalid_input_reprompts(self):
        mock_console = MagicMock()
        categories = {"Model & Generation": ("DEFAULT_MODEL",)}

        with patch("rich.prompt.Prompt.ask", side_effect=["nope", "1"]):
            selected = select_config_category(categories, console=mock_console)

        assert selected == "Model & Generation"
        mock_console.print.assert_any_call(
            "[red]Invalid choice. Enter a category number or 'q'.[/red]"
        )

    def test_run_custom_endpoint_manager_update_rejects_invalid_index(self):
        """An out-of-range or non-numeric index should warn and cancel, not crash."""
        from notewise.config import get_config_db_path
        from notewise.storage import config_store

        db_path = get_config_db_path()
        config_store.upsert_custom_endpoint(
            db_path,
            CustomEndpointProfile(
                name="office", base_url="https://old.example/v1", api_key="old-key"
            ),
        )

        mock_console = MagicMock()
        with patch("rich.prompt.Prompt.ask", side_effect=["u", "99", "q"]):
            run_custom_endpoint_manager(console=mock_console)

        assert config_store.list_custom_endpoints(db_path) == (
            CustomEndpointProfile(
                name="office", base_url="https://old.example/v1", api_key="old-key"
            ),
        )
        mock_console.print.assert_any_call(
            "[red]Invalid choice. Enter a number 1-1.[/red]"
        )

    def test_run_custom_endpoint_manager_add_selects_model_from_list(self):
        """Confirming model selection should list discovered models by index."""
        from notewise.config import get_config_db_path
        from notewise.storage import config_store

        with (
            patch(
                "notewise.llm.custom_endpoint.discover_openai_compatible_models",
                return_value=["vendor/model-a", "vendor/model-b"],
            ),
            patch(
                "notewise.llm.custom_endpoint.verify_openai_compatible_model",
                new_callable=AsyncMock,
            ) as verify,
            patch("rich.prompt.Confirm.ask", return_value=True),
            patch(
                "rich.prompt.Prompt.ask",
                side_effect=[
                    "a",
                    "Office",
                    "https://new.example/",
                    "new-secret",
                    "2",
                    "q",
                ],
            ),
        ):
            run_custom_endpoint_manager()

        verify.assert_awaited_once_with(
            "https://new.example/v1", "new-secret", "vendor/model-b"
        )
        saved = config_store.list_custom_endpoints(get_config_db_path())
        assert saved == (
            CustomEndpointProfile(
                name="office",
                base_url="https://new.example/v1",
                api_key="new-secret",
            ),
        )

    def test_run_custom_endpoint_manager_adds_new_endpoint(self):
        """'a' should discover, verify, and persist a brand-new endpoint."""
        from notewise.config import get_config_db_path
        from notewise.storage import config_store

        with (
            patch(
                "notewise.llm.custom_endpoint.discover_openai_compatible_models",
                return_value=["vendor/new-model"],
            ),
            patch(
                "notewise.llm.custom_endpoint.verify_openai_compatible_model",
                new_callable=AsyncMock,
            ),
            patch("rich.prompt.Confirm.ask", return_value=False),
            patch(
                "rich.prompt.Prompt.ask",
                side_effect=[
                    "a",
                    "Office",
                    "https://new.example/",
                    "new-secret",
                    "vendor/new-model",
                    "q",
                ],
            ),
        ):
            run_custom_endpoint_manager()

        saved = config_store.list_custom_endpoints(get_config_db_path())
        assert saved == (
            CustomEndpointProfile(
                name="office",
                base_url="https://new.example/v1",
                api_key="new-secret",
            ),
        )

    def test_run_custom_endpoint_manager_updates_existing_endpoint(self):
        """'u' should re-verify and replace only the targeted endpoint."""
        from notewise.config import get_config_db_path
        from notewise.storage import config_store

        db_path = get_config_db_path()
        config_store.upsert_custom_endpoint(
            db_path,
            CustomEndpointProfile(
                name="office", base_url="https://old.example/v1", api_key="old-key"
            ),
        )

        with (
            patch(
                "notewise.llm.custom_endpoint.discover_openai_compatible_models",
                return_value=["vendor/new-model"],
            ),
            patch(
                "notewise.llm.custom_endpoint.verify_openai_compatible_model",
                new_callable=AsyncMock,
            ),
            patch("rich.prompt.Confirm.ask", return_value=False),
            patch(
                "rich.prompt.Prompt.ask",
                side_effect=[
                    "u",
                    "1",
                    "https://new.example/",
                    "",
                    "vendor/new-model",
                    "q",
                ],
            ),
        ):
            run_custom_endpoint_manager()

        saved = config_store.list_custom_endpoints(db_path)
        assert saved == (
            CustomEndpointProfile(
                name="office",
                base_url="https://new.example/v1",
                api_key="old-key",
            ),
        )

    def test_run_custom_endpoint_manager_delete_blocked_by_default_model(self):
        """Deleting the endpoint DEFAULT_MODEL uses must be refused, not applied."""
        from notewise.config import get_config_db_path
        from notewise.storage import config_store

        db_path = get_config_db_path()
        config_store.upsert_custom_endpoint(
            db_path,
            CustomEndpointProfile(
                name="office", base_url="https://old.example/v1", api_key="old-key"
            ),
        )
        save_config({"DEFAULT_MODEL": "office/vendor-model"})

        mock_console = MagicMock()
        with patch("rich.prompt.Prompt.ask", side_effect=["d", "1", "q"]):
            run_custom_endpoint_manager(console=mock_console)

        assert config_store.list_custom_endpoints(db_path) == (
            CustomEndpointProfile(
                name="office", base_url="https://old.example/v1", api_key="old-key"
            ),
        )
        mock_console.print.assert_any_call(
            "[red]Cannot delete 'office' while DEFAULT_MODEL uses it.[/red]"
        )

    def test_run_custom_endpoint_manager_deletes_after_confirmation(self):
        """Confirmed 'd' should remove the endpoint from config.db."""
        from notewise.config import get_config_db_path
        from notewise.storage import config_store

        db_path = get_config_db_path()
        config_store.upsert_custom_endpoint(
            db_path,
            CustomEndpointProfile(
                name="office", base_url="https://old.example/v1", api_key="old-key"
            ),
        )

        with (
            patch("rich.prompt.Prompt.ask", side_effect=["d", "1", "q"]),
            patch("rich.prompt.Confirm.ask", return_value=True),
        ):
            run_custom_endpoint_manager()

        assert config_store.list_custom_endpoints(db_path) == ()

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

    def test_get_api_key_masks_existing_key_with_mask_secret(self):
        """Existing key prompt should use the shared mask_secret helper."""
        existing = "sk-existing-api-key-123456789"

        with patch("rich.prompt.Confirm.ask", return_value=True) as confirm_ask:
            key = get_api_key("openai", existing_key=existing)

        prompt = confirm_ask.call_args.args[0]
        assert "sk-exi...6789" in prompt
        assert existing not in prompt
        assert key == existing


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

    def test_run_setup_wizard_adds_second_custom_endpoint_without_losing_first(
        self, mocker
    ):
        """Adding an endpoint preserves the full pre-existing registry."""
        first = CustomEndpointProfile(
            name="office",
            base_url="https://office.example/v1",
            api_key="office-key",
        )
        second = CustomEndpointProfile(
            name="home",
            base_url="https://home.example/v1",
            api_key="home-key",
        )
        mocker.patch(
            "notewise.ui.setup_wizard.load_config",
            return_value={
                "CUSTOM_LLM_ENDPOINTS": serialize_custom_endpoint_profiles((first,))
            },
        )
        mocker.patch("notewise.ui.setup_wizard.get_available_models", return_value={})
        mocker.patch(
            "notewise.ui.setup_wizard.select_provider",
            return_value="custom_openai_compatible",
        )
        mocker.patch(
            "notewise.ui.setup_wizard._setup_custom_openai_compatible_endpoint",
            return_value=("home/home-model", second),
        )
        mock_save = mocker.patch("notewise.ui.setup_wizard.save_config")
        mocker.patch("rich.prompt.Prompt.ask", side_effect=["/custom/out", "4"])

        result = run_setup_wizard(force=True)

        assert result["DEFAULT_MODEL"] == "home/home-model"
        assert parse_custom_endpoint_profiles(result["CUSTOM_LLM_ENDPOINTS"]) == (
            first,
            second,
        )
        assert parse_custom_endpoint_profiles(
            mock_save.call_args.args[0]["CUSTOM_LLM_ENDPOINTS"]
        ) == (first, second)

    def test_run_setup_wizard_replaces_endpoint_after_verification(self, mocker):
        """A same-name endpoint is replaced only after its model verifies."""
        old_profile = CustomEndpointProfile(
            name="internal-endpoint",
            base_url="https://old-endpoint.example/v1",
            api_key="old-endpoint-key",
        )
        mocker.patch(
            "notewise.ui.setup_wizard.load_config",
            return_value={
                "CUSTOM_LLM_ENDPOINTS": serialize_custom_endpoint_profiles(
                    (old_profile,)
                )
            },
        )
        mocker.patch(
            "notewise.ui.setup_wizard.get_available_models",
            return_value={"gemini": ["gemini-pro"]},
        )
        mocker.patch(
            "notewise.ui.setup_wizard.select_provider",
            return_value="custom_openai_compatible",
        )
        select_model = mocker.patch(
            "notewise.ui.setup_wizard.select_model",
            return_value="vendor/model-id",
        )
        mocker.patch(
            "notewise.llm.custom_endpoint.normalize_custom_model_prefix",
            return_value="internal-endpoint",
        )
        mocker.patch(
            "notewise.llm.custom_endpoint.normalize_openai_base_url",
            return_value="https://endpoint.example/v1",
        )
        discover_models = mocker.patch(
            "notewise.llm.custom_endpoint.discover_openai_compatible_models",
            return_value=["vendor/model-id"],
        )
        mock_save = mocker.patch("notewise.ui.setup_wizard.save_config")

        async def verify_model(*args: object) -> None:
            mock_save.assert_not_called()

        verify_model_mock = mocker.patch(
            "notewise.llm.custom_endpoint.verify_openai_compatible_model",
            new=AsyncMock(side_effect=verify_model),
        )
        mocker.patch(
            "rich.prompt.Prompt.ask",
            side_effect=[
                "Internal endpoint",
                "https://endpoint.example",
                "endpoint-secret",
                "/custom/out",
                "3",
            ],
        )

        result = run_setup_wizard(force=True)

        discover_models.assert_called_once_with(
            "https://endpoint.example/v1",
            "endpoint-secret",
        )
        assert select_model.call_args.args == (
            "internal-endpoint",
            {"internal-endpoint": ["vendor/model-id"]},
        )
        verify_model_mock.assert_awaited_once_with(
            "https://endpoint.example/v1",
            "endpoint-secret",
            "vendor/model-id",
        )
        assert result["DEFAULT_MODEL"] == "internal-endpoint/vendor/model-id"
        assert parse_custom_endpoint_profiles(result["CUSTOM_LLM_ENDPOINTS"]) == (
            CustomEndpointProfile(
                name="internal-endpoint",
                base_url="https://endpoint.example/v1",
                api_key="endpoint-secret",
            ),
        )

    def test_run_setup_wizard_uses_selected_saved_endpoint_credentials(self, mocker):
        """Selecting a saved profile refreshes and verifies with its own key."""
        profile = CustomEndpointProfile(
            name="office",
            base_url="https://office.example/v1",
            api_key="office-key",
        )
        current_config = {
            "CUSTOM_LLM_ENDPOINTS": serialize_custom_endpoint_profiles((profile,))
        }
        mocker.patch(
            "notewise.ui.setup_wizard.load_config",
            return_value=current_config,
        )
        mocker.patch(
            "notewise.ui.setup_wizard.get_available_models",
            return_value={"gemini": ["gemini-pro"]},
        )
        mocker.patch(
            "notewise.ui.setup_wizard.select_provider",
            return_value="office",
        )
        select_model = mocker.patch(
            "notewise.ui.setup_wizard.select_model",
            return_value="vendor/model-id",
        )
        discover_models = mocker.patch(
            "notewise.llm.custom_endpoint.discover_openai_compatible_models",
            return_value=["vendor/model-id"],
        )
        verify_model = mocker.patch(
            "notewise.llm.custom_endpoint.verify_openai_compatible_model",
            new=AsyncMock(),
        )
        mock_save = mocker.patch("notewise.ui.setup_wizard.save_config")
        mocker.patch("rich.prompt.Prompt.ask", side_effect=["/custom/out", "3"])

        result = run_setup_wizard(force=True)

        discover_models.assert_called_once_with(
            "https://office.example/v1",
            "office-key",
        )
        select_model.assert_called_once_with(
            "office",
            {"office": ["vendor/model-id"]},
            console=ANY,
        )
        verify_model.assert_awaited_once_with(
            "https://office.example/v1",
            "office-key",
            "vendor/model-id",
        )
        assert result["DEFAULT_MODEL"] == "office/vendor/model-id"
        assert mock_save.call_args.args[0] == {
            "DEFAULT_MODEL": "office/vendor/model-id",
            "OUTPUT_DIR": "/custom/out",
            "MAX_CONCURRENT_VIDEOS": "3",
        }

    def test_run_setup_wizard_replaces_duplicate_endpoint_only_after_validation(
        self, mocker
    ):
        """A same-name replacement retains the old profile when discovery fails."""
        existing = CustomEndpointProfile(
            name="office",
            base_url="https://old-office.example/v1",
            api_key="old-office-key",
        )
        current_config = {
            "DEFAULT_MODEL": "office/old-model",
            "CUSTOM_LLM_ENDPOINTS": serialize_custom_endpoint_profiles((existing,)),
        }
        console = MagicMock()
        mocker.patch(
            "notewise.ui.setup_wizard.load_config",
            return_value=current_config,
        )
        mocker.patch(
            "notewise.ui.setup_wizard.get_available_models",
            return_value={"gemini": ["gemini-pro"]},
        )
        mocker.patch(
            "notewise.ui.setup_wizard.select_provider",
            return_value="custom_openai_compatible",
        )
        mocker.patch(
            "notewise.llm.custom_endpoint.discover_openai_compatible_models",
            side_effect=CustomEndpointError("Could not discover models."),
        )
        mock_save = mocker.patch("notewise.ui.setup_wizard.save_config")
        mocker.patch(
            "rich.prompt.Prompt.ask",
            side_effect=["Office", "https://new-office.example", "new-key"],
        )

        result = run_setup_wizard(force=True, console=console)

        assert result == current_config
        assert parse_custom_endpoint_profiles(result["CUSTOM_LLM_ENDPOINTS"]) == (
            existing,
        )
        mock_save.assert_not_called()

    def test_run_setup_wizard_does_not_save_when_custom_verification_fails(
        self, mocker
    ):
        """Verification failure is visible and leaves configuration unchanged."""
        current_config = {"DEFAULT_MODEL": "gemini/gemini-pro"}
        console = MagicMock()
        mocker.patch(
            "notewise.ui.setup_wizard.load_config",
            return_value=current_config,
        )
        mocker.patch(
            "notewise.ui.setup_wizard.get_available_models",
            return_value={"gemini": ["gemini-pro"]},
        )
        mocker.patch(
            "notewise.ui.setup_wizard.select_provider",
            return_value="custom_openai_compatible",
        )
        mocker.patch(
            "notewise.llm.custom_endpoint.normalize_custom_model_prefix",
            return_value="internal-endpoint",
        )
        mocker.patch(
            "notewise.llm.custom_endpoint.normalize_openai_base_url",
            return_value="https://endpoint.example/v1",
        )
        mocker.patch(
            "notewise.llm.custom_endpoint.discover_openai_compatible_models",
            return_value=["vendor/model-id"],
        )
        mocker.patch(
            "notewise.ui.setup_wizard.select_model",
            return_value="vendor/model-id",
        )
        verify_model = mocker.patch(
            "notewise.llm.custom_endpoint.verify_openai_compatible_model",
            new=AsyncMock(
                side_effect=CustomEndpointError("Could not verify selected model.")
            ),
        )
        mock_save = mocker.patch("notewise.ui.setup_wizard.save_config")
        mocker.patch(
            "rich.prompt.Prompt.ask",
            side_effect=["Internal endpoint", "https://endpoint.example", "key"],
        )

        result = run_setup_wizard(force=True, console=console)

        assert result == current_config
        verify_model.assert_awaited_once_with(
            "https://endpoint.example/v1",
            "key",
            "vendor/model-id",
        )
        mock_save.assert_not_called()
        console.print.assert_any_call("[red]Could not verify selected model.[/red]")

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
            custom_profiles=(),
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
