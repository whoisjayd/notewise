"""Shared output rendering helpers for pipeline execution."""

from __future__ import annotations

from pathlib import Path

from notewise._constants import PDF_UNSUPPORTED_UNICODE_ERROR
from notewise.pipeline._documents import render_notes_documents


def render_notes_with_warning(
    notes: str,
    title: str,
    rendered_output_targets: dict[str, Path],
    target_language: str,
) -> tuple[dict[str, Path], str | None]:
    rendered_output_targets = render_notes_documents(
        notes,
        title,
        rendered_output_targets,
        target_language=target_language,
    )
    if rendered_output_targets.get("pdf") is not None and (
        rendered_output_targets["pdf"].suffix.lower() == ".md"
    ):
        return rendered_output_targets, PDF_UNSUPPORTED_UNICODE_ERROR.format(
            target_language=target_language
        )
    return rendered_output_targets, None
