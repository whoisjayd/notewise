"""YouTube request rate limiter shared across pipeline instances."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol


class LimiterProtocol(Protocol):
    """Minimal async-context-manager interface used by the pipeline."""

    async def __aenter__(self) -> Any: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None: ...


class FallbackAsyncLimiter:
    """Minimal fallback limiter used when aiolimiter is unavailable."""

    def __init__(self, max_rate: int, time_period: float) -> None:
        self.max_rate = max_rate
        self.time_period = time_period

    async def __aenter__(self) -> FallbackAsyncLimiter:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        return None


def _create_limiter(
    requests_per_minute: int,
    *,
    time_period: float,
) -> LimiterProtocol:
    """Create the best available limiter implementation for this runtime."""
    try:
        from aiolimiter import AsyncLimiter
    except ModuleNotFoundError:
        return FallbackAsyncLimiter(
            max_rate=requests_per_minute,
            time_period=time_period,
        )

    return AsyncLimiter(max_rate=requests_per_minute, time_period=time_period)


_GLOBAL_YOUTUBE_LIMITERS: dict[tuple[int, int], Any] = {}


def get_youtube_limiter(requests_per_minute: int) -> LimiterProtocol:
    """Return a shared AsyncLimiter for the current event loop and rate cap.

    Sharing by ``(loop_id, rate)`` lets concurrent Pipeline instances in the
    same event loop throttle together while avoiding cross-loop reuse.
    """
    try:
        loop_key = id(asyncio.get_running_loop())
    except RuntimeError:
        loop_key = -1

    key = (loop_key, requests_per_minute)
    limiter = _GLOBAL_YOUTUBE_LIMITERS.get(key)
    if limiter is None:
        limiter = _create_limiter(requests_per_minute, time_period=60)
        _GLOBAL_YOUTUBE_LIMITERS[key] = limiter
    return limiter


def clear_youtube_limiters() -> None:
    """Remove all cached rate limiters. Call in tests or on event-loop teardown."""
    _GLOBAL_YOUTUBE_LIMITERS.clear()
