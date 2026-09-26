"""Tests for the artifact cache check, including colliding video titles."""

from pathlib import Path

from notewise._constants import DEFAULT_NOTES_OUTPUT_FORMAT
from notewise.pipeline._execution import _cached_video_has_requested_artifacts
from notewise.pipeline._helpers import suffix_output_target


class _StubPipeline:
    """Minimal pipeline for the cache check (flat, single-format output)."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_formats = (DEFAULT_NOTES_OUTPUT_FORMAT,)
        self.chapter_directory_output = False
        self.export_transcript_format = None
        self.quiz = False

    def _is_reusable_directory_output(self, target, video_id):
        return False

    def _read_output_target_metadata(self, target, video_id):
        return {}


def test_cache_check_accepts_this_video_suffixed_artifact(tmp_path):
    """A video whose artifact was suffixed away from a colliding title is cached."""
    pipeline = _StubPipeline(tmp_path)
    suffixed = suffix_output_target(tmp_path / "Same Title.md", "bid")
    suffixed.write_text("notes for b", encoding="utf-8")

    assert _cached_video_has_requested_artifacts(pipeline, "bid", "Same Title") is True


def test_cache_check_is_false_when_no_artifact_exists(tmp_path):
    """Nothing on disk for this title means the video must be regenerated."""
    pipeline = _StubPipeline(tmp_path)

    assert _cached_video_has_requested_artifacts(pipeline, "bid", "Same Title") is False


def test_cache_check_prefers_own_suffixed_artifact_over_a_collision(tmp_path):
    """Both files present: the video is cached via its own suffixed artifact."""
    pipeline = _StubPipeline(tmp_path)
    (tmp_path / "Same Title.md").write_text("notes for a", encoding="utf-8")
    suffixed = suffix_output_target(tmp_path / "Same Title.md", "bid")
    suffixed.write_text("notes for b", encoding="utf-8")

    assert _cached_video_has_requested_artifacts(pipeline, "bid", "Same Title") is True
