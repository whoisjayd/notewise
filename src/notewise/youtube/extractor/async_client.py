"""Async wrapper around the synchronous YouTubeExtractorClient.

All public methods are async and run blocking HTTP work in a thread pool via
``asyncio.to_thread``.  Callers never need to sprinkle ``asyncio.to_thread``
themselves — this is the single async boundary for YouTube I/O.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

import structlog

from .client import YouTubeExtractorClient, YouTubeExtractorConfig


logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class AsyncYouTubeExtractorClient:
    """Async facade over :class:`YouTubeExtractorClient`.

    All network I/O is delegated to a thread pool so the event loop is never
    blocked.  One instance can be reused across many concurrent requests.
    """

    def __init__(self, config: YouTubeExtractorConfig | None = None) -> None:
        self._sync = YouTubeExtractorClient(config)

    # ── Public async API ──────────────────────────────────────────────────────

    async def metadata(self, target: str) -> dict[str, Any]:
        """Fetch metadata for a video or playlist URL (async)."""
        return await asyncio.to_thread(self._sync.metadata, target)

    async def chapters(self, target: str) -> dict[str, Any]:
        """Fetch chapter list for a video URL (async)."""
        return await asyncio.to_thread(self._sync.chapters, target)

    async def playlist(self, target: str) -> dict[str, Any]:
        """Fetch playlist entries (async)."""
        return await asyncio.to_thread(self._sync.playlist, target)

    async def transcript(
        self,
        target: str,
        languages: Iterable[str] | None = None,
        include_automatic: bool = True,
    ) -> dict[str, Any]:
        """Fetch transcript for a video URL (async)."""
        return await asyncio.to_thread(
            self._sync.transcript,
            target,
            languages,
            include_automatic,
        )

    async def video_metadata_full(self, target: str) -> dict[str, Any]:
        """Fetch the full raw video payload for a video id or URL (async).

        Lower-level than :meth:`metadata` — returns the internal extractor
        mapping including subtitles, automatic captions, and Innertube context.
        The target is forwarded unchanged so callers can pass either a bare
        video id or a fully-qualified watch URL.
        """
        return await asyncio.to_thread(self._sync._extract_video, target)
