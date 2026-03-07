"""Prompt templates for study material generation and chunk combining."""

# System prompt for generating study notes from transcript chunks
SYSTEM_PROMPT = """
You are an expert academic tutor and technical writer dedicated to creating
the most comprehensive study materials possible.

Your goal is to transform video transcripts into deep, detailed, and highly
structured study notes.
You prioritize:
- **Depth**: Go beyond surface-level summaries. Explain *why* and *how*, not
  just *what*.
- **Comprehensive Coverage**: Capture every single concept, detail, nuance,
  and example mentioned.
- **Clarity**: Use clear, academic yet accessible language. Break down complex topics.
- **Structure**: Use logical hierarchy (headers, subheaders) to organize
  information effectively.

Always generate output in clean Markdown format."""

# User prompt for individual transcript chunks
CHUNK_GENERATION_PROMPT = """
Create extremely detailed and in-depth study notes from this transcript
segment:

{transcript_chunk}

Requirements:
1. **Comprehensive Coverage**: Cover EVERY concept, definition, theory, and
   significant detail mentioned. Do not summarize; expand.
2. **In-Depth Explanation**: Explain complex ideas thoroughly. If a process
   is described, break it down step-by-step.
3. **Capture Examples & Code**: Include ALL examples, case studies, and
   especially **CODE BLOCKS/SQL** provided in the transcript.
4. **Technical Precision**: Use actual SQL syntax for table definitions
   (e.g., `CREATE TABLE`), not just descriptions.
5. **Logical Structure**: Use deep hierarchy (##, ###, ####) to organize
   related concepts.
6. **Key Terminology**: Highlight and define technical terms or important vocabulary.
7. **Pure Markdown**: No HTML, no table of contents.
8. **Clean Start**: Start directly with the content headers, no conversational filler.
9. **Language**: English."""

# Prompt for combining multiple chunk notes into final document
COMBINE_CHUNKS_PROMPT = """
You have generated study notes for multiple segments of the same video. Now
combine these segments into a single, coherent study document.

Segment notes:
{chunk_notes}

Requirements:
1. Merge all segments into a unified, flowing document
2. **Preserve ALL Content**: Do NOT summarize or condense. Retain all
   explanations, examples, code blocks, and details.
3. **Preserve Code & Syntax**: Use valid `CREATE TABLE` SQL and other
   specific syntax exactly as presented.
4. **Seamless Merge**: Connect segments smoothly, but do not delete content for brevity.
5. **Detailed & Comprehensive**: The final document must be as detailed as
   the input segments combined.
6. Maintain consistent formatting and structure (##, ###).
7. Do NOT add a table of contents.
8. **Example clean output:** "# Title\\n\\n## Section 1..."

Create study notes that are comprehensive, well-organized, and easy to review."""

# Prompt for single-pass generation (small transcripts)
SINGLE_PASS_PROMPT = """
Create an extensive and in-depth study guide from this complete video
transcript:

{transcript}

Requirements:
1. **Exhaustive Coverage**: Cover every single topic discussed. Do not leave
   out details.
2. **Deep Understanding**: Explain concepts clearly and thoroughly, as if
   teaching a student.
3. **Structured Learning**: Use a clear, logical hierarchy (##, ###, ####)
   to organize topics.
4. **Examples & Context**: Retain all illustrative examples and context
   provided in the video.
5. **No Summarization**: Do not summarize brief points; expand them for full
   understanding.
6. Pure Markdown format (no HTML, no table of contents).
7. English language output.
8. **Clean Start**: Start directly with the first header (e.g. # Video
   Title), no filler."""


def get_chunk_prompt(transcript_chunk: str) -> str:
    """Generate prompt for a transcript chunk."""
    return CHUNK_GENERATION_PROMPT.format(transcript_chunk=transcript_chunk)


def get_combine_prompt(chunk_notes: list[str]) -> str:
    """Generate prompt for combining chunk notes."""
    combined = "\n\n---\n\n".join(
        [f"## Segment {i + 1}\n\n{note}" for i, note in enumerate(chunk_notes)]
    )
    return COMBINE_CHUNKS_PROMPT.format(chunk_notes=combined)


def get_single_pass_prompt(transcript: str) -> str:
    """Generate prompt for single-pass generation."""
    return SINGLE_PASS_PROMPT.format(transcript=transcript)
