"""Tests for transcript fetching and processing."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from youtube_transcript_api._errors import (
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    VideoUnplayable,
)

from yt_study.core.youtube.metadata import PublicAccessRequiredError, VideoChapter
from yt_study.core.youtube.transcript import (
    TranscriptError,
    TranscriptSegment,
    VideoTranscript,
    YouTubeIPBlockError,
    _describe_video_unplayable,
    _fetch_sync,
    _raise_if_public_access_required,
    fetch_transcript,
    split_transcript_by_chapters,
)


class TestTranscriptHelpers:
    """Helper-level coverage for transcript utilities."""

    def test_video_transcript_to_text_joins_segment_text(self):
        """VideoTranscript.to_text should join segment text with spaces."""
        transcript = VideoTranscript(
            video_id="vid",
            segments=[
                TranscriptSegment(text="Hello", start=0.0, duration=1.0),
                TranscriptSegment(text="world", start=1.0, duration=1.0),
            ],
            language="English",
            language_code="en",
            is_generated=False,
        )

        assert transcript.to_text() == "Hello world"

    @pytest.mark.parametrize(
        ("error", "expected_message"),
        [
            (
                Exception("This video is members only"),
                "Members-only YouTube videos are not supported",
            ),
            (
                Exception("This video is age restricted"),
                "Age-restricted YouTube videos are not supported",
            ),
            (
                Exception("Please sign in to continue"),
                "Sign-in-only YouTube videos are not supported",
            ),
            (
                VideoUnplayable(
                    "vid",
                    None,
                    ["If the owner granted access, please", "sign in"],
                ),
                "Sign-in-only YouTube videos are not supported",
            ),
        ],
    )
    def test_raise_if_public_access_required_detects_restricted_access(
        self,
        error,
        expected_message,
    ):
        """Known sign-in-only restrictions should map to one clean user error."""
        with pytest.raises(PublicAccessRequiredError, match=expected_message):
            _raise_if_public_access_required(error)

    def test_raise_if_public_access_required_ignores_public_errors(self):
        """Non-access errors should be left untouched for normal handling."""
        _raise_if_public_access_required(Exception("captions missing"))

    def test_describe_video_unplayable_prefers_reason(self):
        """A populated reason should win over sub-reasons."""
        error = VideoUnplayable("vid", "Playback restricted", ["sign in"])
        assert _describe_video_unplayable(error) == "Playback restricted"

    def test_describe_video_unplayable_joins_sub_reasons(self):
        """Sub-reasons should be joined when no primary reason is present."""
        error = VideoUnplayable("vid", None, ["First detail", "Second detail"])
        assert _describe_video_unplayable(error) == "First detail; Second detail"

    def test_describe_video_unplayable_falls_back_to_generic_message(self):
        """An empty unplayable error should still produce a readable reason."""
        error = VideoUnplayable("vid", None, [])
        assert _describe_video_unplayable(error) == "video is unplayable"


class TestFetchTranscript:
    """Test fetch_transcript function."""

    @pytest.fixture
    def mock_transcript_api_instance(self, mocker):
        """Mock the YouTubeTranscriptApi class and its instance."""
        # Patch the class
        mock_cls = mocker.patch("yt_study.core.youtube.transcript.YouTubeTranscriptApi")
        # The instance returned by constructor
        mock_instance = mock_cls.return_value
        return mock_instance

    @pytest.mark.asyncio
    async def test_fetch_transcript_success_manual(self, mock_transcript_api_instance):
        """Test successful fetch of manual transcript."""
        # Setup mock for instance method .list()
        mock_list = MagicMock()
        mock_transcript_api_instance.list.return_value = mock_list

        mock_transcript_obj = MagicMock()
        mock_transcript_obj.language = "English"
        mock_transcript_obj.language_code = "en"
        mock_transcript_obj.is_generated = False
        mock_transcript_obj.fetch.return_value = [
            {"text": "Hello", "start": 0.0, "duration": 1.0},
            {"text": "World", "start": 1.0, "duration": 1.0},
        ]

        mock_list.find_manually_created_transcript.return_value = mock_transcript_obj

        # Execute
        result = await fetch_transcript("video123", ["en"])

        # Verify
        assert isinstance(result, VideoTranscript)
        assert result.video_id == "video123"
        assert len(result.segments) == 2
        assert result.segments[0].text == "Hello"
        assert result.language == "English"
        assert not result.is_generated

        # Verify instance call
        mock_transcript_api_instance.list.assert_called_once_with("video123")

    @pytest.mark.asyncio
    async def test_fetch_transcript_fallback_auto(self, mock_transcript_api_instance):
        """Test fallback to auto-generated transcript."""
        mock_list = MagicMock()
        mock_transcript_api_instance.list.return_value = mock_list

        # Manual raises error
        mock_list.find_manually_created_transcript.side_effect = NoTranscriptFound(
            "id", [], []
        )

        # Auto succeeds
        mock_auto = MagicMock()
        mock_auto.language = "English (Auto)"
        mock_auto.language_code = "en"
        mock_auto.is_generated = True
        mock_auto.fetch.return_value = [{"text": "Hi", "start": 0.0, "duration": 1.0}]

        mock_list.find_generated_transcript.return_value = mock_auto

        result = await fetch_transcript("video123")
        assert result.is_generated is True
        assert result.segments[0].text == "Hi"

    @pytest.mark.asyncio
    async def test_fetch_transcript_calls_on_request_callback(
        self, mock_transcript_api_instance
    ):
        """on_request callback should be awaited before the network attempt."""
        mock_list = MagicMock()
        mock_transcript_api_instance.list.return_value = mock_list

        mock_transcript_obj = MagicMock()
        mock_transcript_obj.language = "English"
        mock_transcript_obj.language_code = "en"
        mock_transcript_obj.is_generated = False
        mock_transcript_obj.fetch.return_value = [
            {"text": "Hello", "start": 0.0, "duration": 1.0}
        ]
        mock_list.find_manually_created_transcript.return_value = mock_transcript_obj

        on_request = AsyncMock()

        await fetch_transcript("video123", ["en"], on_request=on_request)

        on_request.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_transcript_fallback_translation(
        self, mock_transcript_api_instance
    ):
        """Test fallback to translation."""
        mock_list = MagicMock()
        mock_transcript_api_instance.list.return_value = mock_list

        # All finds fail
        mock_list.find_manually_created_transcript.side_effect = NoTranscriptFound(
            "id", [], []
        )
        mock_list.find_generated_transcript.side_effect = NoTranscriptFound(
            "id", [], []
        )

        # Iterator returns foreign transcript
        mock_foreign = MagicMock()
        mock_foreign.language_code = "fr"
        mock_foreign.is_translatable = True

        mock_translated = MagicMock()
        mock_translated.language = "English"
        mock_translated.language_code = "en"
        mock_translated.is_generated = False
        mock_translated.fetch.return_value = [
            {"text": "Hello", "start": 0.0, "duration": 1.0}
        ]

        mock_foreign.translate.return_value = mock_translated

        # Mock __iter__ to return list
        mock_list.__iter__.return_value = [mock_foreign]

        result = await fetch_transcript("video123", ["en"])

        mock_foreign.translate.assert_called_with("en")
        assert result.segments[0].text == "Hello"

    @pytest.mark.asyncio
    async def test_fetch_transcript_prefers_translatable_option_over_first_foreign(
        self, mock_transcript_api_instance
    ):
        """Later translatable transcripts should beat the first unusable foreign one."""
        mock_list = MagicMock()
        mock_transcript_api_instance.list.return_value = mock_list

        mock_list.find_manually_created_transcript.side_effect = NoTranscriptFound(
            "id", [], []
        )
        mock_list.find_generated_transcript.side_effect = NoTranscriptFound(
            "id", [], []
        )

        non_translatable = MagicMock()
        non_translatable.language = "German"
        non_translatable.language_code = "de"
        non_translatable.is_translatable = False
        non_translatable.fetch.return_value = [
            {"text": "Hallo", "start": 0.0, "duration": 1.0}
        ]

        translatable = MagicMock()
        translatable.language = "Spanish"
        translatable.language_code = "es"
        translatable.is_translatable = True

        translated = MagicMock()
        translated.language = "English"
        translated.language_code = "en"
        translated.is_generated = True
        translated.fetch.return_value = [
            {"text": "Hello", "start": 0.0, "duration": 1.0}
        ]
        translatable.translate.return_value = translated

        mock_list.__iter__.return_value = [non_translatable, translatable]

        result = await fetch_transcript("video123", ["en"])

        translatable.translate.assert_called_once_with("en")
        assert result.language_code == "en"
        assert result.segments[0].text == "Hello"

    @pytest.mark.asyncio
    async def test_fetch_transcript_unavailable(self, mock_transcript_api_instance):
        """Test fatal error when video is unavailable."""
        # Mock the instance method to raise error
        mock_transcript_api_instance.list.side_effect = VideoUnavailable("video123")

        with pytest.raises(TranscriptError, match="video is unavailable"):
            await fetch_transcript("video123")

    @pytest.mark.asyncio
    async def test_fetch_transcript_private_video_fails_without_retry(
        self, mock_transcript_api_instance
    ):
        """Private videos should surface a clean fatal error on the first attempt."""
        mock_transcript_api_instance.list.side_effect = VideoUnplayable(
            "video123",
            "This video is private",
            [
                "If the owner of this video has granted you access, please",
                "sign in",
                ".",
            ],
        )

        with pytest.raises(
            PublicAccessRequiredError,
            match="Private YouTube videos are not supported",
        ):
            await fetch_transcript("video123")

        mock_transcript_api_instance.list.assert_called_once_with("video123")

    @pytest.mark.asyncio
    async def test_fetch_transcript_retry_logic(self, mock_transcript_api_instance):
        """Test retry logic on transient errors."""
        # Setup Success Mock
        mock_list = MagicMock()
        mock_t = MagicMock()
        mock_t.fetch.return_value = []
        mock_t.language = "en"
        mock_t.language_code = "en"
        mock_t.is_generated = False

        mock_list.find_manually_created_transcript.return_value = mock_t

        # Configure side effect for list()
        mock_transcript_api_instance.list.side_effect = [
            Exception("Connection reset"),
            Exception("Timeout"),
            mock_list,
        ]

        result = await fetch_transcript("video123")
        assert isinstance(result, VideoTranscript)
        # Check call count
        assert mock_transcript_api_instance.list.call_count == 3

    @pytest.mark.asyncio
    async def test_fetch_transcript_uses_default_client(self, mocker):
        """Transcript fetch should construct YouTubeTranscriptApi plainly."""
        mock_cls = mocker.patch("yt_study.core.youtube.transcript.YouTubeTranscriptApi")
        mock_instance = mock_cls.return_value
        mock_list = MagicMock()
        mock_instance.list.return_value = mock_list

        mock_transcript_obj = MagicMock()
        mock_transcript_obj.language = "English"
        mock_transcript_obj.language_code = "en"
        mock_transcript_obj.is_generated = False
        mock_transcript_obj.fetch.return_value = [
            {"text": "Hello", "start": 0.0, "duration": 1.0}
        ]
        mock_list.find_manually_created_transcript.return_value = mock_transcript_obj

        await fetch_transcript("video123", ["en"])

        assert mock_cls.call_count >= 1
        assert mock_cls.call_args.kwargs == {}

    @pytest.mark.asyncio
    async def test_fetch_transcript_supports_object_segment_results(
        self, mock_transcript_api_instance
    ):
        """Object-style transcript snippets should be normalized too."""
        mock_list = MagicMock()
        mock_transcript_api_instance.list.return_value = mock_list

        mock_transcript_obj = MagicMock()
        mock_transcript_obj.language = "English"
        mock_transcript_obj.language_code = "en"
        mock_transcript_obj.is_generated = False
        mock_transcript_obj.fetch.return_value = [
            MagicMock(text="Hello", start=0.5, duration=1.25),
        ]
        mock_list.find_manually_created_transcript.return_value = mock_transcript_obj

        result = await fetch_transcript("video123", ["en"])

        assert result.segments[0].text == "Hello"
        assert result.segments[0].start == 0.5
        assert result.segments[0].duration == 1.25

    @pytest.mark.asyncio
    async def test_fetch_transcript_transcripts_disabled_is_fatal(
        self, mock_transcript_api_instance
    ):
        """Disabled transcripts should raise a clean non-retryable error."""
        mock_transcript_api_instance.list.side_effect = TranscriptsDisabled("video123")

        with pytest.raises(TranscriptError, match="Transcripts are disabled"):
            await fetch_transcript("video123")

        mock_transcript_api_instance.list.assert_called_once_with("video123")

    @pytest.mark.asyncio
    async def test_fetch_transcript_video_unplayable_uses_short_reason(
        self, mock_transcript_api_instance
    ):
        """Non-private unplayable videos should surface the condensed reason."""
        mock_transcript_api_instance.list.side_effect = VideoUnplayable(
            "video123",
            "Playback restricted",
            [],
        )

        with pytest.raises(
            TranscriptError,
            match="Could not fetch transcript: Playback restricted",
        ):
            await fetch_transcript("video123")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("error_cls", [RequestBlocked, IpBlocked])
    async def test_fetch_transcript_request_blocked_raises_ip_block(
        self, mock_transcript_api_instance, error_cls
    ):
        """Request-level blocking should map to the IP-block guidance error."""
        mock_transcript_api_instance.list.side_effect = error_cls("video123")

        with pytest.raises(YouTubeIPBlockError, match="blocking requests from your IP"):
            await fetch_transcript("video123")

    @pytest.mark.asyncio
    async def test_fetch_transcript_ip_block_message_in_generic_error(
        self, mock_transcript_api_instance
    ):
        """String-based IP block errors should also map to YouTubeIPBlockError."""
        mock_transcript_api_instance.list.side_effect = RuntimeError(
            "YouTube is blocking requests from your IP address"
        )

        with pytest.raises(YouTubeIPBlockError, match="blocking requests from your IP"):
            await fetch_transcript("video123")


class TestFetchSync:
    """Synchronous transcript strategy coverage."""

    @pytest.fixture
    def mock_transcript_api_instance(self, mocker):
        """Mock the YouTubeTranscriptApi class and its instance."""
        mock_cls = mocker.patch("yt_study.core.youtube.transcript.YouTubeTranscriptApi")
        return mock_cls.return_value

    def test_fetch_sync_uses_any_manual_transcript_when_preferred_missing(
        self, mock_transcript_api_instance
    ):
        """A manual transcript in another language should beat last-resort fallback."""
        mock_list = MagicMock()
        mock_transcript_api_instance.list.return_value = mock_list

        manual_other = MagicMock()
        manual_other.language = "French"
        manual_other.language_code = "fr"
        manual_other.fetch.return_value = [{"text": "Bonjour"}]

        mock_list.find_manually_created_transcript.side_effect = [
            NoTranscriptFound("vid", ["en"], []),
            manual_other,
        ]
        mock_list.find_generated_transcript.side_effect = NoTranscriptFound(
            "vid", ["en"], []
        )
        mock_list.__iter__.return_value = [manual_other]

        raw_transcript, transcript_meta, found_msg = _fetch_sync("vid", ["en"])

        assert raw_transcript == [{"text": "Bonjour"}]
        assert transcript_meta is manual_other
        assert found_msg == "Using manual transcript in French"

    def test_fetch_sync_prefers_matching_language_from_available_list(
        self, mock_transcript_api_instance
    ):
        """A preferred language from the available list should be used directly."""
        mock_list = MagicMock()
        mock_transcript_api_instance.list.return_value = mock_list

        preferred = MagicMock()
        preferred.language = "Hindi"
        preferred.language_code = "hi"
        preferred.fetch.return_value = [{"text": "Namaste"}]

        mock_list.find_manually_created_transcript.side_effect = [
            NoTranscriptFound("vid", ["hi"], []),
            NoTranscriptFound("vid", ["hi"], []),
        ]
        mock_list.find_generated_transcript.side_effect = NoTranscriptFound(
            "vid", ["hi"], []
        )
        mock_list.__iter__.return_value = [preferred]

        raw_transcript, transcript_meta, found_msg = _fetch_sync("vid", ["hi"])

        assert raw_transcript == [{"text": "Namaste"}]
        assert transcript_meta is preferred
        assert found_msg == "Using Hindi"

    def test_fetch_sync_uses_first_available_when_translation_unavailable(
        self, mock_transcript_api_instance
    ):
        """English fallback should use the first transcript when it cannot translate."""
        mock_list = MagicMock()
        mock_transcript_api_instance.list.return_value = mock_list

        fallback = MagicMock()
        fallback.language = "German"
        fallback.language_code = "de"
        fallback.is_translatable = False
        fallback.fetch.return_value = [{"text": "Hallo"}]

        mock_list.find_manually_created_transcript.side_effect = [
            NoTranscriptFound("vid", ["en"], []),
            NoTranscriptFound("vid", ["en"], []),
        ]
        mock_list.find_generated_transcript.side_effect = NoTranscriptFound(
            "vid", ["en"], []
        )
        mock_list.__iter__.return_value = [fallback]

        raw_transcript, transcript_meta, found_msg = _fetch_sync("vid", ["en"])

        assert raw_transcript == [{"text": "Hallo"}]
        assert transcript_meta is fallback
        assert found_msg == "Using German (translation not available)"

    def test_fetch_sync_uses_first_available_when_english_is_not_requested(
        self, mock_transcript_api_instance
    ):
        """Non-English requests should fall back to the first available transcript."""
        mock_list = MagicMock()
        mock_transcript_api_instance.list.return_value = mock_list

        fallback = MagicMock()
        fallback.language = "French"
        fallback.language_code = "fr"
        fallback.fetch.return_value = [{"text": "Bonjour"}]

        mock_list.find_manually_created_transcript.side_effect = [
            NoTranscriptFound("vid", ["es"], []),
            NoTranscriptFound("vid", ["es"], []),
        ]
        mock_list.find_generated_transcript.side_effect = NoTranscriptFound(
            "vid", ["es"], []
        )
        mock_list.__iter__.return_value = [fallback]

        raw_transcript, transcript_meta, found_msg = _fetch_sync("vid", ["es"])

        assert raw_transcript == [{"text": "Bonjour"}]
        assert transcript_meta is fallback
        assert found_msg == "Using French"

    def test_fetch_sync_raises_when_no_transcripts_are_available(
        self, mock_transcript_api_instance
    ):
        """An empty available-transcript list should re-raise NoTranscriptFound."""
        mock_list = MagicMock()
        mock_transcript_api_instance.list.return_value = mock_list

        mock_list.find_manually_created_transcript.side_effect = [
            NoTranscriptFound("vid", ["en"], []),
            NoTranscriptFound("vid", ["en"], []),
        ]
        mock_list.find_generated_transcript.side_effect = NoTranscriptFound(
            "vid", ["en"], []
        )
        mock_list.__iter__.return_value = []

        with pytest.raises(NoTranscriptFound):
            _fetch_sync("vid", ["en"])

    def test_fetch_sync_wraps_last_resort_errors(self, mock_transcript_api_instance):
        """Unexpected last-resort failures should be wrapped as TranscriptError."""
        mock_list = MagicMock()
        mock_transcript_api_instance.list.return_value = mock_list

        translatable = MagicMock()
        translatable.language = "Spanish"
        translatable.language_code = "es"
        translatable.is_translatable = True
        translatable.translate.side_effect = RuntimeError("translation boom")

        mock_list.find_manually_created_transcript.side_effect = [
            NoTranscriptFound("vid", ["en"], []),
            NoTranscriptFound("vid", ["en"], []),
        ]
        mock_list.find_generated_transcript.side_effect = NoTranscriptFound(
            "vid", ["en"], []
        )
        mock_list.__iter__.return_value = [translatable]

        with pytest.raises(TranscriptError, match="No usable transcript found"):
            _fetch_sync("vid", ["en"])


class TestSplitTranscript:
    """Test splitting transcript by chapters."""

    def test_split_transcript_simple(self):
        """Test basic split logic."""
        # Create mock transcript
        # 0-60s, 60-120s
        segments = [
            MagicMock(text="Part 1", start=10, duration=10),
            MagicMock(text="Part 1 End", start=50, duration=5),
            MagicMock(text="Part 2", start=70, duration=10),
            MagicMock(text="Part 2 End", start=110, duration=5),
        ]

        transcript = VideoTranscript(
            video_id="id",
            segments=segments,
            language="en",
            language_code="en",
            is_generated=False,
        )

        chapters = [
            VideoChapter(title="Chapter 1", start_seconds=0, end_seconds=60),
            VideoChapter(title="Chapter 2", start_seconds=60, end_seconds=None),
        ]

        result = split_transcript_by_chapters(transcript, chapters)

        assert len(result) == 2
        assert "Part 1" in result["Chapter 1"]
        assert "Part 1 End" in result["Chapter 1"]
        assert "Part 2" not in result["Chapter 1"]

        assert "Part 2" in result["Chapter 2"]
        assert "Part 2 End" in result["Chapter 2"]

    def test_split_transcript_skips_empty_chapters(self):
        """Chapters with no matching segments are omitted from the result."""
        segments = [
            MagicMock(text="Part 3", start=200, duration=10),
        ]

        transcript = VideoTranscript(
            video_id="id",
            segments=segments,
            language="en",
            language_code="en",
            is_generated=False,
        )

        chapters = [
            # This chapter has no segments in the 0-60s window
            VideoChapter(title="Empty Chapter", start_seconds=0, end_seconds=60),
            # This chapter captures the only segment
            VideoChapter(title="Real Chapter", start_seconds=180, end_seconds=None),
        ]

        result = split_transcript_by_chapters(transcript, chapters)

        assert "Empty Chapter" not in result
        assert "Real Chapter" in result
        assert "Part 3" in result["Real Chapter"]

    def test_split_transcript_disambiguates_duplicate_titles(self):
        """Duplicate chapter titles should preserve all chapter transcript slices."""
        segments = [
            MagicMock(text="First intro", start=10, duration=5),
            MagicMock(text="Second intro", start=70, duration=5),
        ]

        transcript = VideoTranscript(
            video_id="id",
            segments=segments,
            language="en",
            language_code="en",
            is_generated=False,
        )

        chapters = [
            VideoChapter(title="Intro", start_seconds=0, end_seconds=60),
            VideoChapter(title="Intro", start_seconds=60, end_seconds=None),
        ]

        result = split_transcript_by_chapters(transcript, chapters)

        assert result["Intro"] == "First intro"
        assert result["Intro (2)"] == "Second intro"

    def test_split_transcript_keeps_boundary_overlaps(self):
        """Segments spanning a boundary should remain in any chapter they overlap."""
        transcript = VideoTranscript(
            video_id="id",
            segments=[
                MagicMock(text="Intro tail", start=58, duration=5),
                MagicMock(text="Chapter two", start=61, duration=4),
            ],
            language="en",
            language_code="en",
            is_generated=False,
        )
        chapters = [
            VideoChapter(title="Intro", start_seconds=0, end_seconds=60),
            VideoChapter(title="Deep Dive", start_seconds=60, end_seconds=None),
        ]

        result = split_transcript_by_chapters(transcript, chapters)

        assert "Intro tail" in result["Intro"]
        assert "Intro tail" in result["Deep Dive"]
        assert "Chapter two" in result["Deep Dive"]
