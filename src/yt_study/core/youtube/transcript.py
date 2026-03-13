"""Transcript fetching with multi-language support."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Any

from requests import Session
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
)

from .metadata import VideoChapter


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


async def fetch_transcript(
    video_id: str,
    languages: list[str] | None = None,
    cookies_path: Path | None = None,
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
        cookies_path: Optional path to Netscape cookies.txt file.
        on_request: Optional async callback to invoke before each network attempt.

    Returns:
        VideoTranscript object.

    Raises:
        TranscriptError: If no transcript is available.
    """
    if languages is None:
        languages = ["en"]

    retries = 3
    http_client = _build_http_client(cookies_path)
    try:
        for attempt in range(retries):
            try:
                if on_request is not None:
                    await on_request()

                # Wrap blocking YouTubeTranscriptApi calls in a thread
                # This is critical to prevent blocking the asyncio event loop
                # during concurrency
                raw_transcript, transcript_meta, log_msg = await asyncio.to_thread(
                    _fetch_sync, video_id, languages, http_client
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
                logger.error(f"Transcript unavailable for {video_id}: {e}")
                raise TranscriptError(
                    f"Transcripts are disabled or video is unavailable: {video_id}"
                ) from e

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
                        f"Transcript fetch failed ({err_text}), retrying in "
                        f"{wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Failed to fetch transcript for {video_id}: {e}")
                    raise TranscriptError(
                        f"Could not fetch transcript: {str(e)}"
                    ) from e

        # Should be unreachable due to raise in loop
        raise TranscriptError(f"Failed to fetch transcript for {video_id}")
    finally:
        if http_client is not None:
            http_client.close()


def _fetch_sync(
    video_id: str,
    languages: list[str],
    http_client: Session | None = None,
) -> tuple[Any, Any, str]:
    """Blocking helper to interact with YouTubeTranscriptApi."""
    ytt_api = YouTubeTranscriptApi(http_client=http_client)

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


def _build_http_client(cookies_path: Path | None) -> Session | None:
    """Build a requests Session with loaded Netscape cookies, if provided."""
    if cookies_path is None:
        return None

    try:
        resolved_path = cookies_path.expanduser().resolve()
    except Exception as e:  # pragma: no cover - defensive guard
        raise TranscriptError(f"Invalid cookies path: {e}") from e

    if not resolved_path.exists():
        raise TranscriptError(f"Cookies file does not exist: {resolved_path}")

    cookie_jar = MozillaCookieJar(str(resolved_path))
    try:
        cookie_jar.load(ignore_discard=True, ignore_expires=True)
    except Exception as e:
        raise TranscriptError("Failed to parse cookies file.") from e

    session = Session()
    session.cookies.update(cookie_jar)
    logger.info("Using authenticated transcript session from provided cookies file.")
    return session


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

            # Check if segment start is within chapter range
            if chapter.end_seconds is None:
                # Last chapter - include everything after start
                if segment_start >= chapter.start_seconds:
                    chapter_segments.append(segment.text)
            else:
                # Middle chapters - include if in range
                if (
                    segment_start >= chapter.start_seconds
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
