"""Tests for render_notes_with_warning."""

from __future__ import annotations

from unittest.mock import patch

from notewise._constants import PDF_RENDER_FALLBACK_WARNING
from notewise.pipeline._output_rendering import render_notes_with_warning


def test_render_notes_with_warning_returns_no_warning_on_success(tmp_path):
    targets = {"md": tmp_path / "notes.md"}

    rendered, warning = render_notes_with_warning(
        "# Title\n\nBody", "Title", targets, "English"
    )

    assert rendered["md"] == tmp_path / "notes.md"
    assert rendered["md"].exists()
    assert warning is None


def test_render_notes_with_warning_surfaces_pdf_fallback(tmp_path):
    targets = {"pdf": tmp_path / "notes.pdf"}

    def _broken_pdf_renderer(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("fpdf2 choked on this HTML")

    with patch.dict(
        "notewise.pipeline._documents._DOCUMENT_RENDERERS",
        {"pdf": _broken_pdf_renderer},
    ):
        rendered, warning = render_notes_with_warning(
            "# Title\n\nBody", "Title", targets, "English"
        )

    assert rendered["pdf"] == (tmp_path / "notes.pdf").with_suffix(".md")
    assert rendered["pdf"].exists()
    assert warning == PDF_RENDER_FALLBACK_WARNING


def test_render_notes_with_warning_no_warning_when_pdf_not_requested(tmp_path):
    targets = {"html": tmp_path / "notes.html"}

    rendered, warning = render_notes_with_warning(
        "# Title\n\nBody", "Title", targets, "English"
    )

    assert rendered["html"].exists()
    assert warning is None
