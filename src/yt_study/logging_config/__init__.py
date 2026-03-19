"""Logging utilities for yt-study (structlog-based)."""

from typing import cast

import structlog

from .setup import configure_logging, get_session_log_path


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog bound logger for the given name."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))


__all__ = ["configure_logging", "get_logger", "get_session_log_path"]
