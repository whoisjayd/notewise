"""Shared helpers for parsing and defaulting config values."""

from pathlib import Path


_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}


def parse_bool_setting(value: str | None, default: bool) -> bool:
    """Parse a boolean-like config value with a default fallback."""
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in _TRUTHY:
        return True
    if normalized in _FALSY:
        return False
    return default


def is_valid_bool_setting(value: str | None) -> bool:
    """Return True when a bool-like string is recognized or unset."""
    if value is None:
        return True
    normalized = value.strip().lower()
    return normalized in _TRUTHY or normalized in _FALSY


def default_youtube_oauth_token_file() -> Path:
    """Return the canonical default YouTube OAuth token cache path."""
    return Path.home() / ".yt-study" / "youtube_token.json"
