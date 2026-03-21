"""Tests for log formatting and redaction."""

from __future__ import annotations

import structlog

from yt_study.logging import configure_logging, redact_sensitive_text


def test_redact_sensitive_text_masks_common_secret_shapes():
    """Raw API keys and bearer tokens should never survive log redaction."""
    google_key = "AIza" + "A" * 32
    bearer = "Bearer abcdefghijklmnopqrstuvwxyz123456"

    redacted = redact_sensitive_text(
        f"gemini_api_key={google_key} authorization: {bearer}"
    )

    assert google_key not in redacted
    assert bearer not in redacted
    assert "[REDACTED]" in redacted


def test_configure_logging_writes_plain_redacted_tracebacks(tmp_path):
    """Session logs should stay readable and redact sensitive structured values."""
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
