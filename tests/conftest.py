"""Test configuration and fixtures."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from yt_study.db import DatabaseManager


@pytest.fixture
def sample_video_id():
    """Sample YouTube video ID for testing."""
    return "dQw4w9WgXcQ"


@pytest.fixture
def sample_playlist_id():
    """Sample YouTube playlist ID for testing."""
    return "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"


@pytest.fixture(autouse=True)
def isolate_state_dir(tmp_path, monkeypatch):
    """Isolate yt-study state files (including SQLite cache) per test."""
    monkeypatch.setenv("YT_STUDY_HOME", str(tmp_path / ".yt-study"))
    yield
    DatabaseManager.close_all_instances()


@pytest.fixture
def temp_output_dir(tmp_path):
    """Create a temporary output directory."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return output_dir


@pytest.fixture
def mock_config(monkeypatch):
    """Mock configuration with dummy API keys."""
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_gemini_key")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy_openai_key")

    # Reload config to pick up env vars if necessary,
    # or just rely on Config loading from env.
    from yt_study.core.config import config

    config.gemini_api_key = "dummy_gemini_key"
    config.openai_api_key = "dummy_openai_key"
    return config


@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider."""
    provider = MagicMock()
    provider.generate = AsyncMock(return_value="# Generated Notes\n\nTest content.")
    provider.model = "mock-model"
    return provider


@pytest.fixture
def mock_extractor_client(mocker):
    """Mock native ExtractorClient in all wrapper modules."""
    meta_client = mocker.patch("yt_study.core.youtube.metadata.ExtractorClient")
    transcript_client = mocker.patch("yt_study.core.youtube.transcript.ExtractorClient")
    playlist_client = mocker.patch("yt_study.core.youtube.playlist.ExtractorClient")
    return {
        "metadata": meta_client,
        "transcript": transcript_client,
        "playlist": playlist_client,
    }
