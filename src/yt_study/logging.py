"""Centralized structlog configuration for yt-study.

Call ``configure_logging()`` once at application startup from the CLI entry
point before any business logic runs. All modules use structlog via
``structlog.get_logger(__name__)``.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

import structlog

from yt_study._constants import LOGS_DIR_NAME, SESSION_LOG_PREFIX, STATE_DIR_NAME


_NOISY_LOGGERS = ("LiteLLM", "litellm", "httpx", "httpcore")
_SESSION_LOG_PATH: Path | None = None


def get_session_log_path() -> Path | None:
    """Return the current session log file path, if configured."""
    return _SESSION_LOG_PATH


def configure_logging(
    *,
    state_dir: Path | None = None,
    env: str | None = None,
) -> Path | None:
    """Configure structlog and stdlib logging for yt-study.

    Safe to call multiple times (subsequent calls reconfigure).

    Args:
        state_dir: Base dir for log files. Defaults to ~/.yt-study.
        env: Override environment ('development'|'production').
             Reads YT_STUDY_ENV env var if not provided.

    Returns:
        Path to the session log file, or None if file logging is unavailable.
    """
    global _SESSION_LOG_PATH
    del env

    # Suppress noisy third-party loggers early
    os.environ.setdefault("LITELLM_LOG", "ERROR")
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Shared processors applied to every log record
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # File logs should stay plain-text and editor-friendly.
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.KeyValueRenderer(
            sort_keys=False,
            key_order=["timestamp", "level", "logger", "event"],
        ),
        foreign_pre_chain=shared_processors,
    )

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    # Console handler — CRITICAL+1 keeps terminal clean for end users
    console_handler = logging.NullHandler()
    console_handler.setLevel(logging.CRITICAL + 1)
    root.addHandler(console_handler)

    # File handler — session-isolated, DEBUG+
    session_log: Path | None = None
    try:
        base = state_dir or (Path.home() / STATE_DIR_NAME)
        log_dir = base / LOGS_DIR_NAME
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        session_log = log_dir / f"{SESSION_LOG_PREFIX}-{ts}.log"
        fh = logging.FileHandler(session_log, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        root.addHandler(fh)
        _SESSION_LOG_PATH = session_log
    except Exception:
        pass  # Non-fatal; continue without file logging

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    return session_log
