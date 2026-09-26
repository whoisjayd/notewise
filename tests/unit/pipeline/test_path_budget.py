"""Tests for path-length budgeting in output naming."""

from notewise._constants import (
    CHAPTER_MARKDOWN_FILE_EXTENSION,
    MAX_FILENAME_LENGTH,
    MAX_PATH_LENGTH,
)
from notewise.utils import sanitize_filename, truncate_for_path


LONG_TITLE = "V" * MAX_FILENAME_LENGTH
LONG_CHAPTER = "C" * MAX_FILENAME_LENGTH


def test_short_name_is_returned_unchanged(tmp_path):
    assert truncate_for_path(tmp_path, "Notes.md") == "Notes.md"


def test_truncation_keeps_the_assembled_path_within_budget(tmp_path):
    """The real chapter leaf must fit under a realistic long output directory."""
    output_dir = tmp_path / ("segment" * 4)
    output_target = output_dir / sanitize_filename(LONG_TITLE)
    leaf = f"01_{sanitize_filename(LONG_CHAPTER)}{CHAPTER_MARKDOWN_FILE_EXTENSION}"

    result = truncate_for_path(output_target, leaf)

    assert len(str(output_target / result)) <= MAX_PATH_LENGTH
    assert result.startswith("01_")
    assert result.endswith(CHAPTER_MARKDOWN_FILE_EXTENSION)


def test_truncation_never_returns_a_trailing_dot_or_space(tmp_path):
    parent = tmp_path / ("d" * 200)

    result = truncate_for_path(parent, "x" * MAX_FILENAME_LENGTH)

    assert result
    assert result == result.rstrip(" .")


def test_parent_already_over_the_cap_returns_the_name_unchanged(tmp_path):
    """A hopeless parent must not yield a mangled stub name."""
    parent = tmp_path / ("d" * 120) / ("t" * MAX_FILENAME_LENGTH)
    leaf = f"01_{sanitize_filename(LONG_CHAPTER)}{CHAPTER_MARKDOWN_FILE_EXTENSION}"

    assert truncate_for_path(parent, leaf) == leaf


def test_chapter_files_stay_distinct_after_truncation(tmp_path):
    """Truncation must not collapse two chapters onto one file name."""
    output_target = tmp_path / ("segment" * 5) / sanitize_filename(LONG_TITLE)
    first = truncate_for_path(
        output_target,
        f"01_{sanitize_filename('A' * 90)}{CHAPTER_MARKDOWN_FILE_EXTENSION}",
    )
    second = truncate_for_path(
        output_target,
        f"02_{sanitize_filename('B' * 90)}{CHAPTER_MARKDOWN_FILE_EXTENSION}",
    )

    assert first != second
