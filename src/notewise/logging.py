"""Centralized structlog configuration for NoteWise.

Call ``configure_logging()`` once at application startup from the CLI entry
point before any business logic runs. All modules use structlog via
``structlog.get_logger(__name__)``.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import threading
from collections.abc import Mapping, MutableMapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import structlog

from notewise._constants import LOGS_DIR_NAME, SESSION_LOG_PREFIX, STATE_DIR_NAME


_NOISY_LOGGERS = ("LiteLLM", "litellm", "httpx", "httpcore")
_SESSION_LOG_PATH: Path | None = None
_LOGGING_LOCK = threading.Lock()
_LOGGING_CONFIGURED = False
_REDACTED = "[REDACTED]"
_SENSITIVE_KEY_NAMES = frozenset(
    {
        "geminiapikey",
        "openaiapikey",
        "anthropicapikey",
        "groqapikey",
        "xaiapikey",
        "mistralapikey",
        "cohereapikey",
        "deepseekapikey",
        "apikey",
        "accesstoken",
        "refreshtoken",
        "token",
        "authorization",
        "secret",
        "password",
        "cookie",
        "cookies",
        "youtubecookiefile",
    }
)
_ASSIGNMENT_REDACTION_PATTERN = re.compile(
    r"(?i)(?P<key>\b(?:gemini|openai|anthropic|groq|xai|mistral|cohere|deepseek)?"
    r"_?api[_ -]?key|access[_ -]?token|refresh[_ -]?token|authorization|token|"
    r"secret|password|cookie(?:s)?|youtube_cookie_file\b)"
    r"(?P<sep>\s*[:=]\s*)"
    r"(?P<value>'[^']*'|\"[^\"]*\"|[^\s,\]}]+)"
)
_BEARER_TOKEN_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._+/=-]{10,}")
_GOOGLE_API_KEY_PATTERN = re.compile(r"\bAIza[0-9A-Za-z\-_]{20,}\b")
_OPENAI_STYLE_KEY_PATTERN = re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9._-]{16,}\b")
_SENSITIVE_TEXT_PATTERNS = (
    _BEARER_TOKEN_PATTERN,
    _GOOGLE_API_KEY_PATTERN,
    _OPENAI_STYLE_KEY_PATTERN,
)


def _normalize_sensitive_key(key: str) -> str:
    """Normalize a key name for secret matching."""
    return re.sub(r"[^a-z0-9]", "", key.lower())


def _is_sensitive_key(key: str) -> bool:
    """Return whether a mapping key should be redacted."""
    return _normalize_sensitive_key(key) in _SENSITIVE_KEY_NAMES


def redact_sensitive_text(text: str) -> str:
    """Redact API keys, tokens, and similar credentials from log text."""
    sanitized = _ASSIGNMENT_REDACTION_PATTERN.sub(
        lambda match: f"{match.group('key')}{match.group('sep')}{_REDACTED}",
        text,
    )
    for pattern in _SENSITIVE_TEXT_PATTERNS:
        sanitized = pattern.sub(_REDACTED, sanitized)
    return sanitized


def make_log_safe_text(text: str) -> str:
    """Return text that won't crash when emitted on non-UTF terminals."""
    encoding = sys.stderr.encoding or sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="backslashreplace").decode(encoding)


def redact_sensitive_data(value: Any) -> Any:
    """Recursively redact sensitive values in structured log payloads."""
    if isinstance(value, Mapping):
        return {
            key: (
                _REDACTED if _is_sensitive_key(str(key)) else redact_sensitive_data(val)
            )
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item) for item in value)
    if isinstance(value, set):
        return {redact_sensitive_data(item) for item in value}
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value


def _redact_event_dict(
    _logger: Any,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> Mapping[str, Any]:
    """Apply recursive secret redaction to a structlog event payload."""
    return {
        key: (_REDACTED if _is_sensitive_key(key) else redact_sensitive_data(value))
        for key, value in event_dict.items()
    }


def get_session_log_path() -> Path | None:
    """Return the current session log file path, if configured."""
    with _LOGGING_LOCK:
        return _SESSION_LOG_PATH


def get_log_dir(state_dir: Path | None = None) -> Path:
    """Return the directory that stores notewise session logs."""
    base = state_dir or (Path.home() / STATE_DIR_NAME)
    return base / LOGS_DIR_NAME


def prune_log_files(
    *,
    older_than_days: int = 7,
    state_dir: Path | None = None,
) -> int:
    """Remove old session log files while keeping the active session log intact."""
    log_dir = get_log_dir(state_dir)
    if not log_dir.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=max(older_than_days, 0))
    deleted = 0
    with _LOGGING_LOCK:
        active_log = _SESSION_LOG_PATH
        for log_path in log_dir.glob("*.log"):
            if active_log is not None and log_path.resolve() == active_log.resolve():
                continue
            try:
                modified = datetime.fromtimestamp(log_path.stat().st_mtime)
            except OSError:
                continue
            if modified >= cutoff:
                continue
            try:
                log_path.unlink()
                deleted += 1
            except OSError:
                continue
    return deleted


def configure_logging(
    *,
    state_dir: Path | None = None,
    env: str | None = None,
) -> Path | None:
    """Configure structlog and stdlib logging for NoteWise.

    Safe to call multiple times (subsequent calls reconfigure).

    Args:
        state_dir: Base dir for log files. Defaults to ~/.notewise.
        env: Override environment ('development'|'production').
             Reads NOTEWISE_ENV env var if not provided.

    Returns:
        Path to the session log file, or None if file logging is unavailable.
    """
    global _LOGGING_CONFIGURED, _SESSION_LOG_PATH
    del env
    with _LOGGING_LOCK:
        if _LOGGING_CONFIGURED:
            return _SESSION_LOG_PATH

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
            _redact_event_dict,
        ]

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

        console_handler = logging.NullHandler()
        console_handler.setLevel(logging.CRITICAL + 1)
        root.addHandler(console_handler)

        session_log: Path | None = None
        try:
            base = state_dir or (Path.home() / STATE_DIR_NAME)
            log_dir = base / LOGS_DIR_NAME
            log_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            session_log = log_dir / f"{SESSION_LOG_PREFIX}-{ts}.log"
            file_handler = logging.FileHandler(session_log, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
            _SESSION_LOG_PATH = session_log
        except Exception:
            _SESSION_LOG_PATH = None

        structlog.configure(
            processors=[
                *shared_processors,
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        _LOGGING_CONFIGURED = True
        return session_log
