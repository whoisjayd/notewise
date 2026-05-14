"""Unit tests for document rendering helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

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


if TYPE_CHECKING:
    from pathlib import Path


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


def test_markdown_to_html_escapes_raw_html() -> None:
    html = _markdown_to_html("# Notes\n\n<script>alert('x')</script>")

    assert "<script>" not in html
    assert "&lt;script&gt;alert('x')&lt;/script&gt;" in html


def test_markdown_to_html_preserves_blockquotes() -> None:
    html = _markdown_to_html("> Important idea")

    assert "<blockquote>" in html
    assert "Important idea" in html


def test_markdown_to_html_escapes_raw_html_inside_blockquotes() -> None:
    html = _markdown_to_html("> <script>alert(1)</script>")

    assert "<blockquote>" in html
    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_markdown_to_html_preserves_autolinks() -> None:
    html = _markdown_to_html("See <https://example.com>")

    assert '<a href="https://example.com">https://example.com</a>' in html


@pytest.mark.parametrize(
    "markdown_text",
    [
        "[unsafe](javascript:alert(1))",
        "[unsafe](JaVaScRiPt:alert(1))",
        "[unsafe](data:text/html,<script>alert(1)</script>)",
        "[unsafe](\x01javascript:alert(1))",
    ],
)
def test_markdown_to_html_removes_unsafe_link_hrefs(markdown_text: str) -> None:
    html = _markdown_to_html(markdown_text)

    assert "unsafe" in html
    assert "href=" not in html
    assert "javascript:" not in html.casefold()
    assert "data:" not in html.casefold()


@pytest.mark.parametrize(
    ("markdown_text", "expected_href"),
    [
        ("[safe](http://example.com)", 'href="http://example.com"'),
        ("[safe](https://example.com/path)", 'href="https://example.com/path"'),
        ("[safe](  HtTpS://Example.com  )", 'href="HtTpS://Example.com"'),
        ("[safe](mailto:learner@example.com)", 'href="mailto:learner@example.com"'),
        ("[safe](#chapter-1)", 'href="#chapter-1"'),
    ],
)
def test_markdown_to_html_preserves_safe_link_hrefs(
    markdown_text: str,
    expected_href: str,
) -> None:
    html = _markdown_to_html(markdown_text)

    assert expected_href in html


def test_markdown_to_html_preserves_fenced_code_angle_brackets() -> None:
    html = _markdown_to_html("```html\n<div>hi</div>\n```")

    assert "&lt;div&gt;hi&lt;/div&gt;" in html
    assert "&amp;lt;div&amp;gt;" not in html


def test_markdown_to_html_does_not_treat_single_backtick_as_fence() -> None:
    html = _markdown_to_html("`html\n<script>x</script>\n`")

    assert '<pre class="code-block">' not in html
    assert "<script>" not in html
    assert "&amp;lt;script&amp;gt;x&amp;lt;/script&amp;gt;" in html


def test_markdown_to_html_closes_fence_only_with_matching_marker() -> None:
    html = _markdown_to_html("````html\n~~~\n<div>hi</div>\n````\n<script>x</script>")

    assert "&lt;div&gt;hi&lt;/div&gt;" in html
    assert "<script>" not in html
    assert "&lt;script&gt;x&lt;/script&gt;" in html


def test_markdown_to_html_preserves_indented_code_angle_brackets() -> None:
    html = _markdown_to_html("    <div>hi</div>")

    assert "&lt;div&gt;hi&lt;/div&gt;" in html
    assert "&amp;lt;div&amp;gt;" not in html


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


def test_render_html_document_normalizes_underscore_locale_tag(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "notes.html"

    render_notes_document(
        "# Titulo",
        "Portuguese Notes",
        output_path,
        "html",
        target_language="pt_BR",
    )

    html = output_path.read_text(encoding="utf-8")
    assert '<html lang="pt-BR">' in html


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
