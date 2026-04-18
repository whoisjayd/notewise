"""YouTube-specific domain value objects."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VideoChapter:
    """A video chapter with title and time range."""

    title: str
    start_seconds: int
    end_seconds: int | None = None


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
    segments: list[TranscriptSegment]
    language: str
    language_code: str
    is_generated: bool

    def to_text(self) -> str:
        """Convert transcript segments to continuous text."""
        return " ".join(seg.text for seg in self.segments)

    def to_text_with_timestamps(self) -> str:
        """Convert transcript segments to text with [MM:SS] timestamps."""
        parts = []
        for seg in self.segments:
            minutes = int(seg.start // 60)
            seconds = int(seg.start % 60)
            timestamp = f"[{minutes:02d}:{seconds:02d}]"
            parts.append(f"{timestamp} {seg.text}")
        return " ".join(parts)


@dataclass(frozen=True)
class VideoMetadata:
    """All metadata needed by the pipeline for a single video."""

    video_id: str
    title: str
    duration: int
    chapters: list[VideoChapter] = field(default_factory=list)


@dataclass
class ParsedURL:
    """Parsed YouTube URL information."""

    url_type: str  # 'video' | 'playlist'
    video_id: str | None = None
    playlist_id: str | None = None
