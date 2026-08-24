"""Unit tests for the `notewise transcript` command."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from typer.testing import CliRunner

from notewise.cli import app as cli_app
from notewise.domain.youtube import TranscriptSegment, VideoTranscript
from notewise.errors import IPBlockError, TranscriptUnavailableError


runner = CliRunner()

VIDEO_URL = "https://youtu.be/dQw4w9WgXcQ"
VIDEO_ID = "dQw4w9WgXcQ"
VIDEO_TITLE = "My Video"


@pytest.fixture
def fake_transcript() -> VideoTranscript:
    return VideoTranscript(
        video_id=VIDEO_ID,
        segments=[TranscriptSegment(text="Hello world", start=0.0, duration=1.5)],
        language="English",
        language_code="en",
        is_generated=False,
    )


@pytest.fixture(autouse=True)
def patched_config(mocker: Any, tmp_path: Any) -> SimpleNamespace:
    """Redirect config lookups to an isolated output directory."""
    settings = SimpleNamespace(
        default_output_dir=tmp_path / "default-out",
        default_languages=["en"],
        youtube_cookie_file=None,
    )
    mocker.patch.object(cli_app, "_get_config", return_value=settings)
    return settings


def _patch_video_layer(
    mocker: Any,
    transcript: VideoTranscript,
    *,
    details: dict[str, Any] | None = None,
    url_type: str = "video",
) -> tuple[Any, Any]:
    if details is None:
        details = {"id": VIDEO_ID, "title": VIDEO_TITLE}
    parse = mocker.patch.object(
        cli_app,
        "parse_youtube_url",
        return_value=SimpleNamespace(
            url_type=url_type,
            video_id=VIDEO_ID if url_type == "video" else None,
            playlist_id=None if url_type == "video" else "PLabc1234567890",
        ),
    )
    mocker.patch.object(
        cli_app,
        "get_video_details",
        AsyncMock(return_value=details),
    )
    mocker.patch(
        "notewise.youtube.metadata.video_metadata_from_details",
        return_value=SimpleNamespace(title=VIDEO_TITLE),
    )
    fetch = mocker.patch.object(
        cli_app,
        "fetch_transcript",
        AsyncMock(return_value=transcript),
    )
    return parse, fetch


def test_transcript_writes_txt_file_by_default(mocker, tmp_path, fake_transcript):
    """Default txt format writes <title>-transcript.txt and prints the path."""
    _patch_video_layer(mocker, fake_transcript)

    result = runner.invoke(
        cli_app.app, ["transcript", VIDEO_URL, "--output", str(tmp_path)]
    )

    assert result.exit_code == 0
    written = tmp_path / f"{VIDEO_TITLE}-transcript.txt"
    assert written.exists()
    assert written.read_text(encoding="utf-8") == "Hello world"
    assert str(written) in result.output.replace("\n", "")
    cli_app.get_video_details.assert_awaited_once_with(VIDEO_ID, None)
    cli_app.fetch_transcript.assert_awaited_once_with(
        VIDEO_ID,
        ["en"],
        cookie_file=None,
        video_data={"id": VIDEO_ID, "title": VIDEO_TITLE},
    )


def test_transcript_writes_json_file(mocker, tmp_path, fake_transcript):
    """JSON format serializes metadata plus timed segments."""
    _patch_video_layer(mocker, fake_transcript)

    result = runner.invoke(
        cli_app.app,
        ["transcript", VIDEO_URL, "--format", "json", "--output", str(tmp_path)],
    )

    assert result.exit_code == 0
    written = tmp_path / f"{VIDEO_TITLE}-transcript.json"
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["video_id"] == VIDEO_ID
    assert payload["language"] == "English"
    assert payload["segments"][0]["text"] == "Hello world"


def test_transcript_unavailable_exits_1_with_message(mocker, tmp_path, fake_transcript):
    """A missing transcript renders a friendly failure with exit code 1."""
    _patch_video_layer(mocker, fake_transcript)
    cli_app.fetch_transcript.side_effect = TranscriptUnavailableError("no track")

    result = runner.invoke(
        cli_app.app, ["transcript", VIDEO_URL, "--output", str(tmp_path)]
    )

    assert result.exit_code == 1
    assert "couldn't get a usable transcript" in result.output


def test_transcript_rejects_playlist_with_process_pointer(
    mocker, tmp_path, fake_transcript
):
    """Playlist inputs point users at `process --export-transcript`."""
    _, fetch = _patch_video_layer(mocker, fake_transcript, url_type="playlist")

    result = runner.invoke(
        cli_app.app, ["transcript", VIDEO_URL, "--output", str(tmp_path)]
    )

    assert result.exit_code == 1
    assert "process --export-transcript" in result.output
    cli_app.get_video_details.assert_not_awaited()
    fetch.assert_not_awaited()


def test_transcript_rejects_invalid_format_before_network(
    mocker, tmp_path, fake_transcript
):
    """Unsupported formats fail before URL parsing or any network call."""
    parse, fetch = _patch_video_layer(mocker, fake_transcript)

    result = runner.invoke(
        cli_app.app,
        [
            "transcript",
            VIDEO_URL,
            "--format",
            "pdf",
            "--output",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 1
    assert "txt, json" in result.output
    parse.assert_not_called()
    cli_app.get_video_details.assert_not_awaited()
    fetch.assert_not_awaited()
    assert list(tmp_path.iterdir()) == []


def test_transcript_creates_missing_output_dir(mocker, tmp_path, fake_transcript):
    """A missing --output directory is created before writing."""
    _patch_video_layer(mocker, fake_transcript)
    target = tmp_path / "exports" / "nested"

    result = runner.invoke(
        cli_app.app, ["transcript", VIDEO_URL, "--output", str(target)]
    )

    assert result.exit_code == 0
    assert (target / f"{VIDEO_TITLE}-transcript.txt").exists()


def test_transcript_collision_appends_video_id(mocker, tmp_path, fake_transcript):
    """Filename collisions gain the video ID before the extension."""
    _patch_video_layer(mocker, fake_transcript)
    existing = tmp_path / f"{VIDEO_TITLE}-transcript.txt"
    existing.write_text("original", encoding="utf-8")
    id_collision = tmp_path / f"{VIDEO_TITLE}-transcript-{VIDEO_ID}.txt"
    id_collision.write_text("previous run", encoding="utf-8")

    result = runner.invoke(
        cli_app.app, ["transcript", VIDEO_URL, "--output", str(tmp_path)]
    )

    assert result.exit_code == 0
    assert existing.read_text(encoding="utf-8") == "original"
    assert id_collision.read_text(encoding="utf-8") == "previous run"
    numbered = tmp_path / f"{VIDEO_TITLE}-transcript-{VIDEO_ID}-2.txt"
    assert numbered.read_text(encoding="utf-8") == "Hello world"


def test_transcript_ip_block_renders_error_panel(mocker, tmp_path, fake_transcript):
    """An IP block renders a Transcript Error panel via format_user_error."""
    _patch_video_layer(mocker, fake_transcript)
    error = IPBlockError("requests blocked")
    cli_app.fetch_transcript.side_effect = error
    format_error = mocker.patch.object(
        cli_app,
        "format_user_error",
        return_value="Network is blocked by YouTube.",
    )

    result = runner.invoke(
        cli_app.app, ["transcript", VIDEO_URL, "--output", str(tmp_path)]
    )

    assert result.exit_code == 1
    assert "Transcript Error" in result.output
    assert "Network is blocked by YouTube." in result.output
    format_error.assert_called_once_with(error)


def test_transcript_batch_file_input_gets_playlist_pointer(
    mocker, tmp_path, fake_transcript
):
    """Batch-file paths are rejected with the playlist pointer message."""
    parse, fetch = _patch_video_layer(mocker, fake_transcript)

    result = runner.invoke(
        cli_app.app, ["transcript", "./urls.txt", "--output", str(tmp_path)]
    )

    assert result.exit_code == 1
    assert "process --export-transcript" in result.output
    parse.assert_not_called()
    fetch.assert_not_awaited()
