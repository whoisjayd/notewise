"""Tests for the release-check helpers."""

from __future__ import annotations

from notewise import updater


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None

    def read(self) -> bytes:
        return self._payload


def test_check_for_updates_reports_available_release(monkeypatch) -> None:
    payload = b"""
    {
            "tag_name": "v1.1.1",
      "html_url": "https://example.com/release"
    }
    """

    def fake_urlopen(*_args: object, **_kwargs: object) -> _FakeResponse:
        return _FakeResponse(payload)

    monkeypatch.setattr(updater, "urlopen", fake_urlopen)

    status = updater.check_for_updates()

    assert status.available is True
    assert status.latest_version == "1.1.1"
    assert status.update_commands
    assert "notewise" in status.update_commands[0]


def test_binary_install_uses_windows_installer_command(monkeypatch) -> None:
    monkeypatch.setattr(updater.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updater.os, "name", "nt", raising=False)

    commands = updater._get_update_commands()

    assert commands == (
        "irm https://github.com/whoisjayd/notewise/"
        "releases/latest/download/install.ps1 | iex",
    )


def test_python_install_includes_package_manager_commands(monkeypatch) -> None:
    monkeypatch.setattr(updater.sys, "frozen", False, raising=False)
    monkeypatch.setattr(updater.os, "name", "posix", raising=False)

    commands = updater._get_update_commands()

    assert commands[:3] == (
        "uv tool upgrade notewise",
        "pipx upgrade notewise",
        "pip install --upgrade notewise",
    )
    assert commands[-1].endswith("install.sh | sh")
