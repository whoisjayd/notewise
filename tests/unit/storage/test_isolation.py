"""Tests for shared-state cleanup performed by the test harness."""

from __future__ import annotations

from notewise.pipeline._limiter import _GLOBAL_YOUTUBE_LIMITERS, get_youtube_limiter
from notewise.storage.repository import DatabaseRepository


def test_test_harness_can_populate_shared_state(tmp_path):
    """This test leaves shared state dirty so the next test can verify teardown."""
    DatabaseRepository.get_instance(tmp_path / "cache.db")
    get_youtube_limiter(5)

    assert DatabaseRepository._instances
    assert _GLOBAL_YOUTUBE_LIMITERS


def test_test_harness_clears_shared_state_between_tests():
    """Autouse teardown should clear DB singletons and YouTube limiters."""
    assert DatabaseRepository._instances == {}
    assert _GLOBAL_YOUTUBE_LIMITERS == {}
