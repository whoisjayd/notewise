"""YouTube request rate limiter shared across pipeline instances."""

from __future__ import annotations

import asyncio
import weakref

from aiolimiter import AsyncLimiter

from notewise._constants import YOUTUBE_LIMIT_PERIOD_SECONDS


def _create_limiter(requests_per_minute: int, *, time_period: float) -> AsyncLimiter:
    """Create the declared runtime limiter implementation."""
    return AsyncLimiter(max_rate=requests_per_minute, time_period=time_period)


# Keyed by the actual loop object (weakly), not id(loop): once a loop is
# garbage collected its entry disappears automatically, so this can't leak
# across a long-lived process's many event loops, and it can't collide when
# CPython reuses a dead loop's id() for an unrelated new loop.
_LOOP_SCOPED_LIMITERS: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, dict[int, AsyncLimiter]
] = weakref.WeakKeyDictionary()
# Fallback for callers with no running loop (rare; not loop-scoped).
_SENTINEL_LIMITERS: dict[int, AsyncLimiter] = {}


def get_youtube_limiter(requests_per_minute: int) -> AsyncLimiter:
    """Return a shared AsyncLimiter for the current event loop and rate cap.

    Sharing by (loop, rate) lets concurrent Pipeline instances in the same
    event loop throttle together while avoiding cross-loop reuse.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        limiters = _SENTINEL_LIMITERS
    else:
        limiters = _LOOP_SCOPED_LIMITERS.setdefault(loop, {})

    limiter = limiters.get(requests_per_minute)
    if limiter is None:
        limiter = _create_limiter(
            requests_per_minute,
            time_period=YOUTUBE_LIMIT_PERIOD_SECONDS,
        )
        limiters[requests_per_minute] = limiter
    return limiter


def clear_youtube_limiters() -> None:
    """Remove all cached rate limiters. Call in tests or on event-loop teardown."""
    _LOOP_SCOPED_LIMITERS.clear()
    _SENTINEL_LIMITERS.clear()
