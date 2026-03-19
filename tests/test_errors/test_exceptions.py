"""Tests for the centralized exception hierarchy."""

import pytest

from yt_study.errors import (
    ConfigurationError,
    ExtractionError,
    IPBlockError,
    LLMError,
    LLMGenerationError,
    PersistenceError,
    PlaylistError,
    TranscriptUnavailableError,
    ValidationError,
    VideoUnavailableError,
    YouTubeError,
    YtStudyError,
    format_user_error,
    raise_if_video_unavailable,
)


class TestExceptionHierarchy:
    """All custom exceptions must descend from YtStudyError."""

    @pytest.mark.parametrize(
        "exc_class",
        [
            ConfigurationError,
            ValidationError,
            VideoUnavailableError,
            TranscriptUnavailableError,
            IPBlockError,
            PlaylistError,
            ExtractionError,
            LLMGenerationError,
            PersistenceError,
        ],
    )
    def test_all_are_yt_study_error_subclasses(self, exc_class):
        assert issubclass(exc_class, YtStudyError)

    def test_youtube_errors_are_youtube_error_subclasses(self):
        for cls in (
            VideoUnavailableError,
            TranscriptUnavailableError,
            IPBlockError,
            PlaylistError,
            ExtractionError,
        ):
            assert issubclass(cls, YouTubeError)

    def test_llm_generation_error_is_llm_error_subclass(self):
        assert issubclass(LLMGenerationError, LLMError)


class TestExceptionContext:
    """Exceptions carry structured context."""

    def test_context_dict_available(self):
        exc = TranscriptUnavailableError(
            "no track", video_id="abc123", languages=["en"]
        )
        assert exc.context["video_id"] == "abc123"
        assert exc.context["languages"] == ["en"]

    def test_context_dict_is_copy(self):
        exc = VideoUnavailableError("private", video_id="xyz")
        copy1 = exc.context
        copy2 = exc.context
        assert copy1 == copy2
        assert copy1 is not copy2  # returns a new dict each time

    def test_str_includes_context(self):
        exc = VideoUnavailableError("restricted", video_id="abc", reason="private")
        s = str(exc)
        assert "video_id='abc'" in s
        assert "reason='private'" in s

    def test_empty_context_str_is_clean(self):
        exc = YtStudyError("plain message")
        assert str(exc) == "plain message"


class TestRaiseIfVideoUnavailable:
    """raise_if_video_unavailable converts strings to VideoUnavailableError."""

    @pytest.mark.parametrize(
        "text,expected_reason",
        [
            ("This video is private", "private"),
            ("private video detected", "private"),
            ("This is a private video", "private"),
            ("private playlist content", "private"),
            ("members-only video", "members_only"),
            ("members only content", "members_only"),
            ("age restricted content", "age_restricted"),
            ("age-restricted video", "age_restricted"),
            ("sign in to confirm your age", "age_restricted"),
            ("please sign in to view", "login_required"),
            ("sign in required", "login_required"),
            ("requires login to view", "login_required"),
        ],
    )
    def test_raises_on_known_patterns(self, text, expected_reason):
        with pytest.raises(VideoUnavailableError) as exc_info:
            raise_if_video_unavailable(text)
        assert exc_info.value.context.get("reason") == expected_reason

    def test_does_not_raise_on_unrelated_error(self):
        # Should NOT raise for generic network errors
        raise_if_video_unavailable("network timeout occurred")
        raise_if_video_unavailable("connection reset by peer")
        raise_if_video_unavailable("rate limit exceeded")

    def test_video_id_propagated_to_exception(self):
        with pytest.raises(VideoUnavailableError) as exc_info:
            raise_if_video_unavailable("This video is private", video_id="abc123")
        assert exc_info.value.context.get("video_id") == "abc123"

    def test_none_video_id_is_allowed(self):
        with pytest.raises(VideoUnavailableError):
            raise_if_video_unavailable("This video is private", video_id=None)


class TestFormatUserError:
    """format_user_error converts exceptions to plain user strings."""

    def test_video_unavailable_stripped_of_context(self):
        exc = VideoUnavailableError("Private videos not supported.", reason="private")
        msg = format_user_error(exc)
        assert "Private videos not supported." in msg
        assert "reason=" not in msg  # context dict stripped

    def test_ip_block_message(self):
        msg = format_user_error(IPBlockError("blocked"))
        assert "blocking requests from this network" in msg.lower()

    def test_transcript_unavailable_message(self):
        msg = format_user_error(TranscriptUnavailableError("no track"))
        assert "transcript" in msg.lower()

    def test_timeout_message(self):
        msg = format_user_error(RuntimeError("connection timed out"))
        assert "timed out" in msg.lower() or "timeout" in msg.lower()

    def test_rate_limit_message(self):
        msg = format_user_error(Exception("429 too many requests"))
        assert "rate" in msg.lower() or "limit" in msg.lower()

    def test_unknown_error_fallback(self):
        msg = format_user_error(RuntimeError("something weird happened"))
        assert len(msg) > 0
        assert "session log" in msg.lower()
