"""Event system for progress reporting and decoupled communication."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Protocol


class EventType(Enum):
    """Types of events that can be emitted."""

    PROGRESS_UPDATE = auto()
    STATUS_CHANGE = auto()
    ERROR = auto()
    COMPLETED = auto()
    STARTED = auto()


@dataclass
class Event:
    """Base event class."""

    type: EventType
    video_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


class EventHandler(Protocol):
    """Protocol for event handlers."""

    def __call__(self, event: Event) -> None: ...


class EventEmitter:
    """Simple event emitter to decouple core logic from UI."""

    def __init__(self) -> None:
        self._handlers: list[EventHandler] = []

    def subscribe(self, handler: EventHandler) -> None:
        """Subscribe a new handler."""
        if handler not in self._handlers:
            self._handlers.append(handler)

    def unsubscribe(self, handler: EventHandler) -> None:
        """Unsubscribe a handler."""
        if handler in self._handlers:
            self._handlers.remove(handler)

    def emit(self, event: Event) -> None:
        """Emit an event to all subscribers."""
        import contextlib

        for handler in self._handlers:
            with contextlib.suppress(Exception):
                handler(event)

    def emit_progress(
        self,
        video_id: str | None,
        message: str,
        progress: float | None = None,
        **kwargs: Any,
    ) -> None:
        """Helper to emit progress updates."""
        data: dict[str, Any] = {"message": message}
        if progress is not None:
            data["progress"] = progress
        data.update(kwargs)
        self.emit(Event(EventType.PROGRESS_UPDATE, video_id, data))

    def emit_status(self, video_id: str | None, status: str, **kwargs: Any) -> None:
        """Helper to emit status changes."""
        data: dict[str, Any] = {"status": status}
        data.update(kwargs)
        self.emit(Event(EventType.STATUS_CHANGE, video_id, data))
