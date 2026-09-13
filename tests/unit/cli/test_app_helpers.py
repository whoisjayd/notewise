"""Unit tests for CLI helper behavior."""

from __future__ import annotations

from typer.testing import CliRunner

from notewise.cli.app import app, looks_like_batch_file_path


runner = CliRunner()


def test_looks_like_batch_file_path_ignores_schemeless_urls() -> None:
    """Schemeless video hosts should stay on the URL-validation path."""
    assert looks_like_batch_file_path("youtube.com/watch?v=dQw4w9WgXcQ") is False
    assert looks_like_batch_file_path("vimeo.com/123456") is False


def test_looks_like_batch_file_path_keeps_real_file_signals() -> None:
    """Real local path indicators should still be treated as batch files."""
    assert looks_like_batch_file_path("./urls.txt") is True
    assert looks_like_batch_file_path("path/to/list.txt") is True
    assert looks_like_batch_file_path("C:/temp/urls.txt") is True


def test_short_help_alias_works_at_every_command_level() -> None:
    """`-h` should behave like `--help` at the root, group, and leaf levels."""
    for args in (["-h"], ["cache", "-h"], ["config", "get", "-h"]):
        result = runner.invoke(app, args)
        assert result.exit_code == 0
        assert "Show this message and exit" in result.output
