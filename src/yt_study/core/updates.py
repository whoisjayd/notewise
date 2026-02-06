"""Update checker for yt-study."""

import sys

import httpx
from packaging import version

from .. import __version__


PYPI_URL = "https://pypi.org/pypi/yt-study/json"
TIMEOUT = 2.0


def get_latest_version() -> str | None:
    """Fetch the latest version from PyPI."""
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(PYPI_URL)
            response.raise_for_status()
            data = response.json()
            version_str = data.get("info", {}).get("version")
            return str(version_str) if version_str else None
    except Exception:
        return None


def is_update_available() -> tuple[bool, str | None]:
    """Check if an update is available."""
    latest = get_latest_version()
    if not latest:
        return False, None

    try:
        current_v = version.parse(__version__)
        latest_v = version.parse(latest)
        return latest_v > current_v, latest
    except Exception:
        return False, None


def is_frozen() -> bool:
    """Check if the application is running as a frozen binary (e.g., PyInstaller)."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
