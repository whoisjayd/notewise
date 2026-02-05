"""Prompts for synthetic chapter generation."""

SYSTEM_PROMPT = """You are an expert video content analyst. Your task is to identify logical chapters or sections within a video transcript.
For each chapter, provide a clear, descriptive title and the exact timestamp in [MM:SS] format where it begins."""

CHAPTER_GENERATION_PROMPT = """Analyze the following transcript and identify its logical sections.
For each section, provide:
1. The start timestamp in [MM:SS] format (must be one from the transcript).
2. A concise, descriptive title for the section.

Format your response as a JSON list of objects:
[
  {{"timestamp": "00:00", "title": "Introduction"}},
  {{"timestamp": "05:12", "title": "Main Topic Analysis"}},
  ...
]

Transcript:
{transcript}
"""

def get_chapter_generation_prompt(transcript: str) -> str:
    """Get the prompt for generating synthetic chapters."""
    return CHAPTER_GENERATION_PROMPT.format(transcript=transcript)
