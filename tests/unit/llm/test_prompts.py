"""Tests for prompt quality guardrails."""

from notewise.llm.prompts import chapter_notes, quiz, study_notes


def test_study_note_prompts_ban_source_referential_phrasing():
    """Study-note prompts should prevent transcript/meta narration artifacts."""
    chunk_prompt = study_notes.get_chunk_prompt("example transcript")
    single_pass_prompt = study_notes.get_single_pass_prompt("example transcript")

    for prompt in (chunk_prompt, single_pass_prompt):
        assert "Do not mention the transcript" in prompt
        assert "as stated in the transcript" in prompt
        assert "as mentioned in the video" in prompt
        assert "should not need to open the" in prompt.lower()


def test_study_note_prompts_avoid_vague_marketing_labels():
    """Prompts should not encourage vague title text in generated notes."""
    rendered = "\n".join(
        [
            study_notes.get_system_prompt(),
            study_notes.get_chunk_prompt("example transcript"),
            study_notes.get_single_pass_prompt("example transcript"),
            chapter_notes.get_chapter_prompt("Intro", "example transcript"),
        ]
    ).lower()

    for vague_phrase in ("exam-ready", "complete study guide", "source material"):
        assert vague_phrase not in rendered


def test_study_note_prompts_limit_heading_noise():
    """Study-note prompts should keep Markdown useful without heading spam."""
    chunk_prompt = study_notes.get_chunk_prompt("example transcript")
    single_pass_prompt = study_notes.get_single_pass_prompt("example transcript")

    for prompt in (chunk_prompt, single_pass_prompt):
        assert "Use headings only when they improve navigation" in prompt
        assert "Do not create a new heading for every sentence" in prompt
        assert (
            "code fences must start and end at the beginning of a line"
            in prompt.lower()
        )


def test_chapter_prompts_use_polished_notes_style():
    """Chapter prompts should share the same clean study-note style."""
    prompt = chapter_notes.get_chapter_prompt("Intro", "example transcript")

    assert "Do not mention the transcript" in prompt
    assert "Use headings only when they improve navigation" in prompt
    assert "should not need to open the" in prompt.lower()
    assert "code fences must start and end at the beginning of a line" in prompt.lower()


def test_quiz_prompts_request_standalone_learning_artifacts():
    """Quiz prompts should produce useful study material without source chatter."""
    prompt = quiz.get_quiz_prompt("example transcript")
    combine_prompt = quiz.get_quiz_combine_prompt(["quiz section"])

    for rendered in (prompt, combine_prompt):
        assert "should not need to open the" in rendered.lower()
        assert "Do not mention the transcript" in rendered
        assert "as stated in the transcript" in rendered
