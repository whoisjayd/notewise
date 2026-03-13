"""Tests for YouTube OAuth helper utilities."""

import json
import time

from yt_study.core.youtube.auth import (
    build_oauth_kwargs,
    inspect_oauth_token_file,
    maybe_reset_oauth_token_for_retry,
)


def test_build_oauth_kwargs_disabled_returns_empty():
    """OAuth kwargs should be empty when OAuth is disabled."""
    kwargs = build_oauth_kwargs(
        use_oauth=False,
        allow_oauth_cache=True,
        token_file="token.json",
    )
    assert kwargs == {}


def test_build_oauth_kwargs_enabled_includes_token_file():
    """OAuth kwargs should forward cache controls and token file."""
    kwargs = build_oauth_kwargs(
        use_oauth=True,
        allow_oauth_cache=False,
        token_file="token.json",
    )
    assert kwargs == {
        "use_oauth": True,
        "allow_oauth_cache": False,
        "token_file": "token.json",
    }


def test_inspect_oauth_token_file_missing(tmp_path):
    """Missing token file should return a non-error empty status."""
    token_file = tmp_path / "missing-token.json"
    status = inspect_oauth_token_file(str(token_file))
    assert status.exists is False
    assert status.expired is False
    assert status.has_refresh_token is False
    assert status.parse_error is False


def test_inspect_oauth_token_file_parse_error(tmp_path):
    """Invalid JSON should be reported as parse error."""
    token_file = tmp_path / "broken-token.json"
    token_file.write_text("{not-json", encoding="utf-8")

    status = inspect_oauth_token_file(str(token_file))
    assert status.exists is True
    assert status.parse_error is True
    assert status.expired is False


def test_inspect_oauth_token_file_accepts_string_expiry(tmp_path):
    """String-form expiry should be parsed to detect expired caches."""
    token_file = tmp_path / "token.json"
    token_file.write_text(
        json.dumps(
            {
                "access_token": "access",
                "refresh_token": "refresh",
                "expires": str(time.time() - 30),
            }
        ),
        encoding="utf-8",
    )

    status = inspect_oauth_token_file(str(token_file))
    assert status.exists is True
    assert status.expired is True
    assert status.has_refresh_token is True
    assert status.parse_error is False


def test_inspect_oauth_token_file_invalid_expiry_is_stale_when_access_present(tmp_path):
    """Access-token cache entries with invalid expiry are treated as stale."""
    token_file = tmp_path / "token.json"
    token_file.write_text(
        json.dumps(
            {
                "access_token": "access",
                "refresh_token": "refresh",
                "expires": "not-a-number",
            }
        ),
        encoding="utf-8",
    )

    status = inspect_oauth_token_file(str(token_file))
    assert status.exists is True
    assert status.expired is True
    assert status.has_refresh_token is True
    assert status.parse_error is False


def test_maybe_reset_oauth_token_for_retry_clears_once(tmp_path):
    """OAuth-like errors should clear stale cache once and request retry."""
    token_file = tmp_path / "token.json"
    token_file.write_text("{}", encoding="utf-8")

    should_retry = maybe_reset_oauth_token_for_retry(
        error=KeyError("access_token"),
        use_oauth=True,
        allow_oauth_cache=True,
        token_file=str(token_file),
        already_retried=False,
    )
    assert should_retry is True
    assert not token_file.exists()

    # Second pass should not trigger another reset/retry.
    should_retry_again = maybe_reset_oauth_token_for_retry(
        error=KeyError("access_token"),
        use_oauth=True,
        allow_oauth_cache=True,
        token_file=str(token_file),
        already_retried=True,
    )
    assert should_retry_again is False
