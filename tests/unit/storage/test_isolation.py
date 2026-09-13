"""Tests for shared-state cleanup performed by the test harness."""

from __future__ import annotations

import asyncio
import gc

from notewise.pipeline._limiter import (
    _LOOP_SCOPED_LIMITERS,
    _SENTINEL_LIMITERS,
    clear_youtube_limiters,
    get_youtube_limiter,
)
from notewise.storage.repository import DatabaseRepository


def test_test_harness_can_populate_shared_state(tmp_path):
    """This test leaves shared state dirty so the next test can verify teardown."""
    DatabaseRepository.get_instance(tmp_path / "cache.db")
    get_youtube_limiter(5)

    assert DatabaseRepository._instances
    assert _SENTINEL_LIMITERS


def test_test_harness_clears_shared_state_between_tests():
    """Autouse teardown should clear DB singletons and YouTube limiters."""
    assert DatabaseRepository._instances == {}
    assert _SENTINEL_LIMITERS == {}
    assert len(_LOOP_SCOPED_LIMITERS) == 0


async def test_loop_scoped_limiter_is_shared_within_one_loop():
    """Two calls in the same running loop must reuse the same limiter."""
    first = get_youtube_limiter(5)
    second = get_youtube_limiter(5)

    assert first is second
    assert len(_LOOP_SCOPED_LIMITERS) == 1


def test_loop_scoped_limiter_is_dropped_when_its_loop_is_garbage_collected():
    """A dead loop's limiters must not leak, and its id() must not be reused
    to silently hand back a stale limiter to an unrelated new loop.

    The limiter is actually acquired (not just constructed): AsyncLimiter
    only stores a strong reference back to its loop once ``acquire()`` runs,
    and that reference is exactly what would keep the loop pinned alive
    through this cache if eviction only happened on garbage collection.
    """
    clear_youtube_limiters()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_acquire_youtube_limiter())
        assert len(_LOOP_SCOPED_LIMITERS) == 1
    finally:
        loop.close()

    del loop
    gc.collect()

    assert len(_LOOP_SCOPED_LIMITERS) == 0


async def _acquire_youtube_limiter():
    async with get_youtube_limiter(5):
        pass
