"""Document rendering helpers for notes output formats."""

from __future__ import annotations

import re
from collections.abc import Callable
from html import escape
from io import BytesIO
from pathlib import Path

from notewise._constants import (
    CHAPTER_BUNDLE_SEPARATOR,
    DEFAULT_NOTES_OUTPUT_FORMAT,
    DEFAULT_RENDERED_HTML_STYLES,
    DEFAULT_RENDERED_PDF_STYLES,
    DOCX_BODY_FONT_NAME,
    DOCX_BODY_FONT_SIZE_PT,
    DOCX_BODY_SPACE_AFTER_PT,
    DOCX_HEADING_FONT_NAME,
    DOCX_HEADING_ONE_FONT_SIZE_PT,
    DOCX_HEADING_SPACE_AFTER_PT,
    DOCX_HEADING_SPACE_BEFORE_PT,
    DOCX_HEADING_THREE_FONT_SIZE_PT,
    DOCX_HEADING_TWO_FONT_SIZE_PT,
    DOCX_SECTION_MARGIN_INCHES,
    DOCX_TITLE_FONT_SIZE_PT,
    MARKDOWN_RENDER_EXTENSIONS,
    NOTES_OUTPUT_EXTENSIONS,
    OUTPUT_FORMAT_SEPARATOR,
    SUPPORTED_NOTES_OUTPUT_FORMATS,
)
from notewise.errors import ValidationError


DocumentRenderer = Callable[[str, str, Path], None]
_LIST_ITEM_RE = re.compile(r"^(?P<indent>\s*)(?:[-*+]\s+|\d+\.\s+)")
_CODE_BLOCK_RE = re.compile(
    r"<pre><code(?:\s+class=\"[^\"]*\")?>(?P<code>.*?)</code></pre>", re.DOTALL
)


def normalize_output_format(output_format: str | None) -> str:
    """Normalize and validate the requested notes output format."""
    candidate = (output_format or DEFAULT_NOTES_OUTPUT_FORMAT).strip().lower()
    if candidate not in SUPPORTED_NOTES_OUTPUT_FORMATS:
        supported = ", ".join(SUPPORTED_NOTES_OUTPUT_FORMATS)
        raise ValidationError(
            f"Unsupported output format '{output_format}'. Choose one of: {supported}."
        )
    return candidate


def normalize_output_formats(
    output_format_value: str | list[str] | tuple[str, ...] | None,
) -> list[str]:
    """Parse, validate, and deduplicate one or more requested formats."""
    if output_format_value is None:
        raw_values = [DEFAULT_NOTES_OUTPUT_FORMAT]
    elif isinstance(output_format_value, str):
        raw_values = output_format_value.split(OUTPUT_FORMAT_SEPARATOR)
    else:
        raw_values = list(output_format_value)

    normalized_formats: list[str] = []
    for raw_value in raw_values:
        candidate = normalize_output_format(raw_value)
        if candidate not in normalized_formats:
            normalized_formats.append(candidate)
    return normalized_formats


def get_output_extension(output_format: str | None) -> str:
    """Return the canonical file extension for the selected format."""
    return NOTES_OUTPUT_EXTENSIONS[normalize_output_format(output_format)]


def build_chapter_bundle(title: str, chapter_notes: list[str]) -> str:
    """Bundle generated chapter notes into one Markdown document."""
    cleaned_notes = [notes.strip() for notes in chapter_notes if notes.strip()]
    if not cleaned_notes:
        return f"# {title}\n"
    return f"# {title}\n\n{CHAPTER_BUNDLE_SEPARATOR.join(cleaned_notes)}\n"


def render_notes_document(
    markdown_text: str,
    title: str,
    output_path: Path,
    output_format: str | None,
) -> Path:
    """Render a Markdown study document to the requested file format."""
    normalized_format = normalize_output_format(output_format)
    renderer = _DOCUMENT_RENDERERS[normalized_format]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    renderer(markdown_text, title, output_path)
    return output_path


def render_notes_documents(
    markdown_text: str,
    title: str,
    output_targets: dict[str, Path],
) -> dict[str, Path]:
    """Render a Markdown study document to multiple target formats."""
    for output_format, output_path in output_targets.items():
        render_notes_document(markdown_text, title, output_path, output_format)
    return dict(output_targets)


