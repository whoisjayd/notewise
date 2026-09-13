"""Escaping for untrusted content interpolated into prompt delimiter tags."""

from __future__ import annotations

from html import escape as _html_escape


def escape_untrusted_content(text: str) -> str:
    """Neutralize angle brackets in untrusted text before prompt interpolation.

    Prompts wrap untrusted transcript/chapter-title text in pseudo-XML tags
    (e.g. ``<transcript>...</transcript>``) and instruct the model to treat
    everything inside as data, not instructions. Without escaping, a
    transcript segment containing the literal substring ``</transcript>``
    would prematurely close that boundary, letting anything after it in the
    transcript be read as prompt-author text instead of untrusted content.
    """
    return _html_escape(text, quote=False)
