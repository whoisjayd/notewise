"""Synthetic chapter engine to identify sections in unchaptered videos."""

import json
import re
from typing import TYPE_CHECKING

import structlog

from ...prompts.chapters import SYSTEM_PROMPT, get_chapter_generation_prompt
from ..youtube.metadata import VideoChapter


if TYPE_CHECKING:
    from ..youtube.transcript import VideoTranscript
    from .providers import LLMProvider

logger = structlog.get_logger(__name__)


class SyntheticChapterEngine:
    """
    Engine for generating logical chapters for videos lacking them.
    """

    def __init__(self, provider: "LLMProvider"):
        self.provider = provider

    def _parse_timestamp(self, ts_str: str) -> int:
        """Parse [MM:SS] or [HH:MM:SS] into seconds."""
        parts = ts_str.strip("[]").split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except (ValueError, IndexError):
            pass
        return 0

    async def generate_chapters(
        self, transcript: "VideoTranscript"
    ) -> list[VideoChapter]:
        """
        Analyze transcript and generate synthetic chapters.
        """
        logger.info("Generating synthetic chapters", video_id=transcript.video_id)

        # We use timestamped text to help LLM identify boundaries
        text = transcript.to_timestamped_text()

        # If text is too long, we might need to chunk it for chapter identification
        # but for now we'll assume it fits in context for common study videos.
        prompt = get_chapter_generation_prompt(text)

        response = await self.provider.generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=0.1,  # Low temperature for structural consistency
        )

        try:
            # Extract JSON from response (handling potential Markdown wrapping)
            json_match = re.search(r"\[\s*\{.*\}\s*\]", response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
            else:
                data = json.loads(response)

            chapters = []
            for i, entry in enumerate(data):
                title = entry.get("title", f"Section {i + 1}")
                start_ts = entry.get("timestamp", "00:00")
                start_seconds = self._parse_timestamp(start_ts)

                chapters.append(VideoChapter(title=title, start_seconds=start_seconds))

            if not chapters:
                return []

            # Sort by start time
            chapters.sort(key=lambda x: x.start_seconds)

            # Ensure first chapter starts at 0
            if chapters[0].start_seconds > 0:
                chapters.insert(0, VideoChapter(title="Introduction", start_seconds=0))

            # Calculate end times
            for i in range(len(chapters) - 1):
                chapters[i].end_seconds = chapters[i + 1].start_seconds

            return chapters

        except (json.JSONDecodeError, Exception) as e:
            logger.error("Failed to parse synthetic chapters", error=str(e))
            return []
