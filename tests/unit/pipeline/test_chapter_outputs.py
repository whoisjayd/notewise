"""Tests for chapter-output generation helpers."""

from __future__ import annotations

from types import SimpleNamespace

from notewise.pipeline._chapter_outputs import (
    ChapterGenerationPlan,
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
