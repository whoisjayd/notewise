"""Release-check helpers for the `notewise update` command."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from notewise import __version__
from notewise._constants import (
    LATEST_RELEASE_API_URL,
    RELEASES_PAGE_URL,
    UPDATE_COMMAND_BINARY_UNIX,
    UPDATE_COMMAND_BINARY_WINDOWS,
    UPDATE_COMMAND_PIP,
    UPDATE_COMMAND_PIPX,
    UPDATE_COMMAND_UV,
    UPDATE_HTTP_TIMEOUT_SECONDS,
    UPDATE_INSTALL_SOURCE_BINARY,
    UPDATE_INSTALL_SOURCE_PYTHON,
    UPDATE_METADATA_PARSE_ERROR,
    UPDATER_USER_AGENT,
)
from notewise.errors import UpdateError


@dataclass(frozen=True)
class ReleaseInfo:
    """Release metadata used by the CLI update check."""

    tag_name: str
    version: str
    html_url: str


@dataclass(frozen=True)
class UpdateStatus:
    """Result metadata returned to the CLI layer."""

    current_version: str
    latest_version: str
    available: bool
    install_source: str
    release_url: str
    update_commands: tuple[str, ...]


def _version_key(raw_version: str) -> tuple[int, ...]:
    version = raw_version.strip().lstrip("v")
    parts = version.split(".")
    if len(parts) < 3:
        raise UpdateError(f"Unsupported release version format: {raw_version}")

    normalized: list[int] = []
    for part in parts[:3]:
        digits = "".join(ch for ch in part if ch.isdigit())
        if not digits:
            raise UpdateError(f"Unsupported release version format: {raw_version}")
        normalized.append(int(digits))
    return tuple(normalized)


def _request_json(url: str) -> dict[str, object]:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{UPDATER_USER_AGENT}/{__version__}",
        },
    )
    try:
        with urlopen(request, timeout=UPDATE_HTTP_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise UpdateError(
            f"GitHub returned HTTP {error.code} while checking for updates."
        ) from error
    except URLError as error:
        raise UpdateError(
            "Could not reach GitHub Releases while checking for updates."
        ) from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise UpdateError(UPDATE_METADATA_PARSE_ERROR) from error

    if not isinstance(payload, dict):
        raise UpdateError("Latest release metadata was not returned as an object.")
    return payload


def get_latest_release() -> ReleaseInfo:
    """Fetch the latest GitHub release metadata."""
    payload = _request_json(LATEST_RELEASE_API_URL)
    tag_name = str(payload.get("tag_name", "")).strip()
    if not tag_name:
        raise UpdateError("Latest release metadata is missing a tag name.")

    html_url = str(payload.get("html_url", RELEASES_PAGE_URL)).strip()
    return ReleaseInfo(
        tag_name=tag_name,
        version=tag_name.lstrip("v"),
        html_url=html_url or RELEASES_PAGE_URL,
    )


def _is_standalone_binary() -> bool:
    """Return whether the app is running from a bundled standalone binary."""
    return bool(getattr(sys, "frozen", False))


def _get_install_source() -> str:
    """Return a user-facing install source label."""
    if _is_standalone_binary():
        return UPDATE_INSTALL_SOURCE_BINARY
    return UPDATE_INSTALL_SOURCE_PYTHON


def _get_update_commands() -> tuple[str, ...]:
    """Return the recommended upgrade commands for the current install source."""
    if _is_standalone_binary():
        if os.name == "nt":
            return (UPDATE_COMMAND_BINARY_WINDOWS,)
        return (UPDATE_COMMAND_BINARY_UNIX,)

    return (UPDATE_COMMAND_UV, UPDATE_COMMAND_PIPX, UPDATE_COMMAND_PIP)


def check_for_updates() -> UpdateStatus:
    """Return the currently installed and latest available versions."""
    latest_release = get_latest_release()
    update_available = _version_key(latest_release.version) > _version_key(__version__)
    return UpdateStatus(
        current_version=__version__,
        latest_version=latest_release.version,
        available=update_available,
        install_source=_get_install_source(),
        release_url=latest_release.html_url,
        update_commands=_get_update_commands(),
    )
