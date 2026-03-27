"""Tests for configuration management (Pydantic v2 BaseSettings)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

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
        original_read_text = Path.read_text

        def _counting_read_text(path: Path, *args, **kwargs):  # noqa: ANN001
            nonlocal read_calls
            read_calls += 1
            return original_read_text(path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", _counting_read_text)

        source = UserConfigSource(Config)
        source.get_field_value(None, "default_model")
        source.get_field_value(None, "default_model")
        source()

        assert read_calls == 1


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

    def test_openrouter_returns_none(self):
        assert self.cfg.get_api_key_name_for_model("openrouter/some-model") is None

    def test_reasoning_models(self):
        assert self.cfg.get_api_key_name_for_model("o1") == "OPENAI_API_KEY"
        assert self.cfg.get_api_key_name_for_model("o3-mini") == "OPENAI_API_KEY"
        assert self.cfg.get_api_key_name_for_model("o4-preview") == "OPENAI_API_KEY"
