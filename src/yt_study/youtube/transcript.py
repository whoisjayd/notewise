"""Transcript fetching with multi-language support."""

import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional

from rich.console import Console
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

console = Console()
logger = logging.getLogger(__name__)


@dataclass
class TranscriptSegment:
    """A segment of transcript text with timing."""
    
    text: str
    start: float
    duration: float


@dataclass
class VideoTranscript:
    """Complete transcript for a video."""
    
    video_id: str
    segments: List[TranscriptSegment]
    language: str
    language_code: str
    is_generated: bool
    
    def to_text(self) -> str:
        """Convert transcript segments to continuous text."""
        return " ".join(segment.text for segment in self.segments)


class TranscriptError(Exception):
    """Exception raised for transcript-related errors."""
    pass


async def fetch_transcript(
    video_id: str,
    languages: Optional[List[str]] = None
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
        video_id: YouTube video ID
        languages: Preferred language codes (e.g., ['en', 'hi']). Defaults to ['en']
        
    Returns:
        VideoTranscript object
        
    Raises:
        TranscriptError: If no transcript is available
    """
    if languages is None:
        languages = ['en']
    
    retries = 3
    
    for attempt in range(retries):
        try:
            # Wrap blocking YouTubeTranscriptApi calls in a thread
            # This is critical to prevent blocking the asyncio event loop during concurrency
            def _fetch_sync():
                ytt_api = YouTubeTranscriptApi()
                
                # List all available transcripts
                transcript_list = ytt_api.list(video_id)
                
                # Try to find manually created transcript first
                try:
                    transcript = transcript_list.find_manually_created_transcript(languages)
                    found_msg = f"Found manual transcript: {transcript.language}"
                except NoTranscriptFound:
                    # Try auto-generated
                    try:
                        transcript = transcript_list.find_generated_transcript(languages)
                        found_msg = f"Using auto-generated transcript: {transcript.language}"
                    except NoTranscriptFound:
                        # Try any manual transcript
                        try:
                            transcript = transcript_list.find_manually_created_transcript(
                                [t.language_code for t in transcript_list]
                            )
                            found_msg = f"Using manual transcript in {transcript.language}"
                        except NoTranscriptFound:
                            # Last resort: try to get any available transcript and translate to English
                            available = list(transcript_list)
                            if not available:
                                raise TranscriptError(f"No transcripts available for video {video_id}")
                            
                            first_available = available[0]
                            
                            # Try to translate to English if not English already
                            if 'en' in languages and first_available.language_code != 'en':
                                if first_available.is_translatable:
                                    transcript = first_available.translate('en')
                                    found_msg = f"Translated {first_available.language} → English"
                                else:
                                    transcript = first_available
                                    found_msg = f"Using {transcript.language} (translation not available)"
                            else:
                                transcript = first_available
                                found_msg = f"Using {transcript.language}"
                
                # Fetch the actual transcript data
                raw_transcript = transcript.fetch()
                return raw_transcript, transcript, found_msg

            # Execute sync logic in thread
            raw_transcript, transcript, log_msg = await asyncio.to_thread(_fetch_sync)
            logger.info(log_msg)
            
            # Convert to our format
            # raw_transcript is a list of dicts: {'text': '...', 'start': 0.0, 'duration': 0.0}
            segments = []
            for segment in raw_transcript:
                # Handle both dict and object access just in case
                if isinstance(segment, dict):
                    text = segment.get('text', '')
                    start = segment.get('start', 0.0)
                    duration = segment.get('duration', 0.0)
                else:
                    text = getattr(segment, 'text', '')
                    start = getattr(segment, 'start', 0.0)
                    duration = getattr(segment, 'duration', 0.0)
                    
                segments.append(TranscriptSegment(
                    text=text,
                    start=start,
                    duration=duration
                ))
            
            return VideoTranscript(
                video_id=video_id,
                segments=segments,
                language=transcript.language,
                language_code=transcript.language_code,
                is_generated=transcript.is_generated
            )
            
        except (TranscriptsDisabled, VideoUnavailable) as e:
            # Fatal errors, do not retry
            logger.error(f"Transcript unavailable for {video_id}: {e}")
            raise TranscriptError(f"Transcripts are disabled or video is unavailable: {video_id}") from e
            
        except (TranscriptError, NoTranscriptFound) as e:
            # Already handled or strictly not found, do not retry
            raise

        except Exception as e:
            if attempt < retries - 1:
                wait_time = 2 ** attempt
                logger.warning(f"Transcript fetch failed ({str(e)}), retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Failed to fetch transcript for {video_id}: {e}")
                raise TranscriptError(f"Could not fetch transcript: {str(e)}")
    
    # Should be unreachable due to raise in loop, but for type safety:
    raise TranscriptError(f"Failed to fetch transcript for {video_id}")


def split_transcript_by_chapters(
    transcript: VideoTranscript,
    chapters: List
) -> dict[str, str]:
    """
    Split a video transcript by chapters.
    
    Args:
        transcript: VideoTranscript object
        chapters: List of VideoChapter objects
        
    Returns:
        Dictionary mapping chapter titles to their transcript text
    """
    from ..youtube.metadata import VideoChapter
    
    chapter_transcripts = {}
    
    for chapter in chapters:
        # Filter segments for this chapter
        chapter_segments = []
        
        for segment in transcript.segments:
            segment_start = segment.start
            segment_end = segment.start + segment.duration
            
            # Check if segment overlaps with chapter time range
            if chapter.end_seconds is None:
                # Last chapter - include everything after start
                if segment_start >= chapter.start_seconds:
                    chapter_segments.append(segment.text)
            else:
                # Middle chapters - include if in range
                if segment_start >= chapter.start_seconds and segment_start < chapter.end_seconds:
                    chapter_segments.append(segment.text)
        
        # Combine segments for this chapter
        chapter_text = " ".join(chapter_segments)
        chapter_transcripts[chapter.title] = chapter_text
    
    return chapter_transcripts
