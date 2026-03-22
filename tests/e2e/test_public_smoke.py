"""Opt-in end-to-end smoke tests for live public YouTube content."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


_RUN_E2E = os.environ.get("RUN_E2E") == "1"
_GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not _RUN_E2E or not _GEMINI_KEY,
        reason="Set RUN_E2E=1 and GEMINI_API_KEY to run live smoke tests.",
    ),
]

_VIDEO_URL = "https://www.youtube.com/watch?v=8uiZC0l4Ajw"
_PLAYLIST_URL = (
    "https://www.youtube.com/playlist?list=PL7s8EzBd1s8op6WSiYxr3U9E_T1DoIkJG"
)
_DEFAULT_MODEL = "gemini/gemini-2.5-flash"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _REPO_ROOT / "src"


def _prepare_live_state_dir() -> Path:
    state_dir = Path(os.environ["YT_STUDY_HOME"])
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "config.env").write_text(
        f"DEFAULT_MODEL={_DEFAULT_MODEL}\n",
        encoding="utf-8",
    )
    return state_dir


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{_SRC_ROOT}{os.pathsep}{pythonpath}" if pythonpath else str(_SRC_ROOT)
    )
    return subprocess.run(
        [sys.executable, "-m", "yt_study", *args],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )


@pytest.mark.parametrize(
    ("url", "output_dir_name", "minimum_markdown_files"),
    [
        (_VIDEO_URL, "video", 1),
        (_PLAYLIST_URL, "playlist", 2),
    ],
)
def test_public_smoke(url, output_dir_name, minimum_markdown_files, tmp_path):
    """Live public YouTube inputs should still process end-to-end."""
    _prepare_live_state_dir()
    output_dir = tmp_path / output_dir_name

    result = _run_cli("process", url, "--no-ui", "--output", str(output_dir))

    assert result.returncode == 0, (
        f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
    )

    markdown_files = list(output_dir.rglob("*.md"))
    assert len(markdown_files) >= minimum_markdown_files
    assert "Done:" in result.stdout or "Batch Completed" in result.stdout
