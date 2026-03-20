"""Tests for shared config parsing helpers."""

import pytest

from yt_study.utils import is_valid_bool_setting, parse_bool_setting


@pytest.mark.parametrize("value", ["1", " true ", "YES", "On"])
def test_parse_bool_setting_truthy_values(value):
    """Truthy strings should parse to True regardless of casing or spacing."""
    assert parse_bool_setting(value, default=False) is True


@pytest.mark.parametrize("value", ["0", " false ", "NO", "Off"])
def test_parse_bool_setting_falsy_values(value):
    """Falsy strings should parse to False regardless of casing or spacing."""
    assert parse_bool_setting(value, default=True) is False


def test_parse_bool_setting_falls_back_to_default_for_unknown_or_missing_values():
    """Unknown values and None should preserve the provided default."""
    assert parse_bool_setting(None, default=True) is True
    assert parse_bool_setting("maybe", default=False) is False
    assert parse_bool_setting("  ", default=True) is True


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, True),
        ("true", True),
        (" FALSE ", True),
        ("sometimes", False),
        ("", False),
    ],
)
def test_is_valid_bool_setting_recognizes_supported_values(value, expected):
    """Validation should accept recognized bool strings or unset values only."""
    assert is_valid_bool_setting(value) is expected
