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
        limiters = _LOOP_SCOPED_LIMITERS.get(loop)
        if limiters is None:
            limiters = {}
            _LOOP_SCOPED_LIMITERS[loop] = limiters
            _evict_on_close(loop)

    limiter = limiters.get(requests_per_minute)
    if limiter is None:
        limiter = _create_limiter(
            requests_per_minute,
            time_period=YOUTUBE_LIMIT_PERIOD_SECONDS,
        )
        limiters[requests_per_minute] = limiter
    return limiter


def _evict_on_close(loop: asyncio.AbstractEventLoop) -> None:
    """Drop this loop's cached limiters as soon as it closes.

    Once acquired, ``AsyncLimiter`` keeps a strong reference to the loop it
    ran on (aiolimiter sets ``self._event_loop`` in ``acquire()``). Left
    alone, that reference runs straight back through this cache -- a
    module-level GC root -- to ``loop`` itself, so the weak key here would
    never actually go weak and the entry would never get collected. Evicting
    on ``close()`` (rather than waiting on GC) breaks that chain deterministically.
    """
    original_close = loop.close

    def close_and_evict() -> None:
        _LOOP_SCOPED_LIMITERS.pop(loop, None)
        original_close()

    loop.close = close_and_evict  # ty: ignore[invalid-assignment]


def clear_youtube_limiters() -> None:
    """Remove all cached rate limiters. Call in tests or on event-loop teardown."""
    _LOOP_SCOPED_LIMITERS.clear()
    _SENTINEL_LIMITERS.clear()