def _normalize_markdown_blocks(markdown_text: str) -> str:
    normalized_lines: list[str] = []
    previous_line = ""

    for line in markdown_text.splitlines():
        stripped = line.strip()
        is_list_item = bool(_LIST_ITEM_RE.match(line))
        previous_is_list_item = bool(_LIST_ITEM_RE.match(previous_line))
        previous_is_content = bool(previous_line.strip())
        previous_is_heading = previous_line.lstrip().startswith("#")

        if (
            is_list_item
            and not previous_is_list_item
            and previous_is_content
            and not previous_is_heading
            and line == stripped
            and normalized_lines
            and normalized_lines[-1] != ""
        ):
            normalized_lines.append("")

        normalized_lines.append(line)
        previous_line = line

    return "\n".join(normalized_lines)


def _markdown_to_html(markdown_text: str) -> str:
    import markdown as markdown_lib

    rendered_html = markdown_lib.markdown(
        _normalize_markdown_blocks(markdown_text),
        extensions=list(MARKDOWN_RENDER_EXTENSIONS),
    )
    return _normalize_rendered_html(rendered_html)


def _normalize_rendered_html(body_html: str) -> str:
    def _replace_code_block(match: re.Match[str]) -> str:
        code_html = match.group("code")
        return f'<pre class="code-block">{code_html}</pre>'

    return _CODE_BLOCK_RE.sub(_replace_code_block, body_html)


def _build_html_document(
    title: str,
    body_html: str,
    styles: str = DEFAULT_RENDERED_HTML_STYLES,
) -> str:
    escaped_title = escape(title)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8" />\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1" />\n'
        f"  <title>{escaped_title}</title>\n"
        "  <style>\n"
        f"{styles}\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        '  <main class="document">\n'
        f"{body_html}\n"
        "  </main>\n"
        "</body>\n"
        "</html>\n"
    )


def _write_markdown(markdown_text: str, _title: str, output_path: Path) -> None:
    output_path.write_text(markdown_text, encoding="utf-8")


def _write_html(markdown_text: str, title: str, output_path: Path) -> None:
    html_document = _build_html_document(title, _markdown_to_html(markdown_text))
    output_path.write_text(html_document, encoding="utf-8")


def _write_pdf(markdown_text: str, title: str, output_path: Path) -> None:
    from xhtml2pdf import pisa

    html_document = _build_html_document(
        title,
        _markdown_to_html(markdown_text),
        DEFAULT_RENDERED_PDF_STYLES,
    )
    with output_path.open("wb") as output_file:
        result = pisa.CreatePDF(html_document, dest=output_file, encoding="utf-8")
    if result.err:
        raise ValidationError("Could not render PDF output for this document.")


def _write_docx(markdown_text: str, title: str, output_path: Path) -> None:
    from docx import Document
    from docx.shared import Inches, Pt
    from html2docx import html2docx

    document_buffer = html2docx(_markdown_to_html(markdown_text), title=title)
    document_buffer.seek(0)
    document = Document(document_buffer)

    for section in document.sections:
        section.top_margin = Inches(DOCX_SECTION_MARGIN_INCHES)
        section.bottom_margin = Inches(DOCX_SECTION_MARGIN_INCHES)
        section.left_margin = Inches(DOCX_SECTION_MARGIN_INCHES)
        section.right_margin = Inches(DOCX_SECTION_MARGIN_INCHES)

    normal_style = document.styles["Normal"]
    normal_style.font.name = DOCX_BODY_FONT_NAME
    normal_style.font.size = Pt(DOCX_BODY_FONT_SIZE_PT)

    for style_name, font_size in (
        ("Title", DOCX_TITLE_FONT_SIZE_PT),
        ("Heading 1", DOCX_HEADING_ONE_FONT_SIZE_PT),
        ("Heading 2", DOCX_HEADING_TWO_FONT_SIZE_PT),
        ("Heading 3", DOCX_HEADING_THREE_FONT_SIZE_PT),
    ):
        style = document.styles[style_name]
        style.font.name = DOCX_HEADING_FONT_NAME
        style.font.size = Pt(font_size)
        style.paragraph_format.space_before = Pt(DOCX_HEADING_SPACE_BEFORE_PT)
        style.paragraph_format.space_after = Pt(DOCX_HEADING_SPACE_AFTER_PT)

    for paragraph in document.paragraphs:
        if paragraph.text.strip():
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(DOCX_BODY_SPACE_AFTER_PT)
            paragraph.paragraph_format.line_spacing = 1.1
        else:
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)

    styled_buffer = BytesIO()
    document.save(styled_buffer)
    output_path.write_bytes(styled_buffer.getvalue())


_DOCUMENT_RENDERERS: dict[str, DocumentRenderer] = {
    "md": _write_markdown,
    "html": _write_html,
    "pdf": _write_pdf,
    "docx": _write_docx,
}
