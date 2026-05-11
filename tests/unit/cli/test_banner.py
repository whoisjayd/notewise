"""Tests for CLI banner helpers."""

from __future__ import annotations

import builtins

from rich.console import Console

from notewise.cli import _banner


def test_get_version_falls_back_to_dev_when_import_fails(monkeypatch) -> None:
    """Missing package metadata should fall back to the dev banner version."""
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "notewise" and "__version__" in fromlist:
            raise ImportError("missing version")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert _banner._get_version() == "dev"


def test_print_banner_renders_dev_version(monkeypatch) -> None:
    """The banner should render a readable fallback version string."""
    console = Console(record=True, width=120)
    monkeypatch.setattr(_banner, "_get_version", lambda: "dev")

    _banner.print_banner(console)

    output = console.export_text()
    assert "███" in output
    assert "AI-powered YouTube study notes" in output
    assert "vdev" in output
    assert "github.com/whoisjayd/notewise" in output


def test_banner_text_groups_ascii_art_lines() -> None:
    """The banner should render as one Rich text block, not delayed line prints."""
    banner = _banner._banner_text(use_unicode=True)

    assert banner.plain.count("\n") == len(_banner._UNICODE_BANNER_LINES) - 1
    assert all(line in banner.plain for line in _banner._UNICODE_BANNER_LINES)
    assert "███████╗███████╗" in banner.plain


def test_banner_panel_falls_back_to_ascii_for_non_utf_console(monkeypatch) -> None:
    """Legacy encodings should avoid decorative Unicode wordmark output."""
    console = Console(record=True, width=120)
    monkeypatch.setattr(_banner, "_supports_unicode_output", lambda _console: False)

    console.print(_banner._banner_panel(console))
    output = console.export_text()

    assert "NOTEWISE" in output
    assert "██" not in output


def test_print_help_banner_delegates_to_main_banner(monkeypatch) -> None:
    """Help output should reuse the primary banner renderer."""
    console = Console(record=True, width=120)
    called: list[Console] = []

    monkeypatch.setattr(_banner, "print_banner", lambda target: called.append(target))

    _banner.print_help_banner(console)

    assert called == [console]
