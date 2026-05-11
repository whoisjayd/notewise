"""YouTube request rate limiter shared across pipeline instances."""

from __future__ import annotations

import asyncio

from aiolimiter import AsyncLimiter

from notewise._constants import RUN_LOOP_SENTINEL, YOUTUBE_LIMIT_PERIOD_SECONDS


def _create_limiter(requests_per_minute: int, *, time_period: float) -> AsyncLimiter:
    """Create the declared runtime limiter implementation."""
    return AsyncLimiter(max_rate=requests_per_minute, time_period=time_period)


_GLOBAL_YOUTUBE_LIMITERS: dict[tuple[int, int], AsyncLimiter] = {}


def get_youtube_limiter(requests_per_minute: int) -> AsyncLimiter:
    """Return a shared AsyncLimiter for the current event loop and rate cap.

    Sharing by ``(loop_id, rate)`` lets concurrent Pipeline instances in the
    same event loop throttle together while avoiding cross-loop reuse.
    """
    try:
        loop_key = id(asyncio.get_running_loop())
    except RuntimeError:
        loop_key = RUN_LOOP_SENTINEL

    key = (loop_key, requests_per_minute)
    limiter = _GLOBAL_YOUTUBE_LIMITERS.get(key)
    if limiter is None:
        limiter = _create_limiter(
            requests_per_minute,
            time_period=YOUTUBE_LIMIT_PERIOD_SECONDS,
        )
        _GLOBAL_YOUTUBE_LIMITERS[key] = limiter
    return limiter


def clear_youtube_limiters() -> None:
    """Remove all cached rate limiters. Call in tests or on event-loop teardown."""
    _GLOBAL_YOUTUBE_LIMITERS.clear()
