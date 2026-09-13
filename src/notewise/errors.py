"""Centralized exceptions and error utilities for NoteWise.

All custom exceptions are defined here. Import from ``notewise.errors`` in
all application code. Never define project-specific exceptions elsewhere.
"""

from __future__ import annotations

import re

from notewise._constants import OAUTH_FALLBACK_MESSAGE


_MODEL_FROM_GENERATION_FAILURE = re.compile(r"Failed to generate with ([^:]+):")


class NoteWiseError(Exception):
    """Base class for all NoteWise application exceptions."""

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


class ConfigurationError(NoteWiseError):
    """Raised for invalid configuration or missing required settings."""


class ValidationError(NoteWiseError):
    """Raised for invalid user input (URL, file path, option value)."""


class UserVisibleCliError(NoteWiseError):
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


class YouTubeError(NoteWiseError):
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


class LLMError(NoteWiseError):
    """Base for LLM provider errors."""


class LLMGenerationError(LLMError):
    """Raised when the LLM returns an error or empty result."""


class PartialChapterGenerationError(LLMError):
    """Raised when some chapters in a concurrent batch generated fine but at
    least one failed.

    Carries the notes that *did* complete so the caller can still persist
    them to their chapter_file targets before propagating failure -- without
    this, a single stuck chapter (a slow free-tier model, a transient
    timeout) would otherwise discard every sibling chapter's already-paid-for
    generation, forcing a full-video regeneration on retry.
    """

    def __init__(
        self,
        completed: dict[str, str],
        failures: list[tuple[str, BaseException]],
    ) -> None:
        self.completed = completed
        self.failures = failures
        summary = "; ".join(f"{title!r}: {error}" for title, error in failures)
        super().__init__(
            f"{len(failures)} of {len(completed) + len(failures)} chapters "
            f"failed to generate: {summary}"
        )


class OAuthError(LLMError):
    """Raised when OAuth/device-flow provider login cannot proceed."""


class CustomEndpointError(LLMError):
    """Raised when a custom OpenAI-compatible endpoint cannot be used safely."""


class PersistenceError(NoteWiseError):
    """Raised on SQLite / database failures."""


class UpdateError(NoteWiseError):
    """Raised when checking for new releases fails."""


def raise_if_video_unavailable(
    error_text: str,
    *,
    video_id: str | None = None,
) -> None:
    """Raise VideoUnavailableError when error_text indicates an access restriction."""
    text = error_text.lower()

    if (
        "private video" in text
        or "this is a private video" in text
        or "private playlist" in text
        or "video is private" in text
        or text.strip().endswith("is private")
    ):
        raise VideoUnavailableError(
            "This YouTube content is private. "
            "Retry with --cookie-file / --cookies from an account that can view it, "
            "or make it unlisted or public.",
            video_id=video_id,
            reason="private",
        )
    if "members-only" in text or "members only" in text:
        raise VideoUnavailableError(
            "This YouTube content is members-only. "
            "Retry with --cookie-file / --cookies from an account that has access, "
            "or use a public or unlisted alternative.",
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
                "This YouTube content is age-restricted. "
                "Retry with --cookie-file / --cookies from an eligible account, "
                "or use a public or unrestricted alternative."
            ),
            video_id=video_id,
            reason="age_restricted",
        )
    if any(
        marker in text
        for marker in (
            "video unavailable",
            "video is unavailable",
            "not found",
            "does not exist",
            "no video found",
            "removed",
            "deleted",
        )
    ):
        raise VideoUnavailableError(
            "This YouTube content isn't available. "
            "Check that the ID is correct and that the video or playlist is public.",
            video_id=video_id,
            reason="unavailable",
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
            "This YouTube content requires sign-in. "
            "Retry with --cookie-file / --cookies, or use a public or unlisted video.",
            video_id=video_id,
            reason="login_required",
        )


def format_user_error(error: Exception) -> str:
    """Return a plain-English failure message suitable for end-user display."""
    if isinstance(error, ValidationError):
        return str(error).split(" [")[0]

    if isinstance(error, VideoUnavailableError):
        return str(error).split(" [")[0]

    if isinstance(error, PartialChapterGenerationError):
        total = len(error.completed) + len(error.failures)
        failed_titles = ", ".join(title for title, _ in error.failures[:3])
        if len(error.failures) > 3:
            failed_titles += f", and {len(error.failures) - 3} more"
        return (
            f"{len(error.completed)}/{total} chapters generated; "
            f"{len(error.failures)} failed ({failed_titles}). Completed "
            "chapters were saved -- rerunning will skip them and only "
            "retry what failed."
        )

    if isinstance(error, IPBlockError):
        return (
            "YouTube is temporarily blocking requests from this network. "
            "Try again later, lower the request rate, or switch networks."
        )

    if isinstance(error, TranscriptUnavailableError):
        error_text = str(error).lower()
        if (
            "transcripts are disabled" in error_text
            or "no transcript" in error_text
            or "could not fetch transcript" in error_text
            or "no usable transcript" in error_text
        ):
            return (
                "We couldn't get a usable transcript for this video. "
                "Make sure captions are available, try another language, "
                "or use a different video."
            )
        return "We couldn't get a usable transcript for this video."

    if isinstance(error, OAuthError):
        return OAUTH_FALLBACK_MESSAGE

    if isinstance(error, CustomEndpointError):
        return str(error).split(" [")[0]

    raw_text = str(error)
    text = raw_text.strip().lower()
    model_match = _MODEL_FROM_GENERATION_FAILURE.search(raw_text)
    model_suffix = f" ({model_match.group(1)})" if model_match else ""

    if "idle timeout" in text:
        return (
            f"The model{model_suffix} stopped responding mid-generation and "
            "timed out after retrying. This is usually a slow or overloaded "
            "(often free-tier) model -- try a different/paid model, or lower "
            "MAX_CONCURRENT_CHAPTERS if you're running several chapters at once."
        )

    if "timeout" in text or "timed out" in text:
        return (
            f"The request to the model{model_suffix} timed out while "
            "processing this video. Try again, or switch to a faster model "
            "if this keeps happening."
        )

    if any(
        kw in text
        for kw in (
            "network",
            "connection reset",
            "connection aborted",
            "connection refused",
        )
    ):
        return (
            f"A network problem interrupted the request to the "
            f"model{model_suffix}. Check your connection and try again."
        )

    if any(kw in text for kw in ("rate limit", "too many requests", " 429")):
        return (
            "The upstream service is rate-limiting requests right now. "
            "Please try again later."
        )

    if any(
        kw in text
        for kw in (
            "api key",
            "unauthorized",
            "authentication",
            "invalid api key",
            "permission_denied",
            "permission denied for model",
            "forbidden",
        )
    ):
        return (
            "The selected model or provider is not configured correctly. "
            "Check your API key and try again."
        )

    if any(kw in text for kw in ("permission denied", "access is denied")):
        return (
            "NoteWise could not write the output files. "
            "Check the output folder permissions and try again."
        )

    return (
        "We couldn't process this video. "
        "Check the current session log for technical details."
    )


__all__ = [
    "ConfigurationError",
    "CustomEndpointError",
    "ExtractionError",
    "IPBlockError",
    "LLMError",
    "LLMGenerationError",
    "NoteWiseError",
    "OAuthError",
    "PartialChapterGenerationError",
    "PersistenceError",
    "PlaylistError",
    "TranscriptUnavailableError",
    "UpdateError",
    "UserVisibleCliError",
    "ValidationError",
    "VideoUnavailableError",
    "YouTubeError",
    "format_user_error",
    "raise_if_video_unavailable",
]
