"""Tests for configuration management."""

import os
from unittest.mock import patch

from yt_study.core.config import Config


class TestConfig:
    """Test Config class."""

    def test_defaults(self, monkeypatch):
        """Test default values."""
        # Ensure env doesn't interfere
        monkeypatch.delenv("DEFAULT_MODEL", raising=False)
        monkeypatch.delenv("OUTPUT_DIR", raising=False)
        monkeypatch.delenv("MAX_CONCURRENT_VIDEOS", raising=False)

        # Prevent loading from real user config file
        with patch.object(Config, "_load_from_user_config"):
            cfg = Config()
            assert cfg.default_model == "gemini/gemini-2.5-flash"
            assert cfg.max_concurrent_videos == 5
            assert cfg.youtube_requests_per_minute == 10

    def test_load_from_env(self, monkeypatch):
        """Test loading from environment variables."""
        monkeypatch.setenv("GEMINI_API_KEY", "env_key")
        monkeypatch.setenv("DEFAULT_MODEL", "gpt-4o")

        # Prevent loading from real user config file to ensure env isolation
        with patch.object(Config, "_load_from_user_config"):
            cfg = Config()
            assert cfg.gemini_api_key == "env_key"
            assert cfg.default_model == "gpt-4o"

    def test_load_from_file(self, tmp_path, monkeypatch):
        """Test loading from config file."""
        # Clear env vars that might interfere
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("MAX_CONCURRENT_VIDEOS", raising=False)

        # We want to test _load_from_user_config logic here, so we DON'T mock it.
        # Instead we mock Path.home to point to a temp dir.

        with patch("pathlib.Path.home", return_value=tmp_path):
            config_dir = tmp_path / ".yt-study"
            config_dir.mkdir()
            config_file = config_dir / "config.env"
            config_file.write_text("OPENAI_API_KEY=file_key\nMAX_CONCURRENT_VIDEOS=10")

            cfg = Config()
            assert cfg.openai_api_key == "file_key"
            # Config sets os.environ, so we check that too or the attribute
            assert int(os.environ.get("MAX_CONCURRENT_VIDEOS", 5)) == 10

    def test_get_api_key_for_model(self):
        """Test api key retrieval helper."""
        cfg = Config()
        cfg.gemini_api_key = "gem_key"
        cfg.openai_api_key = "oa_key"

        # We need to sync these to os.environ because
        # get_api_key_for_model reads from os.environ
        with patch.dict(
            os.environ, {"GEMINI_API_KEY": "gem_key", "OPENAI_API_KEY": "oa_key"}
        ):
            assert cfg.get_api_key_for_model("gemini/pro") == "gem_key"
            assert cfg.get_api_key_for_model("gpt-4") == "oa_key"
            assert cfg.get_api_key_for_model("unknown") is None

    def test_cohere_deepseek_keys_load_from_env(self, monkeypatch):
        """Cohere and DeepSeek API keys are loaded from environment variables."""
        monkeypatch.setenv("COHERE_API_KEY", "co_key")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "ds_key")

        with patch.object(Config, "_load_from_user_config"):
            cfg = Config()
            assert cfg.cohere_api_key == "co_key"
            assert cfg.deepseek_api_key == "ds_key"

    def test_cohere_deepseek_model_key_mapping(self):
        """Cohere and DeepSeek model prefixes map to the right env var names."""
        cfg = Config()
        assert cfg.get_api_key_name_for_model("cohere/command-r") == "COHERE_API_KEY"
        assert cfg.get_api_key_name_for_model("command-r-plus") == "COHERE_API_KEY"
        assert (
            cfg.get_api_key_name_for_model("deepseek/deepseek-chat")
            == "DEEPSEEK_API_KEY"
        )

    def test_openai_reasoning_model_key_mapping(self):
        """OpenAI reasoning-model families must resolve to OPENAI_API_KEY."""
        cfg = Config()

        assert cfg.get_api_key_name_for_model("o1") == "OPENAI_API_KEY"
        assert cfg.get_api_key_name_for_model("o1-mini") == "OPENAI_API_KEY"
        assert cfg.get_api_key_name_for_model("o3-mini") == "OPENAI_API_KEY"
        assert cfg.get_api_key_name_for_model("o4-mini") == "OPENAI_API_KEY"

    def test_gateway_models_do_not_map_to_first_party_api_keys(self):
        """Unsupported gateway prefixes should not demand the wrong first-party key."""
        cfg = Config()

        assert (
            cfg.get_api_key_name_for_model("openrouter/google/gemini-2.5-flash") is None
        )
        assert cfg.get_api_key_name_for_model("google/gemini-2.5-flash") is None
        assert cfg.get_api_key_name_for_model("azure/gpt-4o") is None
        assert cfg.get_api_key_name_for_model("vercel_ai_gateway/gpt-4o") is None

    def test_temperature_out_of_range(self, monkeypatch):
        """TEMPERATURE > 1 falls back to 0.7."""
        monkeypatch.delenv("TEMPERATURE", raising=False)
        monkeypatch.setenv("TEMPERATURE", "1.5")

        with patch.object(Config, "_load_from_user_config"):
            cfg = Config()
            assert cfg.temperature == 0.7

    def test_temperature_negative(self, monkeypatch):
        """TEMPERATURE < 0 falls back to 0.7."""
        monkeypatch.delenv("TEMPERATURE", raising=False)
        monkeypatch.setenv("TEMPERATURE", "-0.5")

        with patch.object(Config, "_load_from_user_config"):
            cfg = Config()
            assert cfg.temperature == 0.7

    def test_temperature_invalid_string(self, monkeypatch):
        """TEMPERATURE='abc' falls back to 0.7."""
        monkeypatch.delenv("TEMPERATURE", raising=False)
        monkeypatch.setenv("TEMPERATURE", "abc")

        with patch.object(Config, "_load_from_user_config"):
            cfg = Config()
            assert cfg.temperature == 0.7

    def test_max_tokens_negative(self, monkeypatch):
        """MAX_TOKENS < 1 falls back to None."""
        monkeypatch.delenv("MAX_TOKENS", raising=False)
        monkeypatch.setenv("MAX_TOKENS", "-100")

        with patch.object(Config, "_load_from_user_config"):
            cfg = Config()
            assert cfg.max_tokens is None

    def test_max_tokens_invalid_string(self, monkeypatch):
        """MAX_TOKENS='xyz' falls back to None."""
        monkeypatch.delenv("MAX_TOKENS", raising=False)
        monkeypatch.setenv("MAX_TOKENS", "xyz")

        with patch.object(Config, "_load_from_user_config"):
            cfg = Config()
            assert cfg.max_tokens is None

    def test_youtube_requests_per_minute_valid(self, monkeypatch):
        """YOUTUBE_REQUESTS_PER_MINUTE is loaded when valid and >= 1."""
        monkeypatch.delenv("YOUTUBE_REQUESTS_PER_MINUTE", raising=False)
        monkeypatch.setenv("YOUTUBE_REQUESTS_PER_MINUTE", "25")

        with patch.object(Config, "_load_from_user_config"):
            cfg = Config()
            assert cfg.youtube_requests_per_minute == 25

    def test_youtube_requests_per_minute_invalid_string(self, monkeypatch):
        """Invalid YOUTUBE_REQUESTS_PER_MINUTE falls back to default."""
        monkeypatch.delenv("YOUTUBE_REQUESTS_PER_MINUTE", raising=False)
        monkeypatch.setenv("YOUTUBE_REQUESTS_PER_MINUTE", "abc")

        with patch.object(Config, "_load_from_user_config"):
            cfg = Config()
            assert cfg.youtube_requests_per_minute == 10

    def test_youtube_requests_per_minute_lt_one(self, monkeypatch):
        """YOUTUBE_REQUESTS_PER_MINUTE < 1 falls back to default."""
        monkeypatch.delenv("YOUTUBE_REQUESTS_PER_MINUTE", raising=False)
        monkeypatch.setenv("YOUTUBE_REQUESTS_PER_MINUTE", "0")

        with patch.object(Config, "_load_from_user_config"):
            cfg = Config()
            assert cfg.youtube_requests_per_minute == 10

    def test_legacy_youtube_auth_keys_are_ignored(self, tmp_path, monkeypatch):
        """Removed YouTube auth keys should not be loaded from config.env."""
        for key in (
            "YOUTUBE_USE_OAUTH",
            "YOUTUBE_SAVE_OAUTH_TOKEN",
            "YOUTUBE_OAUTH_TOKEN_FILE",
            "YOUTUBE_AUTO_REFRESH_OAUTH_TOKEN",
        ):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv("MAX_CONCURRENT_VIDEOS", raising=False)

        with patch("pathlib.Path.home", return_value=tmp_path):
            config_dir = tmp_path / ".yt-study"
            config_dir.mkdir()
            config_file = config_dir / "config.env"
            config_file.write_text(
                "\n".join(
                    [
                        "YOUTUBE_USE_OAUTH=true",
                        "YOUTUBE_SAVE_OAUTH_TOKEN=true",
                        "YOUTUBE_OAUTH_TOKEN_FILE=~/tokens/yt-token.json",
                        "YOUTUBE_AUTO_REFRESH_OAUTH_TOKEN=false",
                        "MAX_CONCURRENT_VIDEOS=8",
                    ]
                ),
                encoding="utf-8",
            )

            cfg = Config()

        assert cfg.max_concurrent_videos == 8
        assert "YOUTUBE_USE_OAUTH" not in os.environ
        assert "YOUTUBE_SAVE_OAUTH_TOKEN" not in os.environ
        assert "YOUTUBE_OAUTH_TOKEN_FILE" not in os.environ
        assert "YOUTUBE_AUTO_REFRESH_OAUTH_TOKEN" not in os.environ

    def test_load_from_user_config_strips_quotes_and_warns_for_unknown_keys(
        self, tmp_path, monkeypatch, caplog
    ):
        """Quoted values should load, and unknown keys should warn and be ignored."""
        monkeypatch.delenv("DEFAULT_MODEL", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with patch("pathlib.Path.home", return_value=tmp_path):
            config_dir = tmp_path / ".yt-study"
            config_dir.mkdir()
            (config_dir / "config.env").write_text(
                "\n".join(
                    [
                        'DEFAULT_MODEL="gpt-4o-mini"',
                        "OPENAI_API_KEY='quoted-key'",
                        "UNKNOWN_KEY=value",
                    ]
                ),
                encoding="utf-8",
            )

            with caplog.at_level("WARNING"):
                cfg = Config()

        assert cfg.default_model == "gpt-4o-mini"
        assert cfg.openai_api_key == "quoted-key"
        assert "Ignoring unauthorized config key: UNKNOWN_KEY" in caplog.text

    def test_load_from_user_config_handles_file_read_failures(
        self, tmp_path, monkeypatch, caplog
    ):
        """Config loading should warn and continue when the file cannot be read."""
        monkeypatch.delenv("DEFAULT_MODEL", raising=False)

        with patch("pathlib.Path.home", return_value=tmp_path):
            config_dir = tmp_path / ".yt-study"
            config_dir.mkdir()
            (config_dir / "config.env").write_text(
                "DEFAULT_MODEL=gpt-4o",
                encoding="utf-8",
            )

            with (
                patch("pathlib.Path.open", side_effect=OSError("boom")),
                caplog.at_level("WARNING"),
            ):
                cfg = Config()

        assert cfg.default_model == "gemini/gemini-2.5-flash"
        assert "Failed to load config file" in caplog.text

    def test_sync_env_vars_copies_supported_api_keys(self, monkeypatch):
        """_sync_env_vars should mirror populated provider keys back into os.environ."""
        for key in (
            "GEMINI_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "GROQ_API_KEY",
            "XAI_API_KEY",
            "MISTRAL_API_KEY",
            "COHERE_API_KEY",
            "DEEPSEEK_API_KEY",
        ):
            monkeypatch.delenv(key, raising=False)

        with patch.object(Config, "_load_from_user_config"):
            cfg = Config()

        cfg.gemini_api_key = "gem"
        cfg.openai_api_key = "oa"
        cfg.anthropic_api_key = "anth"
        cfg.groq_api_key = "groq"
        cfg.xai_api_key = "xai"
        cfg.mistral_api_key = "mistral"
        cfg.cohere_api_key = "cohere"
        cfg.deepseek_api_key = "deepseek"
        cfg._sync_env_vars()

        assert os.environ["GEMINI_API_KEY"] == "gem"
        assert os.environ["OPENAI_API_KEY"] == "oa"
        assert os.environ["ANTHROPIC_API_KEY"] == "anth"
        assert os.environ["GROQ_API_KEY"] == "groq"
        assert os.environ["XAI_API_KEY"] == "xai"
        assert os.environ["MISTRAL_API_KEY"] == "mistral"
        assert os.environ["COHERE_API_KEY"] == "cohere"
        assert os.environ["DEEPSEEK_API_KEY"] == "deepseek"

    def test_get_api_key_name_for_model_handles_blank_and_native_prefixes(self):
        """Blank models and native provider prefixes should resolve predictably."""
        cfg = Config()

        assert cfg.get_api_key_name_for_model("   ") is None
        assert cfg.get_api_key_name_for_model("anthropic/claude-sonnet-4") == (
            "ANTHROPIC_API_KEY"
        )
        assert cfg.get_api_key_name_for_model("groq/llama-3.1-8b") == "GROQ_API_KEY"
        assert cfg.get_api_key_name_for_model("xai/grok-3-beta") == "XAI_API_KEY"
        assert cfg.get_api_key_name_for_model("mistral/mistral-large") == (
            "MISTRAL_API_KEY"
        )

    def test_load_positive_int_env_uses_default_when_env_is_missing(self, monkeypatch):
        """Missing positive-int settings should keep the current default."""
        monkeypatch.delenv("MAX_CONCURRENT_VIDEOS", raising=False)

        with patch.object(Config, "_load_from_user_config"):
            cfg = Config()

        assert cfg._load_positive_int_env("MAX_CONCURRENT_VIDEOS", 7) == 7
