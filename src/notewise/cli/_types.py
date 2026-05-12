"""Dataclasses, exceptions, and helpers used across the notewise CLI layer."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from notewise.domain.results import PipelineMetrics


if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class ResolvedSource:
    """Resolved work for a single input URL or playlist."""

    source_url: str
    label: str
    playlist_name: str
    video_ids: list[str]
    output_dir: Path
    is_playlist: bool = False


@dataclass
class _BatchVideoJob:
    """One video job scheduled through the shared batch worker pool."""

    sort_key: tuple[int, int]
    video_id: str
    output_dir: Path
    source_label: str
    is_playlist_video: bool = False


@dataclass
class _OrderedBatchFailure:
    """Failure row with a stable display order for final reporting."""

    sort_key: tuple[int, int]
    item: str
    message: str


@dataclass
class _BatchJobResult:
    """Result of one processed batch video job."""

    sort_key: tuple[int, int]
    success: bool
    display_title: str
    failure_row: _OrderedBatchFailure | None = None
    metrics: PipelineMetrics = field(default_factory=PipelineMetrics)


class _WorkerSlotManager:
    """Maps video IDs to dashboard worker slot indices (event-loop only)."""

    def __init__(self, concurrency: int) -> None:
        self._available: deque[int] = deque(range(concurrency))
        self._assigned: dict[str, int] = {}

    def acquire(self, video_id: str) -> int | None:
        """Assign the next available slot to *video_id*."""
        if self._available:
            slot = self._available.popleft()
            self._assigned[video_id] = slot
            return slot
        return None

    def release(self, video_id: str) -> int | None:
        """Return the slot held by *video_id* back to the pool."""
        slot = self._assigned.pop(video_id, None)
        if slot is not None:
            self._available.append(slot)
        return slot

    def get(self, video_id: str) -> int | None:
        """Return the currently assigned slot for *video_id*, if any."""
        return self._assigned.get(video_id)
