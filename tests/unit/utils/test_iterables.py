"""Tests for iterable utility helpers."""

from notewise.utils import dedupe_ordered


def test_dedupe_ordered_removes_duplicates():
    assert dedupe_ordered(["a", "b", "a", "c"]) == ["a", "b", "c"]


def test_dedupe_ordered_preserves_first_seen_order():
    assert dedupe_ordered(["c", "a", "b", "a", "c"]) == ["c", "a", "b"]


def test_dedupe_ordered_empty_list():
    assert dedupe_ordered([]) == []


def test_dedupe_ordered_no_duplicates_unchanged():
    assert dedupe_ordered(["x", "y", "z"]) == ["x", "y", "z"]


def test_dedupe_ordered_all_same():
    assert dedupe_ordered(["a", "a", "a"]) == ["a"]
