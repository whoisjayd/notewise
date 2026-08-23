"""Tests for chapter-directory output manifest validation."""

import json

import pytest

from notewise._constants import OUTPUT_METADATA_CHAPTER_FILES_KEY
from notewise.pipeline._execution import _chapter_directory_has_complete_manifest


class _StubPipeline:
    """Minimal pipeline exposing a metadata reader backed by real files."""

    def __init__(self, chapter_dir, metadata):
        self._chapter_dir = chapter_dir
        self._metadata = metadata

    def _read_output_target_metadata(self, target, video_id):
        """Mirror core's reader: parse .notewise-output.json from the target."""
        if not target.is_dir():
            return {}
        metadata_path = target / ".notewise-output.json"
        if not metadata_path.exists():
            return {}
        try:
            parsed = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}


def _write_metadata(chapter_dir, metadata):
    """Write a metadata file into the chapter directory."""
    (chapter_dir / ".notewise-output.json").write_text(
        json.dumps(metadata, sort_keys=True),
        encoding="utf-8",
    )


class TestChapterManifestValidation:
    """Test _chapter_directory_has_complete_manifest outcomes."""

    def test_complete_manifest_returns_true(self, tmp_path):
        """A manifest whose every listed file exists on disk validates."""
        chapter_dir = tmp_path / "My Video"
        chapter_dir.mkdir()
        (chapter_dir / "My Video.md").write_text("notes", encoding="utf-8")
        (chapter_dir / "My Video_transcript.txt").write_text(
            "transcript", encoding="utf-8"
        )
        _write_metadata(
            chapter_dir,
            {
                "video_id": "dQw4w9WgXcQ",
                OUTPUT_METADATA_CHAPTER_FILES_KEY: [
                    "My Video.md",
                    "My Video_transcript.txt",
                ],
            },
        )
        assert _chapter_directory_has_complete_manifest(
            _StubPipeline(chapter_dir, None), chapter_dir, "dQw4w9WgXcQ"
        )

    def test_missing_listed_file_returns_false(self, tmp_path):
        """A listed filename absent from the directory fails validation."""
        chapter_dir = tmp_path / "My Video"
        chapter_dir.mkdir()
        (chapter_dir / "My Video.md").write_text("notes", encoding="utf-8")
        _write_metadata(
            chapter_dir,
            {OUTPUT_METADATA_CHAPTER_FILES_KEY: ["My Video.md", "missing.md"]},
        )
        assert not _chapter_directory_has_complete_manifest(
            _StubPipeline(chapter_dir, None), chapter_dir, "vid"
        )

    def test_corrupt_json_metadata_returns_false(self, tmp_path):
        """Truncated JSON metadata yields no dict and fails validation."""
        chapter_dir = tmp_path / "My Video"
        chapter_dir.mkdir()
        (chapter_dir / "My Video.md").write_text("notes", encoding="utf-8")
        (chapter_dir / ".notewise-output.json").write_text(
            '{"chapter_files": ["My Video.md"', encoding="utf-8"
        )
        assert not _chapter_directory_has_complete_manifest(
            _StubPipeline(chapter_dir, None), chapter_dir, "vid"
        )

    def test_non_dict_metadata_returns_false(self, tmp_path):
        """Metadata that parses to a non-dict payload fails validation."""
        chapter_dir = tmp_path / "My Video"
        chapter_dir.mkdir()
        (chapter_dir / ".notewise-output.json").write_text(
            '["My Video.md"]', encoding="utf-8"
        )
        assert not _chapter_directory_has_complete_manifest(
            _StubPipeline(chapter_dir, None), chapter_dir, "vid"
        )

    @pytest.mark.parametrize("entry", [123, None, ["nested.md"]])
    def test_non_string_entries_return_false(self, tmp_path, entry):
        """Non-string chapter_files entries fail validation."""
        chapter_dir = tmp_path / "My Video"
        chapter_dir.mkdir()
        (chapter_dir / "My Video.md").write_text("notes", encoding="utf-8")
        _write_metadata(
            chapter_dir,
            {OUTPUT_METADATA_CHAPTER_FILES_KEY: ["My Video.md", entry]},
        )
        assert not _chapter_directory_has_complete_manifest(
            _StubPipeline(chapter_dir, None), chapter_dir, "vid"
        )

    def test_empty_filename_entry_returns_false(self, tmp_path):
        """An empty-string chapter_files entry fails validation."""
        chapter_dir = tmp_path / "My Video"
        chapter_dir.mkdir()
        (chapter_dir / "My Video.md").write_text("notes", encoding="utf-8")
        _write_metadata(
            chapter_dir,
            {OUTPUT_METADATA_CHAPTER_FILES_KEY: ["My Video.md", ""]},
        )
        assert not _chapter_directory_has_complete_manifest(
            _StubPipeline(chapter_dir, None), chapter_dir, "vid"
        )

    @pytest.mark.parametrize(
        "entry", ["../escape.txt", "..\\escape.txt", "C:\\evil.txt", "/etc/passwd"]
    )
    def test_traversal_shaped_entries_return_false(self, tmp_path, entry):
        """Path separators and parent references in entries fail validation."""
        chapter_dir = tmp_path / "My Video"
        chapter_dir.mkdir()
        (chapter_dir / "My Video.md").write_text("notes", encoding="utf-8")
        _write_metadata(
            chapter_dir,
            {OUTPUT_METADATA_CHAPTER_FILES_KEY: ["My Video.md", entry]},
        )
        assert not _chapter_directory_has_complete_manifest(
            _StubPipeline(chapter_dir, None), chapter_dir, "vid"
        )

    def test_empty_chapter_files_list_returns_false(self, tmp_path):
        """An empty chapter_files list fails validation."""
        chapter_dir = tmp_path / "My Video"
        chapter_dir.mkdir()
        _write_metadata(chapter_dir, {OUTPUT_METADATA_CHAPTER_FILES_KEY: []})
        assert not _chapter_directory_has_complete_manifest(
            _StubPipeline(chapter_dir, None), chapter_dir, "vid"
        )

    def test_missing_chapter_files_key_returns_false(self, tmp_path):
        """Metadata without a chapter_files key fails validation."""
        chapter_dir = tmp_path / "My Video"
        chapter_dir.mkdir()
        (chapter_dir / "My Video.md").write_text("notes", encoding="utf-8")
        _write_metadata(chapter_dir, {"video_id": "vid"})
        assert not _chapter_directory_has_complete_manifest(
            _StubPipeline(chapter_dir, None), chapter_dir, "vid"
        )

    def test_missing_metadata_file_returns_false(self, tmp_path):
        """A chapter directory without any metadata file fails validation."""
        chapter_dir = tmp_path / "My Video"
        chapter_dir.mkdir()
        (chapter_dir / "My Video.md").write_text("notes", encoding="utf-8")
        assert not _chapter_directory_has_complete_manifest(
            _StubPipeline(chapter_dir, None), chapter_dir, "vid"
        )

    def test_pipeline_without_metadata_reader_returns_false(self, tmp_path):
        """A pipeline lacking a callable metadata reader fails validation."""
        chapter_dir = tmp_path / "My Video"
        chapter_dir.mkdir()

        class _NoReader:
            _read_output_target_metadata = None

        assert not _chapter_directory_has_complete_manifest(
            _NoReader(), chapter_dir, "vid"
        )
