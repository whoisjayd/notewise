"""Prompt templates for quiz generation from video transcripts."""

QUIZ_SYSTEM_PROMPT = """
You are an expert educator specialising in active-recall learning.
Your task is to turn video content into a well-structured multiple-choice quiz
that tests genuine understanding of the material — not just memorisation.

Rules:
- Write questions that test comprehension, application, and analysis.
- Every question must have exactly **4 answer options** (A, B, C, D).
- Exactly one option is correct; the other three are plausible distractors.
- Cover the most important concepts proportionally across the transcript.
- Output clean Markdown only — no HTML, no preamble, no closing remarks.
- Start directly with the quiz title header."""

QUIZ_GENERATION_PROMPT = """
Create a multiple-choice quiz based on this video transcript.

Transcript:
{transcript}

Requirements:
1. Generate **10–15 questions** that span the full transcript.
2. Each question must be clearly numbered (e.g., **Q1.**, **Q2.**).
3. List answer options on separate lines prefixed with A), B), C), D).
4. After all options include a line: **Answer: X)** (replace X with the correct letter).
5. Add a one-sentence **Explanation:** after each answer.
6. Group questions under `## Section` headers that match the video's main topics.
7. End with a `## Answer Key` section listing only question numbers and correct letters.

Example format:
---
## Topic One

**Q1.** Question text here?

A) Option one
B) Option two
C) Option three
D) Option four

**Answer: B)**
**Explanation:** Brief reason why B is correct.

---
## Answer Key
Q1 – B
"""


def get_quiz_prompt(transcript: str) -> str:
    """Generate prompt for creating a quiz from a transcript."""
    return QUIZ_GENERATION_PROMPT.format(transcript=transcript)
