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
_VIDEO_WITH_CHAPTERS = _VIDEO_URL
_PLAYLIST_URL = (
    "https://www.youtube.com/playlist?list=PL7s8EzBd1s8op6WSiYxr3U9E_T1DoIkJG"
)
_DEFAULT_MODEL = "gemini/gemini-2.5-flash"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _REPO_ROOT / "src"


def _prepare_live_state_dir() -> Path:
    state_dir = Path(os.environ["NOTEWISE_HOME"])
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
        [sys.executable, "-m", "notewise", *args],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )


@pytest.mark.parametrize(
    (
        "url",
        "output_dir_name",
        "minimum_markdown_files",
        "extra_args",
        "expect_chapter_directory_output",
    ),
    [
        (_VIDEO_URL, "video", 1, [], False),
        (
            _VIDEO_WITH_CHAPTERS,
            "video-chapters",
            1,
            ["--chapter-directory-output"],
            True,
        ),
        (_PLAYLIST_URL, "playlist", 2, [], False),
    ],
)
def test_public_smoke(
    url,
    output_dir_name,
    minimum_markdown_files,
    extra_args,
    expect_chapter_directory_output,
    tmp_path,
):
    """Live public YouTube inputs should still process end-to-end."""
    _prepare_live_state_dir()
    output_dir = tmp_path / output_dir_name

    result = _run_cli(
        "process", url, "--no-ui", "--output", str(output_dir), *extra_args
    )

    assert result.returncode == 0, (
        f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
    )

    markdown_files = list(output_dir.rglob("*.md"))
    visible_markdown_files = [
        file
        for file in markdown_files
        if ".working" not in file.relative_to(output_dir).parts
    ]
    assert len(visible_markdown_files) >= minimum_markdown_files

    if expect_chapter_directory_output:
        assert not (output_dir / ".working").exists()
        chapter_dirs = [
            path
            for path in output_dir.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        ]
        assert chapter_dirs, "expected a per-video directory for chapter output"

        chapter_markdown_files = sorted(chapter_dirs[0].glob("*.md"))
        assert len(chapter_markdown_files) >= 2
        assert all(file.name[:2].isdigit() for file in chapter_markdown_files)
        assert not any(
            file.parent.name == ".working" for file in chapter_markdown_files
        )

    assert "Done:" in result.stdout or "Batch Completed" in result.stdout
