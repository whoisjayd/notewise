"""Centralized exception hierarchy for yt-study.

All custom exceptions are defined here. Import from ``yt_study.errors`` in
all application code. Never define project-specific exceptions elsewhere.
"""

from __future__ import annotations


class YtStudyError(Exception):
    """Base class for all yt-study application exceptions."""

    def __init__(self, message: str = "", **context: object) -> None:
        super().__init__(message)
        self._context: dict[str, object] = context

    @property
    def context(self) -> dict[str, object]:
        return dict(self._context)

    def __str__(self) -> str:
        base = super().__str__()
        if self._context:
            ctx = ", ".join(f"{k}={v!r}" for k, v in self._context.items())
            return f"{base} [{ctx}]"
        return base


class ConfigurationError(YtStudyError):
    """Raised for invalid configuration or missing required settings."""


class ValidationError(YtStudyError):
    """Raised for invalid user input (URL, file path, option value)."""


class UserVisibleCliError(YtStudyError):
    """Structured CLI failure that should be rendered without a traceback."""

    def __init__(
        self,
        title: str,
        rows: list[tuple[str, str]],
        *,
        intro: str | None = None,
    ) -> None:
        super().__init__(title)
        self.title = title
        self.rows = rows
        self.intro = intro


# ── YouTube ───────────────────────────────────────────────────────────────────


class YouTubeError(YtStudyError):
    """Base for all YouTube-related errors."""


class VideoUnavailableError(YouTubeError):
    """Raised when a video/playlist requires sign-in or is private/restricted."""


class TranscriptUnavailableError(YouTubeError):
    """Raised when no usable transcript track can be found or fetched."""


class IPBlockError(YouTubeError):
    """Raised when YouTube blocks requests from the current network."""


class PlaylistError(YouTubeError):
    """Raised when a playlist cannot be accessed or expanded."""


class ExtractionError(YouTubeError):
    """Raised on low-level HTML parsing or innertube API failure."""


# ── LLM ───────────────────────────────────────────────────────────────────────


class LLMError(YtStudyError):
    """Base for LLM provider errors."""


class LLMGenerationError(LLMError):
    """Raised when the LLM returns an error or empty result."""


# ── Persistence ───────────────────────────────────────────────────────────────


class PersistenceError(YtStudyError):
    """Raised on SQLite / database failures."""


# ── Shared guard helper ───────────────────────────────────────────────────────


def raise_if_video_unavailable(
    error_text: str,
    *,
    video_id: str | None = None,
) -> None:
    """Raise VideoUnavailableError when error_text indicates an access restriction.

    Replaces the duplicated _raise_if_public_access_required helpers that
    previously existed across transcript.py, metadata.py, and playlist.py.
    """
    text = error_text.lower()

    if (
        "private video" in text
        or "this is a private video" in text
        or "private playlist" in text
        or "video is private" in text
        or text.strip().endswith("is private")
    ):
        raise VideoUnavailableError(
            "Private YouTube videos are not supported. "
            "Make the video unlisted or public to process it.",
            video_id=video_id,
            reason="private",
        )
    if "members-only" in text or "members only" in text:
        raise VideoUnavailableError(
            "Members-only YouTube videos are not supported. "
            "Use a public or unlisted video to process it.",
            video_id=video_id,
            reason="members_only",
        )
    if (
        "age restricted" in text
        or "age-restricted" in text
        or "sign in to confirm your age" in text
        or "without logging in" in text
    ):
        raise VideoUnavailableError(
            (
                "Age-restricted YouTube videos are not supported. "
                "Use a public or unlisted video without sign-in requirements "
                "to process it."
            ),
            video_id=video_id,
            reason="age_restricted",
        )
    if (
        "sign in" in text
        or "sign-in" in text
        or "please sign in" in text
        or "requires login to view" in text
        or ("login" in text and "without logging in" not in text)
        or "log in" in text
    ):
        raise VideoUnavailableError(
            "Sign-in-only YouTube videos are not supported. "
            "Use a public or unlisted video to process it.",
            video_id=video_id,
            reason="login_required",
        )
