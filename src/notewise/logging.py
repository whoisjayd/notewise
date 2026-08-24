"""Centralized structlog configuration for NoteWise.

Call ``configure_logging()`` once at application startup from the CLI entry
point before any business logic runs. All modules use structlog via
``structlog.get_logger(__name__)``.
"""

from __future__ import annotations

import logging
import os
import re
import stat
import sys
import threading
from collections.abc import Mapping, MutableMapping
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

from notewise._constants import (
    CONFIG_FILE_PERMISSION_MODE,
    GROQ_API_KEY_PATTERN,
    LOGS_DIR_NAME,
    PROVIDER_SECRET_ENV_KEYS,
    SENSITIVE_KEY_SUFFIXES,
    SESSION_LOG_FALLBACK_DISABLED_MESSAGE,
    SESSION_LOG_PREFIX,
    SESSION_LOG_SYMLINK_REFUSED_EVENT,
    THIRD_PARTY_DIAGNOSTIC_LOGGERS,
)


if TYPE_CHECKING:
    from pathlib import Path


_SESSION_LOG_PATH: Path | None = None
_LOGGING_LOCK = threading.Lock()
_LOGGING_CONFIGURED = False
_REDACTED = "[REDACTED]"
_SESSION_LOG_OPEN_FLAGS = (
    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
)
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
    | {re.sub(r"[^a-z0-9]", "", key.lower()) for key in PROVIDER_SECRET_ENV_KEYS}
)
_ASSIGNMENT_REDACTION_PATTERN = re.compile(
    r"(?i)(?P<key_quote>[\"']?)\b(?P<key>[a-z0-9_]*(?:api_key|access_key_id|"
    r"secret_access_key|session_token|access_token|refresh_token)|"
    r"authorization|token|"
    r"secret|password|cookie(?:s)?|youtube_cookie_file)\b(?P=key_quote)"
    r"(?P<sep>\s*[:=]\s*)"
    r"(?P<value_quote>[\"']?)"
    r"(?P<value>'[^']*'|\"[^\"]*\"|[^\s,\]}]+)"
    r"(?P=value_quote)"
)
_BEARER_TOKEN_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._+/=-]{10,}")
_GOOGLE_API_KEY_PATTERN = re.compile(r"\bAIza[0-9A-Za-z\-_]{20,}\b")
_OPENAI_STYLE_KEY_PATTERN = re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9._-]{16,}\b")
_GROQ_API_KEY_PATTERN = re.compile(GROQ_API_KEY_PATTERN)
_SENSITIVE_TEXT_PATTERNS = (
    _BEARER_TOKEN_PATTERN,
    _GOOGLE_API_KEY_PATTERN,
    _OPENAI_STYLE_KEY_PATTERN,
    _GROQ_API_KEY_PATTERN,
)


def _normalize_sensitive_key(key: str) -> str:
    """Normalize a key name for secret matching."""
    return re.sub(r"[^a-z0-9]", "", key.lower())


def _is_sensitive_key(key: str) -> bool:
    """Return whether a mapping key should be redacted."""
    normalized = _normalize_sensitive_key(key)
    return normalized in _SENSITIVE_KEY_NAMES or normalized.endswith(
        SENSITIVE_KEY_SUFFIXES
    )


