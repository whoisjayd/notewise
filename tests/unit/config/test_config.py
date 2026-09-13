"""Tests for configuration management (Pydantic v2 BaseSettings)."""

from __future__ import annotations

import os

import pytest
from pydantic import ValidationError

from notewise import config as config_module
from notewise.config import AppSettings as Config
from notewise.config import UserConfigSource


class TestConfig:
    """Test AppSettings (Config) class."""

    def test_defaults(self, monkeypatch):
        """Default values are correct when env is clean."""
        monkeypatch.delenv("DEFAULT_MODEL", raising=False)
        monkeypatch.delenv("OUTPUT_DIR", raising=False)
        monkeypatch.delenv("MAX_CONCURRENT_VIDEOS", raising=False)
        cfg = Config()
        assert cfg.default_model == "gemini/gemini-2.5-flash"
        assert cfg.max_concurrent_videos == 5
        assert cfg.youtube_requests_per_minute == 10

    def test_load_from_env(self, monkeypatch):
        """Environment variables override defaults."""
        monkeypatch.setenv("GEMINI_API_KEY", "env_key")
        monkeypatch.setenv("DEFAULT_MODEL", "gpt-4o")
        cfg = Config()
        assert cfg.gemini_api_key == "env_key"
        assert cfg.default_model == "gpt-4o"

    def test_load_from_file(self, tmp_path, monkeypatch):
        """Config.env file is loaded and sets values."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("MAX_CONCURRENT_VIDEOS", raising=False)
        monkeypatch.setenv("NOTEWISE_HOME", str(tmp_path / ".notewise"))
        config_dir = tmp_path / ".notewise"
        config_dir.mkdir()
        (config_dir / "config.env").write_text(
            "OPENAI_API_KEY=file_key\nMAX_CONCURRENT_VIDEOS=10"
        )
        cfg = Config()
        assert cfg.openai_api_key == "file_key"
        assert cfg.max_concurrent_videos == 10

    def test_custom_endpoint_registry_loads_from_user_config_without_key_leak(
        self, tmp_path, monkeypatch
    ):
        """Saved endpoint credentials remain scoped to AppSettings."""
        endpoints = (
            '[{"name":"local-endpoint","base_url":"https://llm.example.test/v1",'
            '"api_key":"local-test-key"},{"name":"backup","base_url":'
            '"https://backup.example.test/v1","api_key":"backup-test-key"}]'
        )
        state_dir = tmp_path / ".notewise"
        state_dir.mkdir()
        (state_dir / "config.env").write_text(
            "DEFAULT_MODEL=local-endpoint/Local-Model\n"
            f"CUSTOM_LLM_ENDPOINTS={endpoints}\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("NOTEWISE_HOME", str(state_dir))
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("CUSTOM_LLM_ENDPOINTS", raising=False)

        cfg = Config()

        assert cfg.custom_llm_endpoints == endpoints
        assert [
            (profile.name, profile.base_url, profile.api_key)
            for profile in cfg.get_custom_endpoint_profiles()
        ] == [
            ("local-endpoint", "https://llm.example.test/v1", "local-test-key"),
            ("backup", "https://backup.example.test/v1", "backup-test-key"),
        ]
        assert cfg.get_custom_endpoint_for_model("backup/any-model") == (
            "https://backup.example.test/v1",
            "backup-test-key",
        )
        assert "CUSTOM_LLM_ENDPOINTS" not in os.environ
        assert not (state_dir / "config.env").exists()
        assert "OPENAI_API_KEY" not in os.environ

    def test_output_dir_from_user_config_overrides_ambient_env(
        self, tmp_path, monkeypatch
    ):
        """Global OUTPUT_DIR should win unless the CLI passes --output."""
        state_dir = tmp_path / ".notewise"
        configured_output = tmp_path / "configured-output"
        ambient_output = tmp_path / "ambient-output"
        state_dir.mkdir()
        (state_dir / "config.env").write_text(
            f"OUTPUT_DIR={configured_output}\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("NOTEWISE_HOME", str(state_dir))
        monkeypatch.setenv("OUTPUT_DIR", str(ambient_output))

        cfg = Config()

        assert cfg.default_output_dir == configured_output

    def test_get_api_key_for_model(self, monkeypatch):
        """get_api_key_for_model reads from os.environ."""
        monkeypatch.setenv("GEMINI_API_KEY", "gem_key")
        monkeypatch.setenv("OPENAI_API_KEY", "oa_key")
        cfg = Config()
        assert cfg.get_api_key_for_model("gemini/pro") == "gem_key"
        assert cfg.get_api_key_for_model("gpt-4") == "oa_key"
        assert cfg.get_api_key_for_model("unknown") is None

    def test_cohere_deepseek_keys_load_from_env(self, monkeypatch):
        """Cohere and DeepSeek API keys are loaded from environment variables."""
        monkeypatch.setenv("COHERE_API_KEY", "co_key")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "ds_key")
        cfg = Config()
        assert cfg.cohere_api_key == "co_key"
        assert cfg.deepseek_api_key == "ds_key"

    def test_temperature_out_of_range(self, monkeypatch):
        """Temperature > 1.0 raises ValidationError."""
        monkeypatch.setenv("TEMPERATURE", "1.5")
        with pytest.raises(ValidationError):
            Config()

    def test_temperature_negative(self, monkeypatch):
        """Negative temperature raises ValidationError."""
        monkeypatch.setenv("TEMPERATURE", "-0.1")
        with pytest.raises(ValidationError):
            Config()

    def test_temperature_invalid_string(self, monkeypatch):
        """Non-numeric temperature raises ValidationError."""
        monkeypatch.setenv("TEMPERATURE", "hot")
        with pytest.raises(ValidationError):
            Config()

    def test_invalid_user_config_value_does_not_leak_to_environment(
        self,
        tmp_path,
        monkeypatch,
    ):
        """Rejected config.env values should not pollute later settings loads."""
        monkeypatch.delenv("TEMPERATURE", raising=False)
        monkeypatch.setenv("NOTEWISE_HOME", str(tmp_path / ".notewise"))
        config_dir = tmp_path / ".notewise"
        config_dir.mkdir()
        (config_dir / "config.env").write_text("TEMPERATURE=hot\n", encoding="utf-8")

        with pytest.raises(ValidationError):
            Config()

        assert "TEMPERATURE" not in os.environ

    def test_max_tokens_negative(self, monkeypatch):
        """Negative max_tokens raises ValidationError."""
        monkeypatch.setenv("MAX_TOKENS", "-1")
        with pytest.raises(ValidationError):
            Config()

    def test_max_tokens_invalid_string(self, monkeypatch):
        """Non-numeric max_tokens raises ValidationError."""
        monkeypatch.setenv("MAX_TOKENS", "lots")
        with pytest.raises(ValidationError):
            Config()

    def test_youtube_requests_per_minute_valid(self, monkeypatch):
        """Valid YOUTUBE_REQUESTS_PER_MINUTE is accepted."""
        monkeypatch.setenv("YOUTUBE_REQUESTS_PER_MINUTE", "20")
        cfg = Config()
        assert cfg.youtube_requests_per_minute == 20

    def test_youtube_requests_per_minute_invalid_string(self, monkeypatch):
        """Non-numeric rate raises ValidationError."""
        monkeypatch.setenv("YOUTUBE_REQUESTS_PER_MINUTE", "fast")
        with pytest.raises(ValidationError):
            Config()

    def test_youtube_requests_per_minute_lt_one(self, monkeypatch):
        """Rate < 1 raises ValidationError."""
        monkeypatch.setenv("YOUTUBE_REQUESTS_PER_MINUTE", "0")
        with pytest.raises(ValidationError):
            Config()

    def test_load_from_user_config_strips_quotes_and_warns_for_unknown_keys(
        self, tmp_path, monkeypatch
    ):
        """Config file strips quotes; unknown keys are silently ignored."""
        monkeypatch.setenv("NOTEWISE_HOME", str(tmp_path / ".notewise"))
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        config_dir = tmp_path / ".notewise"
        config_dir.mkdir()
        (config_dir / "config.env").write_text(
            'GEMINI_API_KEY="quoted_key"\nUNKNOWN_KEY=ignored\n'
        )
        cfg = Config()
        assert cfg.gemini_api_key == "quoted_key"
        # Unknown keys are silently dropped (no crash)

    def test_load_from_user_config_handles_file_read_failures(
        self, tmp_path, monkeypatch
    ):
        """Unreadable config file doesn't crash; defaults are used."""
        monkeypatch.setenv("NOTEWISE_HOME", str(tmp_path / ".notewise"))
        monkeypatch.delenv("DEFAULT_MODEL", raising=False)
        # No config.env file → no crash, just defaults
        cfg = Config()
        assert cfg.default_model == "gemini/gemini-2.5-flash"

    def test_sync_env_vars_copies_supported_api_keys(self, monkeypatch):
        """API keys are synced back to os.environ after init."""
        monkeypatch.setenv("GEMINI_API_KEY", "sync_test_key")
        Config()
        assert os.environ.get("GEMINI_API_KEY") == "sync_test_key"

    def test_oauth_token_dirs_default_to_notewise_state_dir(
        self, tmp_path, monkeypatch
    ):
        """OAuth provider tokens should be scoped under the notewise state dir."""
        state_dir = tmp_path / ".notewise"
        monkeypatch.setenv("NOTEWISE_HOME", str(state_dir))
        monkeypatch.delenv("CHATGPT_TOKEN_DIR", raising=False)
        monkeypatch.delenv("GITHUB_COPILOT_TOKEN_DIR", raising=False)

        cfg = Config()

        assert cfg.chatgpt_token_dir == state_dir / "oauth" / "chatgpt"
        assert cfg.github_copilot_token_dir == state_dir / "oauth" / "github_copilot"
        assert os.environ["CHATGPT_TOKEN_DIR"] == str(state_dir / "oauth" / "chatgpt")
        assert os.environ["GITHUB_COPILOT_TOKEN_DIR"] == str(
            state_dir / "oauth" / "github_copilot"
        )

    def test_existing_oauth_token_dirs_are_preserved(self, tmp_path, monkeypatch):
        """Explicit token dir env vars should override notewise defaults."""
        monkeypatch.setenv("NOTEWISE_HOME", str(tmp_path / ".notewise"))
        monkeypatch.setenv("CHATGPT_TOKEN_DIR", str(tmp_path / "chatgpt-custom"))
        monkeypatch.setenv("GITHUB_COPILOT_TOKEN_DIR", str(tmp_path / "copilot-custom"))

        cfg = Config()

        assert os.environ["CHATGPT_TOKEN_DIR"] == str(tmp_path / "chatgpt-custom")
        assert os.environ["GITHUB_COPILOT_TOKEN_DIR"] == str(
            tmp_path / "copilot-custom"
        )
        assert cfg.chatgpt_token_dir == tmp_path / "chatgpt-custom"
        assert cfg.github_copilot_token_dir == tmp_path / "copilot-custom"

    def test_oauth_token_dirs_can_load_from_user_config(self, tmp_path, monkeypatch):
        """OAuth token dir overrides in config.env should be accepted."""
        state_dir = tmp_path / ".notewise"
        config_dir = state_dir
        config_dir.mkdir()
        chatgpt_dir = tmp_path / "chatgpt-config"
        copilot_dir = tmp_path / "copilot-config"
        (config_dir / "config.env").write_text(
            f"CHATGPT_TOKEN_DIR={chatgpt_dir}\n"
            f"GITHUB_COPILOT_TOKEN_DIR={copilot_dir}\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("NOTEWISE_HOME", str(state_dir))
        monkeypatch.delenv("CHATGPT_TOKEN_DIR", raising=False)
        monkeypatch.delenv("GITHUB_COPILOT_TOKEN_DIR", raising=False)

        cfg = Config()

        assert os.environ["CHATGPT_TOKEN_DIR"] == str(chatgpt_dir)
        assert os.environ["GITHUB_COPILOT_TOKEN_DIR"] == str(copilot_dir)
        assert cfg.chatgpt_token_dir == chatgpt_dir
        assert cfg.github_copilot_token_dir == copilot_dir

    def test_managed_oauth_token_dirs_refresh_when_state_dir_changes(
        self, tmp_path, monkeypatch
    ):
        """Derived token dir env vars should not pin future state dirs."""
        first_state_dir = tmp_path / "first"
        second_state_dir = tmp_path / "second"
        monkeypatch.setenv("NOTEWISE_HOME", str(first_state_dir))
        monkeypatch.delenv("CHATGPT_TOKEN_DIR", raising=False)
        monkeypatch.delenv("GITHUB_COPILOT_TOKEN_DIR", raising=False)

        Config()

        monkeypatch.setenv("NOTEWISE_HOME", str(second_state_dir))
        cfg = Config()

        assert cfg.chatgpt_token_dir == second_state_dir / "oauth" / "chatgpt"
        assert cfg.github_copilot_token_dir == (
            second_state_dir / "oauth" / "github_copilot"
        )
        assert os.environ["CHATGPT_TOKEN_DIR"] == str(
            second_state_dir / "oauth" / "chatgpt"
        )
        assert os.environ["GITHUB_COPILOT_TOKEN_DIR"] == str(
            second_state_dir / "oauth" / "github_copilot"
        )

    def test_oauth_token_dirs_precreated_under_state_dir(self, tmp_path, monkeypatch):
        """Token directories should be created before env vars are assigned."""
        state_dir = tmp_path / ".notewise"
        monkeypatch.setenv("NOTEWISE_HOME", str(state_dir))
        monkeypatch.delenv("CHATGPT_TOKEN_DIR", raising=False)
        monkeypatch.delenv("GITHUB_COPILOT_TOKEN_DIR", raising=False)

        Config()

        assert (state_dir / "oauth" / "chatgpt").is_dir()
        assert (state_dir / "oauth" / "github_copilot").is_dir()

    @pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits only")
    def test_oauth_token_dirs_created_owner_only(self, tmp_path, monkeypatch):
        """Token directories should be private to the owner on POSIX systems."""
        import stat

        state_dir = tmp_path / ".notewise"
        monkeypatch.setenv("NOTEWISE_HOME", str(state_dir))
        monkeypatch.delenv("CHATGPT_TOKEN_DIR", raising=False)
        monkeypatch.delenv("GITHUB_COPILOT_TOKEN_DIR", raising=False)

        Config()

        for provider_dir in ("chatgpt", "github_copilot"):
            mode = stat.S_IMODE((state_dir / "oauth" / provider_dir).stat().st_mode)
            assert mode == 0o700

    def test_load_positive_int_env_uses_default_when_env_is_missing(self, monkeypatch):
        """Missing optional int env uses field default."""
        monkeypatch.delenv("MAX_CONCURRENT_VIDEOS", raising=False)
        cfg = Config()
        assert cfg.max_concurrent_videos == 5

    def test_user_config_source_caches_file_parse_per_instance(
        self,
        tmp_path,
        monkeypatch,
    ):
        """A single settings-source instance should only parse config.env once."""
        monkeypatch.setenv("NOTEWISE_HOME", str(tmp_path / ".notewise"))
        config_dir = tmp_path / ".notewise"
        config_dir.mkdir()
        config_path = config_dir / "config.env"
        config_path.write_text(
            "DEFAULT_MODEL=gemini/gemini-2.5-flash",
            encoding="utf-8",
        )

        read_calls = 0
        original_open = os.open

        def _counting_open(path, *args, **kwargs):
            nonlocal read_calls
            if os.fspath(path) == os.fspath(config_path):
                read_calls += 1
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr(config_module.os, "open", _counting_open)

        source = UserConfigSource(Config)
        source.get_field_value(None, "default_model")
        source.get_field_value(None, "default_model")
        source()

        assert read_calls == 1

    def test_user_config_source_ignores_expected_read_failures(
        self, tmp_path, monkeypatch, mocker
    ):
        """Expected config read failures should warn and fall back to empty config."""
        monkeypatch.setenv("NOTEWISE_HOME", str(tmp_path / ".notewise"))
        config_dir = tmp_path / ".notewise"
        config_dir.mkdir()
        (config_dir / "config.env").write_text("DEFAULT_MODEL=unused", encoding="utf-8")
        warning = mocker.patch.object(config_module.logger, "warning")

        def _raise_os_error(*_args, **_kwargs):
            raise OSError("cannot read")

        mocker.patch.object(config_module.os, "open", _raise_os_error)

        assert UserConfigSource(Config)() == {}
        warning.assert_called_once_with(
            "UserConfigSource failed to import legacy config.env",
            config_path=str(config_dir / "config.env"),
            exc_info=True,
        )

    def test_user_config_source_does_not_hide_unexpected_parse_errors(
        self, tmp_path, monkeypatch, mocker
    ):
        """Unexpected parser/runtime errors should remain visible."""
        monkeypatch.setenv("NOTEWISE_HOME", str(tmp_path / ".notewise"))
        config_dir = tmp_path / ".notewise"
        config_dir.mkdir()
        (config_dir / "config.env").write_text("DEFAULT_MODEL=unused", encoding="utf-8")

        def _raise_runtime_error(*_args, **_kwargs):
            raise RuntimeError("bug")

        mocker.patch.object(config_module.os, "open", _raise_runtime_error)

        with pytest.raises(RuntimeError, match="bug"):
            UserConfigSource(Config)()

    @pytest.mark.skipif(os.name == "nt", reason="symlink creation is not available")
    def test_user_config_source_never_follows_a_symlinked_legacy_config(
        self, tmp_path, monkeypatch
    ):
        """A symlinked config.env must not have its target's content imported."""
        monkeypatch.setenv("NOTEWISE_HOME", str(tmp_path / ".notewise"))
        config_dir = tmp_path / ".notewise"
        config_dir.mkdir()
        victim = tmp_path / "victim.env"
        victim.write_text("DEFAULT_MODEL=stolen-from-victim\n", encoding="utf-8")
        (config_dir / "config.env").symlink_to(victim)

        assert UserConfigSource(Config)() == {}
        assert (
            victim.read_text(encoding="utf-8") == "DEFAULT_MODEL=stolen-from-victim\n"
        )
        assert (config_dir / "config.env").is_symlink()


class TestGetApiKeyNameForModel:
    """Test get_api_key_name_for_model."""

    def setup_method(self):
        self.cfg = Config()

    def test_gemini_model_returns_gemini_key(self):
        assert (
            self.cfg.get_api_key_name_for_model("gemini/gemini-2.5-flash")
            == "GEMINI_API_KEY"
        )

    def test_openai_model_returns_openai_key(self):
        assert self.cfg.get_api_key_name_for_model("gpt-4o") == "OPENAI_API_KEY"

    def test_anthropic_model_returns_anthropic_key(self):
        assert (
            self.cfg.get_api_key_name_for_model("claude-3-opus") == "ANTHROPIC_API_KEY"
        )

    def test_groq_model_returns_groq_key(self):
        assert self.cfg.get_api_key_name_for_model("groq/llama3") == "GROQ_API_KEY"

    def test_xai_model_returns_xai_key(self):
        assert self.cfg.get_api_key_name_for_model("grok-2") == "XAI_API_KEY"

    def test_mistral_model_returns_mistral_key(self):
        assert (
            self.cfg.get_api_key_name_for_model("mistral/mistral-large")
            == "MISTRAL_API_KEY"
        )

    def test_cohere_model_returns_cohere_key(self):
        assert self.cfg.get_api_key_name_for_model("command-r") == "COHERE_API_KEY"

    def test_deepseek_model_returns_deepseek_key(self):
        assert (
            self.cfg.get_api_key_name_for_model("deepseek/deepseek-chat")
            == "DEEPSEEK_API_KEY"
        )

    def test_unknown_model_returns_none(self):
        assert self.cfg.get_api_key_name_for_model("unknown-model") is None

    def test_empty_model_returns_none(self):
        assert self.cfg.get_api_key_name_for_model("") is None

    def test_openrouter_model_returns_openrouter_key(self):
        assert (
            self.cfg.get_api_key_name_for_model("openrouter/some-model")
            == "OPENROUTER_API_KEY"
        )

    def test_major_litellm_provider_api_keys(self):
        """Major LiteLLM providers should map to their documented env vars."""
        expected = {
            "azure/gpt-4o": "AZURE_API_KEY",
            "azure_ai/gpt-4o": "AZURE_API_KEY",
            "vercel_ai_gateway/openai/gpt-4o-mini": "VERCEL_AI_GATEWAY_API_KEY",
            "together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo": "TOGETHERAI_API_KEY",
            (
                "fireworks_ai/accounts/fireworks/models/llama-v3p1-8b-instruct"
            ): "FIREWORKS_AI_API_KEY",
            "perplexity/sonar": "PERPLEXITYAI_API_KEY",
            "huggingface/mistralai/Mistral-7B-Instruct-v0.2": "HUGGINGFACE_API_KEY",
            "replicate/meta/meta-llama-3-8b-instruct": "REPLICATE_API_KEY",
            "cerebras/llama3.1-8b": "CEREBRAS_API_KEY",
            "deepinfra/meta-llama/Meta-Llama-3.1-8B-Instruct": "DEEPINFRA_API_KEY",
            "sambanova/Meta-Llama-3.1-8B-Instruct": "SAMBANOVA_API_KEY",
            "cloudflare/@cf/meta/llama-3.1-8b-instruct": "CLOUDFLARE_API_KEY",
            "ai21/jamba-1.5-mini": "AI21_API_KEY",
            "dashscope/qwen-plus": "DASHSCOPE_API_KEY",
            "databricks/databricks-meta-llama-3-1-70b-instruct": "DATABRICKS_API_KEY",
            "novita/meta-llama/llama-3.1-8b-instruct": "NOVITA_API_KEY",
            "nvidia_nim/meta/llama-3.1-8b-instruct": "NVIDIA_NIM_API_KEY",
            "watsonx/meta-llama/llama-3-3-70b-instruct": "WATSONX_API_KEY",
            "voyage/voyage-3": "VOYAGE_API_KEY",
            "jina_ai/jina-embeddings-v3": "JINA_API_KEY",
        }

        for model, env_var in expected.items():
            assert self.cfg.get_api_key_name_for_model(model) == env_var

    def test_oauth_and_credential_chain_providers_do_not_require_api_key(self):
        """OAuth/device-flow and ambient credential providers skip key preflight."""
        for model in (
            "chatgpt/gpt-5-codex",
            "github_copilot/gpt-5-codex",
            "bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0",
            "bedrock_converse/anthropic.claude-3-5-sonnet-20240620-v1:0",
            "amazon_nova/amazon.nova-pro-v1:0",
        ):
            assert self.cfg.get_api_key_name_for_model(model) is None

    def test_new_provider_keys_load_from_user_config(self, tmp_path, monkeypatch):
        """New provider keys should load from config.env and sync to os.environ."""
        monkeypatch.setenv("NOTEWISE_HOME", str(tmp_path / ".notewise"))
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        config_dir = tmp_path / ".notewise"
        config_dir.mkdir(exist_ok=True)
        (config_dir / "config.env").write_text(
            "OPENROUTER_API_KEY=or-key\n",
            encoding="utf-8",
        )

        cfg = Config()

        assert cfg.get_api_key_for_model("openrouter/openai/gpt-4o-mini") == "or-key"
        assert os.environ["OPENROUTER_API_KEY"] == "or-key"

    def test_custom_endpoint_resolution_matches_every_saved_profile(self):
        """Each normalized profile prefix resolves independent of DEFAULT_MODEL."""
        cfg = Config(
            default_model="local-endpoint/Local-Model",
            custom_llm_endpoints=(
                '[{"name":"Local-Endpoint","base_url":"https://llm.example.test",'
                '"api_key":"local-test-key"},{"name":"backup","base_url":'
                '"https://backup.example.test/v1","api_key":"backup-test-key"}]'
            ),
        )

        assert cfg.get_custom_endpoint_for_model(" LOCAL-ENDPOINT/local-model ") == (
            "https://llm.example.test/v1",
            "local-test-key",
        )
        assert cfg.get_custom_endpoint_for_model("backup/other-model") == (
            "https://backup.example.test/v1",
            "backup-test-key",
        )
        assert cfg.get_custom_endpoint_for_model("unconfigured/model") is None

    def test_custom_endpoint_registry_preflight_is_model_scoped(self, monkeypatch):
        """Only unconfigured custom prefixes report the endpoint registry."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        configured = Config(
            custom_llm_endpoints=(
                '[{"name":"local-endpoint","base_url":"https://llm.example.test/v1",'
                '"api_key":"custom-test-key"}]'
            )
        )
        missing_profile = Config(default_model="unconfigured-endpoint/local-model")

        assert (
            configured.get_missing_config_names_for_model("local-endpoint/local-model")
            == ()
        )
        assert missing_profile.get_missing_config_names_for_model(
            "unconfigured-endpoint/local-model"
        ) == ("CUSTOM_LLM_ENDPOINTS",)
        assert missing_profile.get_missing_config_names_for_model(
            "openai/other-model"
        ) == ("OPENAI_API_KEY",)
        assert missing_profile.get_missing_config_names_for_model("ollama/llama3") == ()

    def test_custom_endpoint_registry_is_validated_at_construction(self):
        """Invalid persisted endpoint registries fail settings construction."""
        with pytest.raises(ValidationError, match="valid JSON array"):
            Config(custom_llm_endpoints="not-json")

    def test_alternate_api_key_names_are_accepted(self, monkeypatch):
        """Providers with alternate env var names should accept either key."""
        monkeypatch.delenv("AZURE_API_KEY", raising=False)
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-openai-key")

        assert self.cfg.get_api_key_for_model("azure/gpt-4o") == "azure-openai-key"
        assert self.cfg.get_missing_config_names_for_model("azure/gpt-4o") == ()

    def test_required_companion_env_vars_are_reported(self, monkeypatch):
        """Providers with required companion env vars should report missing values."""
        monkeypatch.setenv("CLOUDFLARE_API_KEY", "cf-key")
        monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)

        assert self.cfg.get_missing_config_names_for_model(
            "cloudflare/@cf/meta/llama-3.1-8b-instruct"
        ) == ("CLOUDFLARE_ACCOUNT_ID",)

    def test_unsupported_model_message_applies_to_any_snapshot_provider(self):
        """Model support preflight should not be limited to OAuth providers."""
        message = self.cfg.get_unsupported_model_message("openrouter/unknown-model")

        assert message is not None
        assert "openrouter/unknown-model" in message
        assert "not currently supported" in message
        assert "notewise setup --force" in message

    def test_unsupported_model_message_uses_provider_display_name(self, mocker):
        """Non-OAuth providers should use the shared friendly provider label."""
        mocker.patch.object(
            config_module,
            "_load_bundled_model_snapshot",
            return_value={"gemini": ("gemini/gemini-2.5-flash",)},
        )

        message = self.cfg.get_unsupported_model_message("gemini/unknown-model")

        assert message is not None
        assert "for Google Gemini" in message
        assert "for gemini" not in message

    def test_unsupported_model_message_preserves_oauth_provider_label(self, mocker):
        """OAuth providers should keep their subscription-oriented labels."""
        mocker.patch.object(
            config_module,
            "_load_bundled_model_snapshot",
            return_value={"chatgpt": ("chatgpt/gpt-5.2",)},
        )

        message = self.cfg.get_unsupported_model_message("chatgpt/unknown-model")

        assert message is not None
        assert "for ChatGPT Subscription" in message

    def test_supported_snapshot_model_has_no_unsupported_message(self):
        snapshot = config_module._load_bundled_model_snapshot()
        selected_model = next(
            model for models in snapshot.values() for model in models if model
        )

        assert self.cfg.get_unsupported_model_message(selected_model) is None

    def test_reasoning_models(self):
        assert self.cfg.get_api_key_name_for_model("o1") == "OPENAI_API_KEY"
        assert self.cfg.get_api_key_name_for_model("o3-mini") == "OPENAI_API_KEY"
        assert self.cfg.get_api_key_name_for_model("o4-preview") == "OPENAI_API_KEY"

    def test_allow_unlisted_models_defaults_to_false(self, monkeypatch):
        """The unlisted-model opt-in must stay off unless explicitly enabled."""
        monkeypatch.delenv("ALLOW_UNLISTED_MODELS", raising=False)

        assert Config().allow_unlisted_models is False

    def test_allow_unlisted_models_loads_from_env(self, monkeypatch):
        """ALLOW_UNLISTED_MODELS parses boolean env values."""
        monkeypatch.setenv("ALLOW_UNLISTED_MODELS", "true")
        assert Config().allow_unlisted_models is True

        monkeypatch.setenv("ALLOW_UNLISTED_MODELS", "false")
        assert Config().allow_unlisted_models is False

    def test_allow_unlisted_models_loads_from_user_config(self, tmp_path, monkeypatch):
        """config.env is an accepted source for the unlisted-model opt-in."""
        monkeypatch.delenv("ALLOW_UNLISTED_MODELS", raising=False)
        monkeypatch.setenv("NOTEWISE_HOME", str(tmp_path / ".notewise"))
        config_dir = tmp_path / ".notewise"
        config_dir.mkdir(exist_ok=True)
        (config_dir / "config.env").write_text(
            "ALLOW_UNLISTED_MODELS=true\n",
            encoding="utf-8",
        )

        assert Config().allow_unlisted_models is True
