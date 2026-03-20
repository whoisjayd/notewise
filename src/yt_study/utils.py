"""Shared utility helpers for yt-study."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TypeVar


_RESERVED = re.compile(
    r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)",
    re.IGNORECASE,
)
_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}

T = TypeVar("T")


def sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a cross-platform filename."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "", name)
    name = re.sub(r"\s+", " ", name)
    name = name.strip().rstrip(".")
    name = name[:100].rstrip(" .")
    if not name:
        return "untitled"
    if _RESERVED.match(name):
        name = f"_{name}"[:100].rstrip(" .")
        if not name:
            return "untitled"
    return name


def safe_output_path(base_dir: Path, filename: str) -> Path:
    """Return a Path using a sanitized filename inside base_dir."""
    return base_dir / sanitize_filename(filename)


def dedupe_ordered(items: list[T]) -> list[T]:
    """Return items in first-seen order with duplicates removed."""
    return list(dict.fromkeys(items))


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


__all__ = [
    "sanitize_filename",
    "safe_output_path",
    "dedupe_ordered",
    "parse_bool_setting",
    "is_valid_bool_setting",
]
