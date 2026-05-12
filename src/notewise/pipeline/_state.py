"""Shared pipeline state and small orchestration helpers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from notewise.utils import dedupe_ordered


if TYPE_CHECKING:
    from pathlib import Path


def dedupe_video_ids(video_ids: list[str]) -> list[str]:
    """Return video IDs in first-seen order with duplicates removed."""
    return dedupe_ordered(video_ids)


@dataclass
class PipelineSharedState:
    """Shared coordination primitives for multi-pipeline batch processing."""

    semaphore: asyncio.Semaphore
    chapter_semaphore: asyncio.Semaphore | None = None
    output_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    reserved_output_targets: set[Path] = field(default_factory=set)
