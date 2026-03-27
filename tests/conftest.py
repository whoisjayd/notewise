"""Test configuration and shared fixtures."""

from __future__ import annotations

import asyncio
import gc
import importlib
import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from notewise.pipeline import clear_youtube_limiters
from notewise.storage import DatabaseRepository


# ── Simple value fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def sample_video_id() -> str:
    return "dQw4w9WgXcQ"


@pytest.fixture
def sample_playlist_id() -> str:
    return "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"


# ── State isolation ───────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def isolate_state_dir(tmp_path, monkeypatch):
    """Redirect ~/.notewise to a tmp dir so tests never touch real state."""
    DatabaseRepository.close_all_instances()
    clear_youtube_limiters()
    gc.collect()
    monkeypatch.setenv("NOTEWISE_HOME", str(tmp_path / ".notewise"))
    yield
    DatabaseRepository.close_all_instances()
    clear_youtube_limiters()
    gc.collect()


@pytest.fixture
def temp_output_dir(tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    return out


# ── Config / provider mocks ───────────────────────────────────────────────────


@pytest.fixture
def mock_config(monkeypatch):
    """Real AppSettings instance with dummy API keys injected."""
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_gemini_key")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy_openai_key")
    from notewise.config import settings as config

    return config


@pytest.fixture
def mock_llm_provider():
    provider = MagicMock()
    provider.generate = AsyncMock(return_value="# Generated Notes\n\nTest content.")
    provider.model = "mock-model"
    return provider


# ── YouTube extractor mock ────────────────────────────────────────────────────


def _make_async_client_instance() -> MagicMock:
    """Build a MagicMock whose every public method is an AsyncMock.

    Mirrors the public interface of AsyncYouTubeExtractorClient so
    production code that does ``await client.transcript(...)`` works
    correctly against the mock.
    """
    instance = MagicMock()
    instance.metadata = AsyncMock(return_value={})
    instance.chapters = AsyncMock(return_value={})
    instance.transcript = AsyncMock(return_value={})
    instance.playlist = AsyncMock(return_value={})
    instance.video_metadata_full = AsyncMock(return_value={})
    return instance


@pytest.fixture
def mock_extractor_client(monkeypatch):
    """Patch AsyncYouTubeExtractorClient in every YouTube module.

    Each patch's ``.return_value`` is a MagicMock whose methods are
    AsyncMocks, so ``await client.transcript(...)`` works in tests.
    """

    def _patch(target: str):
        module_name, attr_name = target.rsplit(".", 1)
        module = importlib.import_module(module_name)
        cls_mock = MagicMock()
        cls_mock.return_value = _make_async_client_instance()
        monkeypatch.setattr(module, attr_name, cls_mock)
        return cls_mock

    return {
        "metadata": _patch("notewise.youtube.metadata.AsyncYouTubeExtractorClient"),
        "transcript": _patch("notewise.youtube.transcript.AsyncYouTubeExtractorClient"),
        "playlist": _patch("notewise.youtube.playlist.AsyncYouTubeExtractorClient"),
    }


def pytest_configure(config: pytest.Config) -> None:
    """Register the local asyncio mark used by the test suite."""
    config.addinivalue_line("markers", "asyncio: run the test in an event loop")
    config.addinivalue_line(
        "markers",
        "integration: run the test across multiple project layers",
    )
    config.addinivalue_line(
        "markers",
        "e2e: opt-in end-to-end smoke test that may hit live services",
    )


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register asyncio ini options when pytest-asyncio is unavailable."""
    parser.addini("asyncio_mode", "Local asyncio runner compatibility option")
    parser.addini(
        "asyncio_default_fixture_loop_scope",
        "Local asyncio runner compatibility option",
    )


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    """Run async tests without requiring pytest-asyncio in local environments."""
    if not inspect.iscoroutinefunction(pyfuncitem.obj):
        return None

    kwargs = {
        name: pyfuncitem.funcargs[name] for name in pyfuncitem._fixtureinfo.argnames
    }
    asyncio.run(pyfuncitem.obj(**kwargs))
    return True
