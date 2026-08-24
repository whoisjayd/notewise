"""Tests for filename sanitization utilities."""

import pytest

from notewise._constants import MAX_FILENAME_LENGTH, SANITIZED_FILENAME_FALLBACK
from notewise.utils import safe_output_path, sanitize_filename


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
        ("", SANITIZED_FILENAME_FALLBACK),
        ("   ", SANITIZED_FILENAME_FALLBACK),
        ("...", SANITIZED_FILENAME_FALLBACK),
        (".", SANITIZED_FILENAME_FALLBACK),
        ("..", SANITIZED_FILENAME_FALLBACK),
        ("filename.", "filename"),
        ("filename...", "filename"),
        (".env", ".env"),  # leading dot preserved
        (".gitignore", ".gitignore"),
        ("filename   ", "filename"),
        ("Title  With  Spaces", "Title With Spaces"),
        ("a" * (MAX_FILENAME_LENGTH * 2), "a" * MAX_FILENAME_LENGTH),
        ("foo\x00bar", "foobar"),
        ("foo\x1fbar", "foobar"),
        ("foo\x7fbar", "foobar"),
        ("\u202eevil", "evil"),  # RTL override stripped (display spoofing)
        ("a\u200bb", "ab"),  # zero-width space stripped
        ("\u2066x\u2069", "x"),  # bidi isolation chars stripped
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
    raw = "a" * (MAX_FILENAME_LENGTH - 1) + " " + "b" * 10
    result = sanitize_filename(raw)
    assert len(result) <= MAX_FILENAME_LENGTH
    assert not result.endswith(" ")


def test_sanitize_reserved_at_max_chars():
    """Reserved names near the filename limit stay within bounds after prefixing."""
    long_nul = "NUL." + "a" * (MAX_FILENAME_LENGTH - len("NUL."))
    result = sanitize_filename(long_nul)
    assert len(result) <= MAX_FILENAME_LENGTH
    assert result.startswith("_")


def test_sanitize_reserved_prefix_happens_before_truncation():
    """Reserved-name protection should survive truncation at the boundary."""
    raw = "NUL." + ("a" * (MAX_FILENAME_LENGTH + 20))
    result = sanitize_filename(raw)
    assert len(result) <= MAX_FILENAME_LENGTH
    assert result.startswith("_")


def test_safe_output_path(tmp_path):
    result = safe_output_path(tmp_path, "Video: Title")
    assert result == tmp_path / "Video Title"
    assert result.parent == tmp_path
