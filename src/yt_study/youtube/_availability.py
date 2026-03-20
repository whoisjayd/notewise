"""Shared availability checks for parsed YouTube metadata payloads."""

from __future__ import annotations

from yt_study.errors import VideoUnavailableError


def raise_for_video_availability(data: dict[str, object]) -> None:
    """Raise a user-facing error for restricted video availability states."""
    availability = str(data.get("availability") or "").lower()
    if availability == "private":
        raise VideoUnavailableError(
            "Private YouTube videos are not supported. "
            "Make the video unlisted or public to process it.",
            reason="private",
        )
    if availability in {"login_required", "unavailable"}:
        raise VideoUnavailableError(
            "Sign-in-only YouTube videos are not supported. "
            "Use a public or unlisted video to process it.",
            reason="login_required",
        )
    if availability == "age_restricted":
        raise VideoUnavailableError(
            (
                "Age-restricted YouTube videos are not supported. "
                "Use a public or unlisted video without sign-in requirements "
                "to process it."
            ),
            reason="age_restricted",
        )


def raise_for_playlist_availability(data: dict[str, object]) -> None:
    """Raise a user-facing error for restricted playlist availability states."""
    availability = str(data.get("availability") or "").lower()
    if availability == "private":
        raise VideoUnavailableError(
            "Private YouTube playlists are not supported. "
            "Make the playlist unlisted or public to process it.",
            reason="private",
        )
