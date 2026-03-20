"""Shared pipeline state and small orchestration helpers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from yt_study.utils import dedupe_ordered


def dedupe_video_ids(video_ids: list[str]) -> list[str]:
    """Return video IDs in first-seen order with duplicates removed."""
    return dedupe_ordered(video_ids)


@dataclass
class PipelineSharedState:
    """Shared coordination primitives for multi-pipeline batch processing."""

    semaphore: asyncio.Semaphore
    output_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    reserved_output_targets: set[Path] = field(default_factory=set)
