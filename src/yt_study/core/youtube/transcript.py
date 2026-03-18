"""Transcript fetching with multi-language support."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .extractor.client import ExtractorClient, ExtractorConfig, ExtractorError
from .metadata import PublicAccessRequiredError, VideoChapter


logger = logging.getLogger(__name__)


@dataclass
class TranscriptSegment:
    """
    A segment of transcript text with timing.

    Attributes:
        text: The spoken text.
        start: Start time in seconds.
        duration: Duration of the segment in seconds.
    """

    text: str
    start: float
    duration: float


@dataclass
class VideoTranscript:
    """
    Complete transcript for a video.

    Attributes:
        video_id: The YouTube video ID.
        segments: List of transcript segments.
        language: Language name (e.g., 'English').
        language_code: Language code (e.g., 'en').
        is_generated: Whether the transcript is auto-generated.
    """

    video_id: str
    segments: list[TranscriptSegment]
    language: str
    language_code: str
    is_generated: bool

    def to_text(self) -> str:
        """Convert transcript segments to continuous text."""
        return " ".join(segment.text for segment in self.segments)


class TranscriptError(Exception):
    """Exception raised for transcript-related errors."""

    pass


class YouTubeIPBlockError(TranscriptError):
    """Exception raised when YouTube blocks IP."""

    pass


def _raise_if_public_access_required(error: Exception) -> None:
    """Convert private or sign-in-only transcript failures into user-facing errors."""
    error_text = str(error).lower()

    if "private" in error_text:
        raise PublicAccessRequiredError(
            "Private YouTube videos are not supported. "
            "Make the video unlisted or public to process it."
        ) from error

    if "members-only" in error_text or "members only" in error_text:
        raise PublicAccessRequiredError(
            "Members-only YouTube videos are not supported. "
            "Use a public or unlisted video to process it."
        ) from error

    if "age restricted" in error_text or "age-restricted" in error_text:
        raise PublicAccessRequiredError(
            "Age-restricted YouTube videos are not supported. "
            "Use a public or unlisted video without sign-in requirements to process it."
        ) from error

    if (
        "sign in" in error_text
        or "sign-in" in error_text
        or "log in" in error_text
        or "login" in error_text
        or "without logging in" in error_text
    ):
        raise PublicAccessRequiredError(
            "Sign-in-only YouTube videos are not supported. "
            "Use a public or unlisted video to process it."
        ) from error


def _extract_error_reason(error: Exception) -> str:
    """Return a concise error string for user-facing failures."""
    message = str(error).strip()
    if message:
        return message
    return "video is unavailable"


async def fetch_transcript(
    video_id: str,
    languages: list[str] | None = None,
    on_request: Callable[[], Awaitable[None]] | None = None,
    cookie_file: str | None = None,
) -> VideoTranscript:
    """
    Fetch transcript for a YouTube video with language fallback and retry logic.

    Priority:
    Strategy:
    1. Native subtitle tracks in preferred language order
    2. Automatic captions fallback when enabled
    3. Innertube player transcript fallback

    Args:
        video_id: YouTube video ID.
        languages: Preferred language codes (e.g., ['en', 'hi']). Defaults to ['en'].
        on_request: Optional async callback to invoke before each network attempt.

    Returns:
        VideoTranscript object.

    Raises:
        TranscriptError: If no transcript is available.
    """
    if languages is None:
        languages = ["en"]

    retries = 3
    for attempt in range(retries):
        try:
            if on_request is not None:
                await on_request()

            # Wrap blocking extractor calls in a thread
            # This is critical to prevent blocking the asyncio event loop
            # during concurrency
            raw_transcript, transcript_meta, log_msg = await asyncio.to_thread(
                _fetch_sync,
                video_id,
                languages,
                cookie_file,
            )

            logger.info(log_msg)

            # Convert to our format
            segments = []
            for segment in raw_transcript:
                # Handle both dict (standard) and object
                # (FetchedTranscriptSnippet) formats
                if isinstance(segment, dict):
                    text = segment.get("text", "")
                    start = segment.get("start", 0.0)
                    duration = segment.get("duration", 0.0)
                else:
                    # Fallback for object-based returns
                    text = getattr(segment, "text", "")
                    start = getattr(segment, "start", 0.0)
                    duration = getattr(segment, "duration", 0.0)

                segments.append(
                    TranscriptSegment(
                        text=text, start=float(start), duration=float(duration)
                    )
                )

            return VideoTranscript(
                video_id=video_id,
                segments=segments,
                language=transcript_meta.language,
                language_code=transcript_meta.language_code,
                is_generated=transcript_meta.is_generated,
            )

        except TranscriptError:
            # Already handled or strictly not found, do not retry
            raise

        except Exception as e:
            _raise_if_public_access_required(e)
            err_str = str(e)
            if "blocking requests from your IP" in err_str:
                logger.error(f"YouTube IP Block detected for {video_id}: {e}")
                raise YouTubeIPBlockError(
                    "YouTube is blocking requests from your IP. "
                    "Please try using a VPN, proxies, or wait a while."
                ) from e

            if attempt < retries - 1:
                wait_time = 2**attempt
                err_text = str(e)
                logger.warning(
                    f"Transcript fetch failed ({err_text}), retrying in {wait_time}s..."
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Failed to fetch transcript for {video_id}: {e}")
                raise TranscriptError(f"Could not fetch transcript: {str(e)}") from e

    # Should be unreachable due to raise in loop
    raise TranscriptError(f"Failed to fetch transcript for {video_id}")


def _fetch_sync(
    video_id: str,
    languages: list[str],
    cookie_file: str | None = None,
) -> tuple[Any, Any, str]:
    """Blocking helper to interact with the native extractor client."""
    try:
        payload = ExtractorClient(
            ExtractorConfig(
                cookie_file=cookie_file,
            )
        ).transcript(
            video_id,
            languages=languages,
            include_automatic=True,
        )
    except ExtractorError as error:
        message = str(error)
        if "no transcript/subtitle track found" in message.lower():
            raise TranscriptError("No usable transcript found") from error
        raise

    raw_transcript = payload.get("segments") or []
    language_code = str(payload.get("language_code") or "")
    track = payload.get("track") or {}
    language_name = str(track.get("name") or language_code or "Unknown")
    transcript_meta = type(
        "NativeTranscriptMeta",
        (),
        {
            "language": language_name,
            "language_code": language_code,
            "is_generated": bool(payload.get("is_generated")),
        },
    )()
    found_msg = f"Using native transcript: {language_name}"
    return raw_transcript, transcript_meta, found_msg


def split_transcript_by_chapters(
    transcript: VideoTranscript, chapters: list[VideoChapter]
) -> dict[str, str]:
    """
    Split a video transcript by chapters.

    Args:
        transcript: VideoTranscript object.
        chapters: List of VideoChapter objects.

    Returns:
        Dictionary mapping chapter titles to their transcript text.
    """
    chapter_transcripts = {}
    seen_titles: dict[str, int] = {}

    for chapter in chapters:
        # Filter segments for this chapter
        chapter_segments = []

        for segment in transcript.segments:
            segment_start = segment.start
            segment_end = segment.start + max(segment.duration, 0.0)

            # Include any segment that overlaps the chapter window.
            if chapter.end_seconds is None:
                if segment_end > chapter.start_seconds:
                    chapter_segments.append(segment.text)
            else:
                if (
                    segment_end > chapter.start_seconds
                    and segment_start < chapter.end_seconds
                ):
                    chapter_segments.append(segment.text)

        # Combine segments for this chapter
        chapter_text = " ".join(chapter_segments)
        if not chapter_text.strip():
            logger.warning(
                f"No transcript segments found for chapter: {chapter.title!r}"
            )
            continue
        seen_titles[chapter.title] = seen_titles.get(chapter.title, 0) + 1
        occurrence = seen_titles[chapter.title]
        unique_title = (
            chapter.title if occurrence == 1 else f"{chapter.title} ({occurrence})"
        )
        chapter_transcripts[unique_title] = chapter_text

    return chapter_transcripts
