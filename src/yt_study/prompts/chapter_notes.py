"""Prompt templates for chapter-based study material generation."""

# Prompt for generating notes from a single chapter
CHAPTER_GENERATION_PROMPT = """
Create an in-depth, detailed study guide for this specific chapter:

Chapter Title: {chapter_title}

Transcript:
{transcript_chunk}

Requirements:
1. **Deep Dive**: Provide a thorough, granular explanation of the chapter's topic.
2. **Comprehensive**: Include every nuance, sub-point, and detail mentioned.
3. **Clarify Concepts**: Explain "why" and "how" for every concept, not just "what".
4. **Examples**: Preserve all examples and use them to illustrate technical points.
5. **Structure**: Use deeply nested headers (###, ####) to break down complex ideas.
6. Pure Markdown format.
7. English language.
8. **DO NOT include any opening or closing conversational text.**
9. **Start directly with the first header (e.g., # Chapter Title)**"""


# Prompt for combining chapter notes
COMBINE_CHAPTER_NOTES_PROMPT = """
You have generated study notes for different chapters of the same video.
Combine these chapter notes into a single, well-organized study document.

Video chapters and notes:
{chapter_notes}

Requirements:
1. Keep chapter structure with clear headers (## Chapter Title)
2. Ensure logical flow between chapters
3. Remove redundancies while preserving all unique information
4. Add a brief introduction summarizing what the video covers
5. Maintain all important details from every chapter
6. Use proper Markdown hierarchy (##, ###, etc.)
7. Do NOT add a table of contents
8. Create a cohesive document that's easy to navigate and review"""


def get_chapter_prompt(chapter_title: str, transcript_chunk: str) -> str:
    """Generate prompt for a chapter."""
    return CHAPTER_GENERATION_PROMPT.format(
        chapter_title=chapter_title, transcript_chunk=transcript_chunk
    )


def get_combine_chapters_prompt(chapter_notes: dict[str, str]) -> str:
    """Generate prompt for combining chapter notes."""
    combined = "\n\n".join(
        [f"## {title}\n\n{notes}" for title, notes in chapter_notes.items()]
    )
    return COMBINE_CHAPTER_NOTES_PROMPT.format(chapter_notes=combined)
