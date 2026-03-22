"""Shared availability checks for parsed YouTube metadata payloads."""

from __future__ import annotations

from yt_study.errors import VideoUnavailableError


def raise_for_video_availability(data: dict[str, object]) -> None:
    """Raise a user-facing error for restricted video availability states."""
    availability = str(data.get("availability") or "").lower()
    if availability == "private":
        raise VideoUnavailableError(
            "This YouTube video is private. "
            "Retry with --cookie-file / --cookies from an account that can view it, "
            "or make the video unlisted or public.",
            reason="private",
        )
    if availability == "login_required":
        raise VideoUnavailableError(
            "This YouTube video requires sign-in. "
            "Retry with --cookie-file / --cookies, or use a public or unlisted video.",
            reason="login_required",
        )
    if availability == "unavailable":
        raise VideoUnavailableError(
            "This YouTube video isn't available. "
            "Check that the ID is correct and that the video is public or unlisted.",
            reason="unavailable",
        )
    if availability == "age_restricted":
        raise VideoUnavailableError(
            (
                "This YouTube video is age-restricted. "
                "Retry with --cookie-file / --cookies from an eligible account, "
                "or use a public or unrestricted video."
            ),
            reason="age_restricted",
        )


def raise_for_playlist_availability(data: dict[str, object]) -> None:
    """Raise a user-facing error for restricted playlist availability states."""
    availability = str(data.get("availability") or "").lower()
    if availability == "private":
        raise VideoUnavailableError(
            "This YouTube playlist is private. "
            "Retry with --cookie-file / --cookies from an account that can view it, "
            "or make the playlist unlisted or public.",
            reason="private",
        )
    if availability == "unavailable":
        raise VideoUnavailableError(
            "This YouTube playlist isn't available. "
            "Check that the ID is correct and that the playlist is public or unlisted.",
            reason="unavailable",
        )
