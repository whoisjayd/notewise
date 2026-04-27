"""Tests for log formatting and redaction."""

from __future__ import annotations

import os
import time
from types import SimpleNamespace

import structlog

import notewise.logging as logging_module
from notewise.logging import (
    configure_logging,
    make_log_safe_text,
    prune_log_files,
    redact_sensitive_text,
)


def _reset_logging_state() -> None:
    logging_module._SESSION_LOG_PATH = None
    logging_module._LOGGING_CONFIGURED = False
    root_logger = logging_module.logging.getLogger()
    for handler in list(root_logger.handlers):
        handler.close()
    root_logger.handlers.clear()


def test_redact_sensitive_text_masks_common_secret_shapes():
    """Raw API keys and bearer tokens should never survive log redaction."""
    google_key = "AIza" + "A" * 32
    bearer = "Bearer abcdefghijklmnopqrstuvwxyz123456"
    openrouter_key = "or_" + "B" * 32
    aws_secret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCY" + "C" * 12

    redacted = redact_sensitive_text(
        f"gemini_api_key={google_key} authorization: {bearer} "
        f"OPENROUTER_API_KEY={openrouter_key} "
        f"AWS_SECRET_ACCESS_KEY={aws_secret}"
    )

    assert google_key not in redacted
    assert bearer not in redacted
    assert openrouter_key not in redacted
    assert aws_secret not in redacted
    assert "[REDACTED]" in redacted


def test_make_log_safe_text_escapes_unencodable_terminal_characters(monkeypatch):
    """Log text should remain printable even on cp1252-style terminals."""
    monkeypatch.setattr(
        logging_module.sys,
        "stderr",
        SimpleNamespace(encoding="cp1252"),
    )
    monkeypatch.setattr(
        logging_module.sys,
        "stdout",
        SimpleNamespace(encoding="cp1252"),
    )

    safe_text = make_log_safe_text("provider failed → retry later")

    assert safe_text == "provider failed \\u2192 retry later"


def test_configure_logging_writes_plain_redacted_tracebacks(tmp_path):
    """Session logs should stay readable and redact sensitive structured values."""
    _reset_logging_state()
    log_path = configure_logging(state_dir=tmp_path)
    assert log_path is not None

    google_key = "AIza" + "B" * 32
    bearer_token = "Bearer zyxwvutsrqponmlkjihgfedcba987654"
    logger = structlog.get_logger("tests.logging")

    try:
        raise RuntimeError(
            f"provider failed gemini_api_key={google_key} authorization={bearer_token}"
        )
    except RuntimeError:
        logger.error(
            "request.failed",
            payload={
                "gemini_api_key": google_key,
                "Authorization": bearer_token,
            },
            exc_info=True,
        )

    text = log_path.read_text(encoding="utf-8")

    assert google_key not in text
    assert bearer_token not in text
    assert "[REDACTED]" in text
    assert "Traceback (most recent call last)" in text
    assert "╭" not in text


def test_configure_logging_is_idempotent(tmp_path):
    """Repeated configure calls should reuse one session log file."""
    _reset_logging_state()
    first = configure_logging(state_dir=tmp_path)
    second = configure_logging(state_dir=tmp_path)

    assert first is not None
    assert second == first
    assert logging_module.get_session_log_path() == first
    assert len(list((tmp_path / "logs").glob("*.log"))) == 1


def test_configure_logging_suppresses_verbose_provider_payload_logs(tmp_path):
    """Third-party clients should not dump prompts or request payloads to logs."""
    _reset_logging_state()
    configure_logging(state_dir=tmp_path)

    for logger_name in ("openai", "openai._base_client", "LiteLLM", "litellm"):
        logger = logging_module.logging.getLogger(logger_name)
        assert logger.getEffectiveLevel() >= logging_module.logging.WARNING

    assert logging_module.logging.getLogger("openai._base_client").propagate is False


def test_prune_log_files_removes_only_old_inactive_logs(tmp_path):
    """Log pruning should skip the active session log and remove stale files."""
    _reset_logging_state()
    active = configure_logging(state_dir=tmp_path)
    assert active is not None
    log_dir = tmp_path / "logs"
    stale = log_dir / "stale.log"
    fresh = log_dir / "fresh.log"
    stale.write_text("old", encoding="utf-8")
    fresh.write_text("new", encoding="utf-8")

    old_time = time.time() - (10 * 24 * 60 * 60)
    fresh_time = time.time() - (1 * 24 * 60 * 60)
    os.utime(stale, (old_time, old_time))
    os.utime(fresh, (fresh_time, fresh_time))

    deleted = prune_log_files(older_than_days=7, state_dir=tmp_path)

    assert deleted == 1
    assert active.exists()
    assert not stale.exists()
    assert fresh.exists()
