"""Convert internal exceptions into non-technical user-facing messages."""

from __future__ import annotations

from .exceptions import IPBlockError, TranscriptUnavailableError, VideoUnavailableError


def format_user_error(error: Exception) -> str:
    """Return a plain-English failure message suitable for end-user display."""
    if isinstance(error, VideoUnavailableError):
        # Strip the structured context suffix so users see a clean message.
        return str(error).split(" [")[0]

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

    text = str(error).strip().lower()

    if "timeout" in text or "timed out" in text:
        return "The request timed out while processing this video. Please try again."

    if any(
        kw in text
        for kw in (
            "network",
            "connection reset",
            "connection aborted",
            "connection refused",
        )
    ):
        return "A network problem interrupted processing. Please try again."

    if any(kw in text for kw in ("rate limit", "too many requests", " 429")):
        return (
            "The upstream service is rate-limiting requests right now. "
            "Please try again later."
        )

    if any(kw in text for kw in ("api key", "unauthorized", "authentication")):
        return (
            "The selected model or provider is not configured correctly. "
            "Check your API key and try again."
        )

    if any(kw in text for kw in ("permission denied", "access is denied")):
        return (
            "yt-study could not write the output files. "
            "Check the output folder permissions and try again."
        )

    return (
        "We couldn't process this video. "
        "Check the current session log for technical details."
    )
