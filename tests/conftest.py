"""Test configuration and fixtures."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def sample_video_id():
    """Sample YouTube video ID for testing."""
    return "dQw4w9WgXcQ"


@pytest.fixture
def sample_playlist_id():
    """Sample YouTube playlist ID for testing."""
    return "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"


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
    from yt_study.config import config

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
def mock_transcript_api(mocker):
    """Mock YouTubeTranscriptApi class."""
    return mocker.patch("yt_study.youtube.transcript.YouTubeTranscriptApi")


@pytest.fixture
def mock_pytube(mocker):
    """Mock pytubefix YouTube and Playlist classes."""
    # We patch the classes where they are imported in metadata.py
    mock_yt = mocker.patch("yt_study.youtube.metadata.YouTube")
    mock_pl = mocker.patch("yt_study.youtube.metadata.Playlist")

    # Also patch in playlist.py if used there
    mocker.patch("yt_study.youtube.playlist.Playlist", new=mock_pl)

    return mock_yt, mock_pl
