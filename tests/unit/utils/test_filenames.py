"""Tests for filename sanitization utilities."""

import pytest

from yt_study.utils import safe_output_path, sanitize_filename


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Normal Title", "Normal Title"),
        ("Title: With Colon", "Title With Colon"),
        ('foo<>:"/\\|?*bar', "foobar"),
        ("CON", "_CON"),
        ("PRN", "_PRN"),
        ("NUL", "_NUL"),
        ("NUL.txt", "_NUL.txt"),
        ("com1.log", "_com1.log"),
        ("COM0", "COM0"),  # COM0 is NOT reserved
        ("LPT0", "LPT0"),  # LPT0 is NOT reserved
        ("", "untitled"),
        ("   ", "untitled"),
        ("...", "untitled"),
        (".", "untitled"),
        ("..", "untitled"),
        ("filename.", "filename"),
        ("filename...", "filename"),
        (".env", ".env"),  # leading dot preserved
        (".gitignore", ".gitignore"),
        ("filename   ", "filename"),
        ("Title  With  Spaces", "Title With Spaces"),
        ("a" * 200, "a" * 100),  # truncated to 100
        ("foo\x00bar", "foobar"),
        ("foo\x1fbar", "foobar"),
        ("foo\x7fbar", "foobar"),
    ],
)
def test_sanitize_filename(name, expected):
    assert sanitize_filename(name) == expected


def test_sanitize_windows_reserved_names():
    for reserved in ("CON", "PRN", "AUX", "NUL"):
        result = sanitize_filename(reserved)
        assert result == f"_{reserved}"
        result_lower = sanitize_filename(reserved.lower())
        assert result_lower == f"_{reserved.lower()}"


def test_sanitize_com_lpt_range():
    for i in range(1, 10):
        assert sanitize_filename(f"COM{i}") == f"_COM{i}"
        assert sanitize_filename(f"LPT{i}") == f"_LPT{i}"


def test_sanitize_truncation_no_trailing_space():
    """Truncation must not leave a trailing space."""
    raw = "a" * 99 + " " + "b" * 10
    result = sanitize_filename(raw)
    assert len(result) <= 100
    assert not result.endswith(" ")


def test_sanitize_reserved_at_100_chars():
    """Reserved names near the 100-char limit stay within 100 chars after prefixing."""
    long_nul = "NUL." + "a" * 96
    result = sanitize_filename(long_nul)
    assert len(result) <= 100
    assert result.startswith("_")


def test_safe_output_path(tmp_path):
    result = safe_output_path(tmp_path, "Video: Title")
    assert result == tmp_path / "Video Title"
    assert result.parent == tmp_path
