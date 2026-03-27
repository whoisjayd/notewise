"""Tests for CLI source-resolution helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from notewise.cli._source_resolution import (
    batch_failure_label,
    failure_rows_for_result,
    ordered_batch_failures_from_error,
    prepare_source,
)
from notewise.cli._types import ResolvedSource, _BatchVideoJob
from notewise.errors import PlaylistError, UserVisibleCliError


@pytest.mark.asyncio
async def test_prepare_source_returns_single_video_resolution(tmp_path) -> None:
    """Direct video URLs should resolve without playlist expansion."""
    context = SimpleNamespace(
        parse_youtube_url=lambda _url: SimpleNamespace(
            url_type="video", video_id="abc"
        ),
        selected_output=tmp_path,
    )

    resolved = await prepare_source(context, "https://youtube.com/watch?v=abc")

    assert resolved.video_ids == ["abc"]
    assert resolved.playlist_name == "Single Video"
    assert resolved.output_dir == tmp_path


@pytest.mark.asyncio
async def test_prepare_source_rejects_missing_video_id(tmp_path) -> None:
    """Video inputs without a usable video id should raise a user-visible error."""
    context = SimpleNamespace(
        parse_youtube_url=lambda _url: SimpleNamespace(url_type="video", video_id=None),
        selected_output=tmp_path,
    )

    with pytest.raises(UserVisibleCliError) as exc:
        await prepare_source(context, "invalid")

    assert exc.value.rows == [("URL", "Could not extract a video ID from this URL.")]


@pytest.mark.asyncio
async def test_prepare_source_wraps_playlist_errors(tmp_path) -> None:
    """Playlist extraction failures should normalize to a playlist error panel."""

    async def _extract_playlist_videos(*_args, **_kwargs):
        raise PlaylistError("private")

    context = SimpleNamespace(
        parse_youtube_url=lambda _url: SimpleNamespace(
            url_type="playlist",
            playlist_id="pl123",
            video_id=None,
        ),
        extract_playlist_videos=_extract_playlist_videos,
        selected_cookie_file=None,
        selected_output=tmp_path,
    )

    with pytest.raises(UserVisibleCliError, match="Playlist Error"):
        await prepare_source(context, "https://youtube.com/playlist?list=pl123")


def test_failure_row_helpers_cover_default_and_playlist_labels() -> None:
    """Failure-row helpers should format fallback and playlist labels consistently."""
    prepared = ResolvedSource(
        source_url="url",
        label="Playlist Title",
        playlist_name="Playlist Title",
        video_ids=["a"],
        output_dir=Path("out"),
    )
    job = _BatchVideoJob(
        sort_key=(0, 0),
        source_label="Playlist Title",
        video_id="abc",
        output_dir=Path("out"),
        is_playlist_video=True,
    )

    assert failure_rows_for_result(prepared, {}) == [
        (
            "Playlist Title",
            (
                "We couldn't process this entry. Check the current session log "
                "for details."
            ),
        )
    ]
    failures = ordered_batch_failures_from_error(
        2,
        "https://youtube.com/watch?v=abc",
        UserVisibleCliError("Input Error", [("URL", "bad"), ("Video", "worse")]),
    )
    assert failures[0].item == "https://youtube.com/watch?v=abc"
    assert failures[1].item == "Video"
    assert batch_failure_label(job, "Video One") == "Playlist Title / Video One"
    job.is_playlist_video = False
    assert batch_failure_label(job, "Video One") == "Video One"
