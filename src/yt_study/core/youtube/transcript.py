"""Transcript fetching with multi-language support."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    VideoUnplayable,
)

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

    if isinstance(error, VideoUnplayable):
        reason = str(getattr(error, "reason", "") or "").lower()
        sub_reasons = " ".join(getattr(error, "sub_reasons", []) or []).lower()
        error_text = f"{reason} {sub_reasons} {error_text}"

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


def _describe_video_unplayable(error: VideoUnplayable) -> str:
    """Return a short reason string for VideoUnplayable errors."""
    reason = str(getattr(error, "reason", "") or "").strip()
    if reason:
        return reason

    sub_reasons = [item.strip() for item in getattr(error, "sub_reasons", []) if item]
    if sub_reasons:
        return "; ".join(sub_reasons)

    return "video is unplayable"


async def fetch_transcript(
    video_id: str,
    languages: list[str] | None = None,
    on_request: Callable[[], Awaitable[None]] | None = None,
) -> VideoTranscript:
    """
    Fetch transcript for a YouTube video with language fallback and retry logic.

    Priority:
    1. Manual transcript in preferred language
    2. Auto-generated transcript in preferred language
    3. Manual transcript in any available language
    4. Auto-generated transcript in any available language
    5. Translated transcript to English

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

            # Wrap blocking YouTubeTranscriptApi calls in a thread
            # This is critical to prevent blocking the asyncio event loop
            # during concurrency
            raw_transcript, transcript_meta, log_msg = await asyncio.to_thread(
                _fetch_sync, video_id, languages
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

        except (TranscriptsDisabled, VideoUnavailable) as e:
            # Fatal errors, do not retry
            _raise_if_public_access_required(e)
            logger.error(f"Transcript unavailable for {video_id}: {e}")
            raise TranscriptError(
                f"Transcripts are disabled or video is unavailable: {video_id}"
            ) from e

        except VideoUnplayable as e:
            # VideoUnplayable is fatal and often indicates sign-in-only content.
            _raise_if_public_access_required(e)
            reason = _describe_video_unplayable(e)
            logger.error(f"Transcript unavailable for {video_id}: {reason}")
            raise TranscriptError(f"Could not fetch transcript: {reason}") from e

        except (TranscriptError, NoTranscriptFound):
            # Already handled or strictly not found, do not retry
            raise

        except (IpBlocked, RequestBlocked) as e:
            # Specifically handle IP blocking
            logger.error(f"YouTube IP Block detected for {video_id}")
            raise YouTubeIPBlockError(
                "YouTube is blocking requests from your IP. "
                "Please try using a VPN, proxies, or wait a while."
            ) from e

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
) -> tuple[Any, Any, str]:
    """Blocking helper to interact with YouTubeTranscriptApi."""
    ytt_api = YouTubeTranscriptApi()

    # List all available transcripts
    # This list call can fail with TranscriptsDisabled or VideoUnavailable
    transcript_list = ytt_api.list(video_id)

    transcript = None
    found_msg = ""

    # Strategy 1: Find manual transcript in preferred language
    try:
        transcript = transcript_list.find_manually_created_transcript(languages)
        found_msg = f"Found manual transcript: {transcript.language}"
    except NoTranscriptFound:
        pass

    # Strategy 2: Try auto-generated in preferred language
    if not transcript:
        try:
            transcript = transcript_list.find_generated_transcript(languages)
            found_msg = f"Using auto-generated transcript: {transcript.language}"
        except NoTranscriptFound:
            pass

    # Strategy 3: Try any manual transcript
    if not transcript:
        try:
            # Get all language codes available
            all_codes = [t.language_code for t in transcript_list]
            transcript = transcript_list.find_manually_created_transcript(all_codes)
            found_msg = f"Using manual transcript in {transcript.language}"
        except NoTranscriptFound:
            pass

    # Strategy 4: Last resort - try any available transcript and translate if needed
    if not transcript:
        try:
            # list(transcript_list) returns iterable of Transcript objects
            available = list(transcript_list)
            if not available:
                raise NoTranscriptFound(video_id, languages, [])

            first_preferred = next(
                (item for item in available if item.language_code in languages),
                None,
            )
            if first_preferred is not None:
                transcript = first_preferred
                found_msg = f"Using {transcript.language}"
            elif "en" in languages:
                translatable = next(
                    (
                        item
                        for item in available
                        if item.language_code != "en" and item.is_translatable
                    ),
                    None,
                )
                if translatable is not None:
                    transcript = translatable.translate("en")
                    found_msg = f"Translated {translatable.language} -> English"
                else:
                    transcript = available[0]
                    found_msg = (
                        f"Using {transcript.language} (translation not available)"
                    )
            else:
                transcript = available[0]
                found_msg = f"Using {transcript.language}"

        except Exception as e:
            # If we really can't find anything
            if isinstance(e, NoTranscriptFound):
                raise
            raise TranscriptError(f"No usable transcript found: {e}") from e

    # Fetch the actual transcript data
    raw_transcript = transcript.fetch()
    return raw_transcript, transcript, found_msg


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
