"""Tests for the release-check helpers."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from notewise import updater
from notewise._constants import UPDATE_METADATA_PARSE_ERROR
from notewise.cli import app as cli_app
from notewise.errors import UpdateError


runner = CliRunner()


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def test_check_for_updates_reports_available_release(mocker) -> None:
    payload = b"""
    {
        "tag_name": "v1.4.2",
        "html_url": "https://example.com/release"
    }
    """

    def fake_urlopen(*_args: object, **_kwargs: object) -> _FakeResponse:
        return _FakeResponse(payload)

    mocker.patch.object(updater, "urlopen", side_effect=fake_urlopen)

    status = updater.check_for_updates()

    assert status.available is True
    assert status.latest_version == "1.4.2"
    assert status.install_source == "Python Package"
    assert status.update_commands
    assert "notewise" in status.update_commands[0]


def test_request_json_wraps_malformed_json(mocker) -> None:
    def fake_urlopen(*_args: object, **_kwargs: object) -> _FakeResponse:
        return _FakeResponse(b"not-json")

    mocker.patch.object(updater, "urlopen", side_effect=fake_urlopen)

    with pytest.raises(UpdateError, match=UPDATE_METADATA_PARSE_ERROR):
        updater._request_json("https://example.com/latest")


def test_binary_install_uses_windows_installer_command(monkeypatch) -> None:
    monkeypatch.setattr(updater.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updater.os, "name", "nt", raising=False)

    commands = updater._get_update_commands()

    assert commands == ("irm https://notewise.click/install | iex",)


def test_python_install_includes_package_manager_commands(monkeypatch) -> None:
    monkeypatch.setattr(updater.sys, "frozen", False, raising=False)
    monkeypatch.setattr(updater.os, "name", "posix", raising=False)

    commands = updater._get_update_commands()

    assert commands[:3] == (
        "uv tool upgrade notewise",
        "pipx upgrade notewise",
        "python -m pip install --upgrade notewise",
    )
    assert not any(command.endswith("install.sh | sh") for command in commands)


def test_binary_install_reports_standalone_source(monkeypatch) -> None:
    monkeypatch.setattr(updater.sys, "frozen", True, raising=False)

    assert updater._get_install_source() == "Standalone Binary"


def test_python_install_reports_package_source(monkeypatch) -> None:
    monkeypatch.setattr(updater.sys, "frozen", False, raising=False)

    assert updater._get_install_source() == "Python Package"


def test_update_command_prints_detected_source_and_matching_command(mocker) -> None:
    mocker.patch.object(
        cli_app,
        "check_for_updates",
        return_value=updater.UpdateStatus(
            current_version="1.4.1",
            latest_version="1.4.1",
            available=True,
            install_source="Standalone Binary",
            release_url="https://example.com/release",
            update_commands=("curl -fsSL https://notewise.click/install | sh",),
        ),
    )

    result = runner.invoke(cli_app.app, ["update"])

    assert result.exit_code == 0
    assert "Update available" in result.output
    assert "Install source: Standalone Binary" in result.output
    assert "curl -fsSL https://notewise.click/install | sh" in result.output
