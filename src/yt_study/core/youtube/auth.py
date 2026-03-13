"""Shared helpers for YouTube OAuth auth configuration and token handling."""

import json
import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

_OAUTH_ERROR_PATTERNS = (
    "invalid_grant",
    "invalid_token",
    "token has been expired or revoked",
    "token expired",
    "oauth",
    "refresh_token",
)


@dataclass(frozen=True)
class OAuthTokenStatus:
    """Basic state extracted from a pytubefix OAuth token cache file."""

    exists: bool
    expired: bool
    has_refresh_token: bool
    parse_error: bool = False


def build_oauth_kwargs(
    *,
    use_oauth: bool,
    allow_oauth_cache: bool,
    token_file: str | None,
) -> dict[str, Any]:
    """Build pytubefix OAuth kwargs for YouTube/Playlist constructors."""
    if not use_oauth:
        return {}

    auth_kwargs: dict[str, Any] = {
        "use_oauth": True,
        "allow_oauth_cache": allow_oauth_cache,
    }
    if token_file:
        auth_kwargs["token_file"] = token_file
    return auth_kwargs


def resolve_token_path(token_file: str | None) -> Path | None:
    """Resolve a token-file string to a Path, or None when unset."""
    if not token_file:
        return None

    try:
        return Path(token_file).expanduser().resolve()
    except Exception:
        return Path(token_file).expanduser()


def looks_like_oauth_token_error(error: Exception) -> bool:
    """
    Heuristic for OAuth token cache/refresh failures.

    pytubefix can surface provider failures in different exception shapes
    (for example, KeyError('access_token') or JSON error strings).
    """
    if isinstance(error, KeyError) and "access_token" in str(error):
        return True

    message = str(error).lower()
    return any(pattern in message for pattern in _OAUTH_ERROR_PATTERNS)


def clear_oauth_token_file(token_file: str | None) -> bool:
    """Delete a cached OAuth token file if it exists."""
    resolved = resolve_token_path(token_file)
    if resolved is None or not resolved.exists():
        return False

    try:
        resolved.unlink()
        return True
    except Exception as exc:
        logger.warning(f"Failed to clear OAuth token cache file: {exc}")
        return False


def inspect_oauth_token_file(token_file: str | None) -> OAuthTokenStatus:
    """Inspect cache token file metadata (exists/expired/refresh token availability)."""
    resolved = resolve_token_path(token_file)
    if resolved is None or not resolved.exists():
        return OAuthTokenStatus(
            exists=False,
            expired=False,
            has_refresh_token=False,
            parse_error=False,
        )

    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return OAuthTokenStatus(
            exists=True,
            expired=False,
            has_refresh_token=False,
            parse_error=True,
        )
    if not isinstance(data, dict):
        return OAuthTokenStatus(
            exists=True,
            expired=False,
            has_refresh_token=False,
            parse_error=True,
        )

    expires_epoch = _coerce_expires_epoch(data.get("expires"))
    has_access_token = bool(data.get("access_token"))
    # Treat cache entries with an access token but missing/invalid expiry as stale.
    expired = has_access_token and (
        expires_epoch is None or expires_epoch <= time.time()
    )
    return OAuthTokenStatus(
        exists=True,
        expired=expired,
        has_refresh_token=bool(data.get("refresh_token")),
        parse_error=False,
    )


def _coerce_expires_epoch(raw_expires: Any) -> float | None:
    """Best-effort parse for token expiry epoch values."""
    if isinstance(raw_expires, (int, float)):
        value = float(raw_expires)
        if not math.isfinite(value):
            return None
        return value
    if isinstance(raw_expires, str):
        candidate = raw_expires.strip()
        if not candidate:
            return None
        try:
            value = float(candidate)
        except ValueError:
            return None
        if not math.isfinite(value):
            return None
        return value
    return None


def maybe_reset_oauth_token_for_retry(
    *,
    error: Exception,
    use_oauth: bool,
    allow_oauth_cache: bool,
    token_file: str | None,
    already_retried: bool,
) -> bool:
    """
    Clear token cache once when it looks stale/invalid and caller wants one retry.

    Returns True when cache was cleared and caller should retry immediately.
    """
    if already_retried:
        return False
    if not (use_oauth and allow_oauth_cache and token_file):
        return False
    if not looks_like_oauth_token_error(error):
        return False

    cleared = clear_oauth_token_file(token_file)
    if cleared:
        logger.warning(
            "Detected stale YouTube OAuth token cache, clearing it and retrying once."
        )
    return cleared
