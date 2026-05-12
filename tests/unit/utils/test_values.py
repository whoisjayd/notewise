"""Tests for numeric utility helpers."""

from notewise.utils import (
    coerce_int,
    coerce_non_negative_float,
    coerce_non_negative_int,
    mask_secret,
    parse_config_env_lines,
    strip_wrapped_quotes,
)


def test_coerce_int_handles_extractor_scalars() -> None:
    assert coerce_int(None, default=4) == 4
    assert coerce_int(True) == 1
    assert coerce_int(2.8) == 2
    assert coerce_int("7") == 7
    assert coerce_int(b"8") == 8
    assert coerce_int("bad", default=3) == 3


def test_coerce_non_negative_int_handles_usage_values() -> None:
    assert coerce_non_negative_int(True) == 1
    assert coerce_non_negative_int(-4) == 0
    assert coerce_non_negative_int(2.8) == 2
    assert coerce_non_negative_int("7") == 7
    assert coerce_non_negative_int("bad") == 0
    assert coerce_non_negative_int(object()) == 0


def test_coerce_non_negative_float_handles_usage_values() -> None:
    assert coerce_non_negative_float(True) == 1.0
    assert coerce_non_negative_float(-4.2) == 0.0
    assert coerce_non_negative_float(2) == 2.0
    assert coerce_non_negative_float("7.5") == 7.5
    assert coerce_non_negative_float("bad") == 0.0
    assert coerce_non_negative_float(object()) == 0.0


def test_mask_secret_preserves_display_variants() -> None:
    assert mask_secret(None) == "(not set)"
    assert mask_secret("short") == "***"
    assert mask_secret("abcdefghijklmnop") == "abcdef...mnop"
    assert mask_secret("abcdefghijklmnop", suffix=" (set)") == "abcdef...mnop (set)"


def test_strip_wrapped_quotes_handles_config_value_variants() -> None:
    assert strip_wrapped_quotes('"quoted"') == "quoted"
    assert strip_wrapped_quotes("'quoted'") == "quoted"
    assert strip_wrapped_quotes('r"D:\\tmp\\out"') == "D:\\tmp\\out"
    assert strip_wrapped_quotes("plain") == "plain"


def test_parse_config_env_lines_ignores_comments_and_strips_values() -> None:
    assert parse_config_env_lines(
        [
            "# comment",
            "",
            "DEFAULT_MODEL = 'gemini/test'",
            "NO_EQUALS",
            'OUTPUT_DIR = r"D:\\notes"',
        ]
    ) == {
        "DEFAULT_MODEL": "gemini/test",
        "OUTPUT_DIR": "D:\\notes",
    }
