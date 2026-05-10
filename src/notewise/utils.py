"""Shared utility helpers for notewise."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import TypeVar

from notewise._constants import (
    BOOL_SETTING_FALSY_VALUES,
    BOOL_SETTING_TRUTHY_VALUES,
    INVALID_FILENAME_CHARS_PATTERN,
    MASKED_SECRET_MIN_VISIBLE_LENGTH,
    MASKED_SECRET_PREFIX_LENGTH,
    MASKED_SECRET_SUFFIX_LENGTH,
    MAX_FILENAME_LENGTH,
    RESERVED_WINDOWS_FILENAME_PATTERN,
    SANITIZED_FILENAME_FALLBACK,
    WHITESPACE_PATTERN,
)


_RESERVED = re.compile(RESERVED_WINDOWS_FILENAME_PATTERN, re.IGNORECASE)

T = TypeVar("T")


def sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a cross-platform filename."""
    name = re.sub(INVALID_FILENAME_CHARS_PATTERN, "", name)
    name = re.sub(WHITESPACE_PATTERN, " ", name)
    name = name.strip().rstrip(".")
    if not name:
        return SANITIZED_FILENAME_FALLBACK
    if _RESERVED.match(name):
        name = f"_{name}"
    name = name[:MAX_FILENAME_LENGTH].rstrip(" .")
    if not name:
        return SANITIZED_FILENAME_FALLBACK
    return name


def safe_output_path(base_dir: Path, filename: str) -> Path:
    """Return a Path using a sanitized filename inside base_dir."""
    return base_dir / sanitize_filename(filename)


def dedupe_ordered(items: list[T]) -> list[T]:
    """Return items in first-seen order with duplicates removed."""
    return list(dict.fromkeys(items))


def coerce_int(value: object | None, *, default: int = 0) -> int:
    """Convert common scalar values to int with a default fallback."""
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, (str, bytes, bytearray)):
        try:
            return int(value)
        except ValueError:
            return default
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def coerce_non_negative_int(value: object) -> int:
    """Convert usage-like values to a non-negative int."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    if isinstance(value, str):
        try:
            return max(0, int(value.strip()))
        except ValueError:
            return 0
    return 0


def coerce_non_negative_float(value: object) -> float:
    """Convert usage-like values to a non-negative float."""
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return max(0.0, float(value))
    if isinstance(value, str):
        try:
            return max(0.0, float(value.strip()))
        except ValueError:
            return 0.0
    return 0.0


def mask_secret(value: str | None, *, suffix: str = "") -> str:
    """Return a partially masked secret for read-only display."""
    if not value:
        return "(not set)"
    if len(value) <= MASKED_SECRET_MIN_VISIBLE_LENGTH:
        return "***"
    return (
        f"{value[:MASKED_SECRET_PREFIX_LENGTH]}..."
        f"{value[-MASKED_SECRET_SUFFIX_LENGTH:]}{suffix}"
    )


def strip_wrapped_quotes(value: str) -> str:
    """Remove one layer of matching quotes from a config value."""
    if (
        len(value) >= 3
        and value[0] in {"r", "R"}
        and value[1] == value[-1]
        and value[1] in {'"', "'"}
    ):
        return value[2:-1]
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def parse_config_env_lines(lines: Iterable[str]) -> dict[str, str]:
    """Parse simple KEY=VALUE config.env lines."""
    parsed: dict[str, str] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed[key.strip()] = strip_wrapped_quotes(value.strip())
    return parsed


def parse_bool_setting(value: str | None, default: bool) -> bool:
    """Parse a boolean-like config value with a default fallback."""
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in BOOL_SETTING_TRUTHY_VALUES:
        return True
    if normalized in BOOL_SETTING_FALSY_VALUES:
        return False
    return default


def is_valid_bool_setting(value: str | None) -> bool:
    """Return True when a bool-like string is recognized or unset."""
    if value is None:
        return True
    normalized = value.strip().lower()
    return (
        normalized in BOOL_SETTING_TRUTHY_VALUES
        or normalized in BOOL_SETTING_FALSY_VALUES
    )


__all__ = [
    "sanitize_filename",
    "safe_output_path",
    "dedupe_ordered",
    "coerce_int",
    "coerce_non_negative_int",
    "coerce_non_negative_float",
    "mask_secret",
    "strip_wrapped_quotes",
    "parse_config_env_lines",
    "parse_bool_setting",
    "is_valid_bool_setting",
]
