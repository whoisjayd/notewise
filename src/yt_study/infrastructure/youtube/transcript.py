"""Transcript fetching with multi-language support."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from yt_study._constants import DEFAULT_LANGUAGES, TRANSCRIPT_MAX_RETRIES
from yt_study.domain.youtube import TranscriptSegment, VideoChapter, VideoTranscript
from yt_study.errors import (
    ExtractionError,
    IPBlockError,
    TranscriptUnavailableError,
    VideoUnavailableError,
    raise_if_video_unavailable,
)
from yt_study.infrastructure.youtube.extractor import (
    AsyncYouTubeExtractorClient,
    YouTubeExtractorConfig,
)


logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


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
    """Fetch transcript for a YouTube video with language fallback and retries."""
    if languages is None:
        languages = list(DEFAULT_LANGUAGES)

    retries = TRANSCRIPT_MAX_RETRIES
    for attempt in range(retries):
        try:
            if on_request is not None:
                await on_request()

            raw_transcript, transcript_meta, log_msg = await _fetch_async(
                video_id,
                languages,
                cookie_file,
            )

            logger.info(log_msg)

            segments: list[TranscriptSegment] = []
            for segment in raw_transcript:
                if isinstance(segment, dict):
                    text = segment.get("text", "")
                    start = segment.get("start", 0.0)
                    duration = segment.get("duration", 0.0)
                else:
                    text = getattr(segment, "text", "")
                    start = getattr(segment, "start", 0.0)
                    duration = getattr(segment, "duration", 0.0)

                segments.append(
                    TranscriptSegment(
                        text=text,
                        start=float(start),
                        duration=float(duration),
                    )
                )

            return VideoTranscript(
                video_id=video_id,
                segments=segments,
                language=transcript_meta.language,
                language_code=transcript_meta.language_code,
                is_generated=transcript_meta.is_generated,
            )

        except TranscriptUnavailableError:
            raise
        except VideoUnavailableError:
            raise
        except Exception as error:
            raise_if_video_unavailable(str(error))
            err_str = str(error)
            if "blocking requests from your IP" in err_str:
                logger.error(f"YouTube IP Block detected for {video_id}: {error}")
                raise IPBlockError(
                    "YouTube is blocking requests from your IP. "
                    "Please try using a VPN, proxies, or wait a while."
                ) from error

            if attempt < retries - 1:
                wait_time = 2**attempt
                logger.warning(
                    f"Transcript fetch failed ({error}), retrying in {wait_time}s..."
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Failed to fetch transcript for {video_id}: {error}")
                raise TranscriptUnavailableError(
                    f"Could not fetch transcript: {error}"
                ) from error

    raise TranscriptUnavailableError(f"Failed to fetch transcript for {video_id}")


async def _fetch_async(
    video_id: str,
    languages: list[str],
    cookie_file: str | None = None,
) -> tuple[Any, Any, str]:
    """Async helper to interact with the async extractor client."""
    try:
        client = AsyncYouTubeExtractorClient(
            YouTubeExtractorConfig(cookie_file=cookie_file)
        )
        payload = await client.transcript(
            video_id,
            languages=languages,
            include_automatic=True,
        )
    except ExtractionError as error:
        message = str(error)
        raise_if_video_unavailable(message)
        if "no transcript/subtitle track found" in message.lower():
            raise TranscriptUnavailableError("No usable transcript found") from error
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
    transcript: VideoTranscript,
    chapters: list[VideoChapter],
) -> dict[str, str]:
    """Split a video transcript by chapters."""
    chapter_transcripts: dict[str, str] = {}
    seen_titles: dict[str, int] = {}

    for chapter in chapters:
        chapter_segments: list[str] = []

        for segment in transcript.segments:
            segment_start = segment.start
            segment_end = segment.start + max(segment.duration, 0.0)

            if chapter.end_seconds is None:
                if segment_end > chapter.start_seconds:
                    chapter_segments.append(segment.text)
            elif (
                segment_end > chapter.start_seconds
                and segment_start < chapter.end_seconds
            ):
                chapter_segments.append(segment.text)

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
