"""Small utilities for working with sequences."""

from __future__ import annotations

from typing import TypeVar


T = TypeVar("T")


def dedupe_ordered(items: list[T]) -> list[T]:
    """Return items in first-seen order with duplicates removed."""
    return list(dict.fromkeys(items))
