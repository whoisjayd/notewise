"""Tests for the package entrypoint."""

from __future__ import annotations

from unittest.mock import MagicMock

from yt_study import __main__ as main_mod


def test_is_help_invocation() -> None:
    assert main_mod._is_help_invocation(["--help"]) is True
    assert main_mod._is_help_invocation(["setup", "-h"]) is True
    assert main_mod._is_help_invocation(["version"]) is False


def test_main_prints_banner_for_help(monkeypatch) -> None:
    console = MagicMock()
    app = MagicMock()
    banner = MagicMock()

    monkeypatch.setattr(main_mod.sys, "argv", ["yt-study", "--help"])
    monkeypatch.setattr("yt_study.cli.app._get_console", lambda: console)
    monkeypatch.setattr("yt_study.cli.app.app", app)
    monkeypatch.setattr("yt_study.cli._banner.print_help_banner", banner)

    main_mod.main()

    banner.assert_called_once_with(console)
    console.print.assert_called_once_with()
    app.assert_called_once_with()


def test_main_skips_banner_for_non_help(monkeypatch) -> None:
    console = MagicMock()
    app = MagicMock()
    banner = MagicMock()

    monkeypatch.setattr(main_mod.sys, "argv", ["yt-study", "version"])
    monkeypatch.setattr("yt_study.cli.app._get_console", lambda: console)
    monkeypatch.setattr("yt_study.cli.app.app", app)
    monkeypatch.setattr("yt_study.cli._banner.print_help_banner", banner)

    main_mod.main()

    banner.assert_not_called()
    console.print.assert_not_called()
    app.assert_called_once_with()
