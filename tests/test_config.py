"""Tests for configuration management."""

import os
from unittest.mock import patch

from yt_study.config import Config


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
            assert cfg.default_model == "gemini/gemini-2.0-flash"
            assert cfg.max_concurrent_videos == 5

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