def redact_sensitive_text(text: str) -> str:
    """Redact API keys, tokens, and similar credentials from log text."""
    sanitized = text
    # Text-shaped secrets (bearer headers, raw key formats) must be masked
    # before assignment-style redaction, which only consumes the value slot.
    for pattern in _SENSITIVE_TEXT_PATTERNS:
        sanitized = pattern.sub(_REDACTED, sanitized)

    def _redact_assignment(match: re.Match[str]) -> str:
        value = match.group("value")
        # Idempotency guard: an already-redacted value must stay wrapped
        # exactly once, otherwise repeated redaction grows '[REDACTED]'
        # into '[REDACTED]]'. A bare (unquoted) marker is captured without
        # its closing bracket because the value pattern stops at ']'.
        if value == _REDACTED or (
            not match.group("value_quote") and f"{value}]" == _REDACTED
        ):
            return match.group(0)
        key_quote = match.group("key_quote")
        value_quote = match.group("value_quote")
        return (
            f"{key_quote}{match.group('key')}{key_quote}"
            f"{match.group('sep')}"
            f"{value_quote}{_REDACTED}{value_quote}"
        )

    sanitized = _ASSIGNMENT_REDACTION_PATTERN.sub(_redact_assignment, sanitized)
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
    if state_dir is None:
        # Lazy import avoids a config -> logging import cycle during startup.
        from notewise.config import get_state_dir

        state_dir = get_state_dir()
    base = state_dir
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
            if log_path.is_symlink():
                # Never unlink a symlinked entry; it may point outside the log dir.
                continue
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


def _lstat_is_regular_file(path: Path) -> bool:
    """Return True when *path* is a plain regular file (never a symlink)."""
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except OSError:
        return False


def _prepare_session_log(log_dir: Path, ts: str) -> Path | None:
    """Atomically reserve a safe session log file path.

    The predictable timestamped name is created exclusively with restrictive
    permissions, closing the TOCTOU window between an existence check and
    the FileHandler attach. An existing plain regular file may be reused; a
    planted symlink is refused once and retried on a pid-suffixed fallback
    name. When both candidates are unsafe, file logging is disabled instead
    of following the link.
    """
    session_logger = structlog.get_logger(__name__)
    primary = log_dir / f"{SESSION_LOG_PREFIX}-{ts}.log"
    fallback = log_dir / f"{SESSION_LOG_PREFIX}-{ts}-{os.getpid()}.log"

    refused_path = ""
    for attempt, candidate in enumerate((primary, fallback)):
        try:
            fd = os.open(
                candidate,
                _SESSION_LOG_OPEN_FLAGS,
                CONFIG_FILE_PERMISSION_MODE,
            )
        except FileExistsError:
            if _lstat_is_regular_file(candidate):
                return candidate
            refused_path = str(candidate)
        else:
            os.close(fd)
            return candidate

        if attempt == 0:
            # A planted symlink at the predictable session log path must
            # not be followed; fall back once to a pid-suffixed filename.
            session_logger.warning(
                SESSION_LOG_SYMLINK_REFUSED_EVENT,
                refused_path=refused_path,
            )

    session_logger.warning(SESSION_LOG_FALLBACK_DISABLED_MESSAGE)
    return None


def configure_logging(
    *,
    state_dir: Path | None = None,
    env: str | None = None,
    verbose: bool = False,
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

        # Keep terminal quiet via NullHandler while preserving file diagnostics.
        os.environ.setdefault("LITELLM_LOG", "ERROR")
        diagnostic_level = logging.DEBUG if verbose else logging.WARNING
        for name in THIRD_PARTY_DIAGNOSTIC_LOGGERS:
            diagnostic_logger = logging.getLogger(name)
            diagnostic_logger.setLevel(diagnostic_level)
            diagnostic_logger.propagate = True
            # Some provider libraries attach their own StreamHandler to stderr.
            # Remove local handlers so records flow only through NoteWise's root
            # file handler, where redaction is applied and the Rich UI stays clean.
            for handler in list(diagnostic_logger.handlers):
                diagnostic_logger.removeHandler(handler)

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
            log_dir = get_log_dir(state_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            session_log = _prepare_session_log(log_dir, ts)
            if session_log is not None:
                file_handler = logging.FileHandler(session_log, encoding="utf-8")
                file_handler.setLevel(logging.DEBUG)
                file_handler.setFormatter(formatter)
                root.addHandler(file_handler)
                _SESSION_LOG_PATH = session_log
        except Exception:
            logging.getLogger(__name__).warning(
                "logging.session_log_initialization_failed",
                exc_info=True,
            )
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
