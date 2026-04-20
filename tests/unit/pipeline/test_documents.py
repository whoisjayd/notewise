"""Unit tests for document rendering helpers."""

from __future__ import annotations

import pytest

from notewise.errors import ValidationError
from notewise.pipeline._documents import (
    _markdown_to_html,
    _normalize_rendered_html,
    build_chapter_bundle,
    get_output_extension,
    normalize_output_format,
    normalize_output_formats,
)


@pytest.mark.parametrize(
    ("value", "expected_extension"),
    [
        ("md", ".md"),
        ("HTML", ".html"),
        ("pdf", ".pdf"),
        ("docx", ".docx"),
    ],
)
def test_supported_output_formats_normalize_and_map_extensions(
    value: str,
    expected_extension: str,
):
    assert get_output_extension(value) == expected_extension
    assert normalize_output_format(value) == expected_extension.removeprefix(".")


def test_unsupported_output_format_raises_validation_error() -> None:
    with pytest.raises(ValidationError, match="Unsupported output format"):
        normalize_output_format("epub")


def test_normalize_output_formats_parses_csv_and_deduplicates() -> None:
    assert normalize_output_formats("md, html, pdf, html") == ["md", "html", "pdf"]


def test_markdown_to_html_normalizes_top_level_lists() -> None:
    html = _markdown_to_html(
        "## Section\nParagraph introducing the list:\n* item one\n* item two"
    )

    assert "<ul>" in html
    assert "<li>item one</li>" in html


def test_normalize_rendered_html_promotes_code_blocks() -> None:
    html = _normalize_rendered_html("<pre><code>print('hi')</code></pre>")

    assert '<pre class="code-block">' in html
    assert "<code>" not in html


def test_build_chapter_bundle_wraps_notes_under_video_title() -> None:
    bundled = build_chapter_bundle(
        "Course Title",
        ["# Intro\n\nFirst part", "# Deep Dive\n\nSecond part"],
    )

    assert bundled.startswith("# Course Title")
    assert "# Intro" in bundled
    assert "# Deep Dive" in bundled
    assert "---" in bundled
