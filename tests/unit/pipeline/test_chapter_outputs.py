"""Tests for chapter-output generation helpers."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from notewise.pipeline._chapter_outputs import (
    ChapterGenerationPlan,
    _atomic_write_text,
    persist_completed_chapter_files,
)


def test_persist_completed_chapter_files_writes_only_completed_chapters(tmp_path):
    """Only chapters present in `completed_chapter_notes` get written.

    This is the partial-failure recovery path: a chapter still missing (it
    failed or never ran) must be left alone so it's regenerated next time,
    while a finished sibling is saved so a rerun's existing
    chapter_file.exists() check can skip it.
    """
    intro_file = tmp_path / "01_intro.md"
    body_file = tmp_path / "02_body.md"
    plan = ChapterGenerationPlan(
        chapters_to_generate={"Intro": "intro text", "Body": "body text"},
        chapter_targets=[
            ("Intro", 0, intro_file),
            ("Body", 120, body_file),
        ],
        chapter_output_files={"Intro": intro_file, "Body": body_file},
    )
    pipeline = SimpleNamespace(timestamps=False)

    persist_completed_chapter_files(pipeline, plan, {"Intro": "# Intro notes"})

    assert intro_file.read_text(encoding="utf-8") == "# Intro notes"
    assert not body_file.exists()


def test_persist_completed_chapter_files_prefixes_timestamps_when_enabled(tmp_path):
    """Matches the timestamp-prefix behavior of the full bundle-write path."""
    intro_file = tmp_path / "01_intro.md"
    plan = ChapterGenerationPlan(
        chapters_to_generate={"Intro": "intro text"},
        chapter_targets=[("Intro", 90, intro_file)],
        chapter_output_files={"Intro": intro_file},
    )
    pipeline = SimpleNamespace(timestamps=True)

    persist_completed_chapter_files(pipeline, plan, {"Intro": "# Intro\nBody"})

    written = intro_file.read_text(encoding="utf-8")
    assert "01:30" in written or "0:01:30" in written


def test_persist_completed_chapter_files_skips_chapters_with_no_file_target():
    """A None chapter_file (e.g. bundled mode with no rendered target) is a no-op."""
    plan = ChapterGenerationPlan(
        chapters_to_generate={"Intro": "intro text"},
        chapter_targets=[("Intro", 0, None)],
        chapter_output_files={},
    )
    pipeline = SimpleNamespace(timestamps=False)

    # Must not raise despite chapter_file being None.
    persist_completed_chapter_files(pipeline, plan, {"Intro": "# Intro notes"})


def test_atomic_write_text_writes_full_content(tmp_path):
    """Normal case: the target file exists with the exact written content."""
    target = tmp_path / "chapter.md"

    _atomic_write_text(target, "# Chapter\nBody text")

    assert target.read_text(encoding="utf-8") == "# Chapter\nBody text"


def test_atomic_write_text_leaves_no_partial_file_on_mid_write_failure(
    tmp_path, monkeypatch
):
    """A failure mid-write must never leave a truncated file at the target path.

    Simulates a crash after the temp file is opened but before it is
    replaced into place: the original write path is only ever a fresh temp
    file, so a mid-write failure must leave the target path untouched
    (absent here, since it never existed) and must not leak the temp file.
    """
    target = tmp_path / "chapter.md"

    original_fdopen = os.fdopen

    def _boom_fdopen(*args, **kwargs):
        handle = original_fdopen(*args, **kwargs)
        try:
            handle.write("this is a partial write that should never land")
            handle.flush()
        finally:
            handle.close()
        raise OSError("simulated crash mid-write")

    monkeypatch.setattr(os, "fdopen", _boom_fdopen)

    with pytest.raises(OSError, match="simulated crash mid-write"):
        _atomic_write_text(target, "# Full notes")

    assert not target.exists()
    leftover_temp_files = list(tmp_path.glob(".chapter.md.*.tmp"))
    assert leftover_temp_files == []


def test_atomic_write_text_does_not_truncate_existing_file_on_failure(
    tmp_path, monkeypatch
):
    """An existing complete file must survive a failed rewrite attempt untouched."""
    target = tmp_path / "chapter.md"
    target.write_text("# Original complete notes", encoding="utf-8")

    def _boom_fdopen(*args, **kwargs):
        raise OSError("simulated crash mid-write")

    monkeypatch.setattr(os, "fdopen", _boom_fdopen)

    with pytest.raises(OSError, match="simulated crash mid-write"):
        _atomic_write_text(target, "# New notes that never finish writing")

    assert target.read_text(encoding="utf-8") == "# Original complete notes"
