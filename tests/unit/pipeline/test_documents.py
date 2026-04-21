"""Unit tests for document rendering helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from notewise.errors import ValidationError
from notewise.pipeline._documents import (
    _build_html_document,
    _markdown_to_html,
    _normalize_pdf_markdown,
    _normalize_rendered_html,
    build_chapter_bundle,
    get_output_extension,
    normalize_output_format,
    normalize_output_formats,
    render_notes_document,
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
    assert "<code>print('hi')</code>" in html


def test_markdown_to_html_normalizes_indented_list_items() -> None:
    html = _markdown_to_html(
        "## Section\n"
        "Paragraph introducing the list:\n"
        "  * nested item one\n"
        "  * nested item two"
    )

    assert "<ul>" in html
    assert "nested item one" in html


def test_normalize_pdf_markdown_replaces_smart_punctuation() -> None:
    normalized = _normalize_pdf_markdown('"quote" - dash - ellipsis...')

    assert normalized == '"quote" - dash - ellipsis...'


def test_normalize_pdf_markdown_downgrades_unicode_punctuation() -> None:
    normalized = _normalize_pdf_markdown("“quote” — dash …")

    assert normalized == '"quote" - dash ...'


def test_normalize_pdf_markdown_rejects_non_latin_scripts() -> None:
    with pytest.raises(ValidationError, match="PDF output currently supports"):
        _normalize_pdf_markdown("हिंदी नोट्स", target_language="Hindi")


def test_build_html_document_sets_language_attribute() -> None:
    html = _build_html_document("Title", "<p>Body</p>", lang="hi")

    assert '<html lang="hi">' in html


def test_render_html_document_uses_target_language_lang_attribute(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "notes.html"

    render_notes_document(
        "# शीर्षक\n\nविवरण",
        "Hindi Notes",
        output_path,
        "html",
        target_language="Hindi",
    )

    html = output_path.read_text(encoding="utf-8")
    assert '<html lang="hi">' in html


def test_render_pdf_document_falls_back_to_markdown_for_non_latin_text(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "notes.pdf"

    rendered_path = render_notes_document(
        "# शीर्षक\n\nविवरण",
        "Hindi Notes",
        output_path,
        "pdf",
        target_language="Hindi",
    )

    assert rendered_path == output_path.with_suffix(".md")
    assert rendered_path.exists()
    assert rendered_path.read_text(encoding="utf-8").startswith("# शीर्षक")


def test_build_chapter_bundle_wraps_notes_under_video_title() -> None:
    bundled = build_chapter_bundle(
        "Course Title",
        ["# Intro\n\nFirst part", "# Deep Dive\n\nSecond part"],
    )

    assert bundled.startswith("# Course Title")
    assert "# Intro" in bundled
    assert "# Deep Dive" in bundled
    assert "---" in bundled
