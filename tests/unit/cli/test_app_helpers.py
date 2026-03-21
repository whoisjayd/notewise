"""Unit tests for CLI helper behavior."""

from __future__ import annotations

from yt_study.cli.app import looks_like_batch_file_path


def test_looks_like_batch_file_path_ignores_schemeless_urls() -> None:
    """Schemeless video hosts should stay on the URL-validation path."""
    assert looks_like_batch_file_path("youtube.com/watch?v=dQw4w9WgXcQ") is False
    assert looks_like_batch_file_path("vimeo.com/123456") is False


def test_looks_like_batch_file_path_keeps_real_file_signals() -> None:
    """Real local path indicators should still be treated as batch files."""
    assert looks_like_batch_file_path("./urls.txt") is True
    assert looks_like_batch_file_path("path/to/list.txt") is True
    assert looks_like_batch_file_path("C:/temp/urls.txt") is True
