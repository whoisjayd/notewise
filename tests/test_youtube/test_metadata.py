"""Tests for video metadata extraction."""

import pytest

from yt_study.errors import ExtractionError as ExtractorError
from yt_study.errors import (
    VideoUnavailableError as PublicAccessRequiredError,
)
from yt_study.errors import (
    raise_if_video_unavailable as _raise_if_public_access_required,
)
from yt_study.infrastructure.youtube.metadata import (
    _check_playlist_availability as _raise_if_playlist_data_requires_public_access,
)
from yt_study.infrastructure.youtube.metadata import (
    _check_video_availability as _raise_if_video_data_requires_public_access,
)
from yt_study.infrastructure.youtube.metadata import (
    get_playlist_info,
    get_video_chapters,
    get_video_duration,
    get_video_metadata,
    get_video_title,
)


class TestVideoMetadata:
    """Test video metadata extraction functions."""

    @pytest.mark.asyncio
    async def test_get_video_metadata_success(self, mock_extractor_client):
        """Single-call metadata path should map chapters and core fields."""
        client = mock_extractor_client["metadata"].return_value
        client.video_metadata_full.return_value = {
            "title": "Awesome Video",
            "duration": 125,
            "availability": "public",
            "chapters": [
                {"title": "Intro", "start_time": 0, "end_time": 60},
                {"title": "Deep Dive", "start_time": 60, "end_time": 125},
            ],
        }

        metadata = await get_video_metadata("video123")

        client.video_metadata_full.assert_awaited_once_with(
            "https://www.youtube.com/watch?v=video123"
        )
        assert metadata.video_id == "video123"
        assert metadata.title == "Awesome Video"
        assert metadata.duration == 125
        assert [chapter.title for chapter in metadata.chapters] == [
            "Intro",
            "Deep Dive",
        ]

    @pytest.mark.asyncio
    async def test_get_video_chapters_success(self, mock_extractor_client):
        """Chapter payload should map to VideoChapter models."""
        client = mock_extractor_client["metadata"].return_value
        client.chapters.return_value = {
            "chapters": [
                {"title": "Intro", "start_time": 0, "end_time": 60},
                {"title": "Middle", "start_time": 60, "end_time": 120},
            ]
        }

        chapters = await get_video_chapters("video123")

        assert len(chapters) == 2
        assert chapters[0].title == "Intro"
        assert chapters[0].end_seconds == 60

    @pytest.mark.asyncio
    async def test_get_video_chapters_none(self, mock_extractor_client):
        """Missing chapters should return an empty list."""
        client = mock_extractor_client["metadata"].return_value
        client.chapters.return_value = {"chapters": []}

        chapters = await get_video_chapters("video123")
        assert chapters == []

    @pytest.mark.asyncio
    async def test_get_video_chapters_extractor_error_returns_empty(
        self, mock_extractor_client
    ):
        client = mock_extractor_client["metadata"].return_value
        client.chapters.side_effect = ExtractorError("network issue")

        assert await get_video_chapters("video123") == []

    @pytest.mark.asyncio
    async def test_get_video_chapters_generic_error_returns_empty(
        self, mock_extractor_client
    ):
        client = mock_extractor_client["metadata"].return_value
        client.chapters.side_effect = RuntimeError("boom")

        assert await get_video_chapters("video123") == []

    @pytest.mark.asyncio
    async def test_get_video_title_success(self, mock_extractor_client):
        """Title should be returned when present."""
        client = mock_extractor_client["metadata"].return_value
        client.metadata.return_value = {
            "title": "Awesome Video",
            "data": {"availability": "public", "title": "Awesome Video"},
        }

        title = await get_video_title("video123")
        assert title == "Awesome Video"

    @pytest.mark.asyncio
    async def test_get_video_title_failure(self, mock_extractor_client):
        """Title extraction failure should fall back to the ID."""
        client = mock_extractor_client["metadata"].return_value
        client.metadata.side_effect = ExtractorError("network error")

        title = await get_video_title("video123")
        assert title == "video123"

    @pytest.mark.asyncio
    async def test_get_video_title_empty_title_falls_back_to_video_id(
        self, mock_extractor_client
    ):
        client = mock_extractor_client["metadata"].return_value
        client.metadata.return_value = {"data": {"availability": "public", "title": ""}}

        assert await get_video_title("video123") == "video123"

    @pytest.mark.asyncio
    async def test_get_video_title_generic_error_falls_back(
        self, mock_extractor_client
    ):
        client = mock_extractor_client["metadata"].return_value
        client.metadata.side_effect = RuntimeError("boom")

        assert await get_video_title("video123") == "video123"

    @pytest.mark.asyncio
    async def test_get_video_duration_success(self, mock_extractor_client):
        """Duration should be read from metadata payload."""
        client = mock_extractor_client["metadata"].return_value
        client.metadata.return_value = {
            "data": {"availability": "public", "duration": 120}
        }

        duration = await get_video_duration("video123")
        assert duration == 120

    @pytest.mark.asyncio
    async def test_get_video_duration_failure(self, mock_extractor_client):
        """Duration failures should return 0."""
        client = mock_extractor_client["metadata"].return_value
        client.metadata.side_effect = ExtractorError("request failed")

        duration = await get_video_duration("video123")
        assert duration == 0

    @pytest.mark.asyncio
    async def test_get_video_duration_none_returns_zero(self, mock_extractor_client):
        client = mock_extractor_client["metadata"].return_value
        client.metadata.return_value = {
            "data": {"availability": "public", "duration": None}
        }

        assert await get_video_duration("video123") == 0

    @pytest.mark.asyncio
    async def test_get_video_duration_generic_error_returns_zero(
        self, mock_extractor_client
    ):
        client = mock_extractor_client["metadata"].return_value
        client.metadata.side_effect = RuntimeError("boom")

        assert await get_video_duration("video123") == 0

    @pytest.mark.asyncio
    async def test_get_video_duration_private_video_raises_clear_error(
        self, mock_extractor_client
    ):
        """Private videos should raise user-facing access errors."""
        client = mock_extractor_client["metadata"].return_value
        client.metadata.return_value = {
            "data": {"availability": "private", "duration": 120}
        }

        with pytest.raises(
            PublicAccessRequiredError,
            match="Make the video unlisted or public to process it",
        ):
            await get_video_duration("video123")


class TestPlaylistMetadata:
    """Test playlist metadata extraction."""

    @pytest.mark.asyncio
    async def test_get_playlist_info_success(self, mock_extractor_client):
        """Playlist title and count should be returned when present."""
        client = mock_extractor_client["metadata"].return_value
        client.metadata.return_value = {
            "title": "My Course",
            "data": {"availability": "public", "playlist_count": 3},
        }

        title, count = await get_playlist_info("pl123")

        assert title == "My Course"
        assert count == 3

    @pytest.mark.asyncio
    async def test_get_playlist_info_failure(self, mock_extractor_client):
        """Playlist failures should use fallback title and count."""
        client = mock_extractor_client["metadata"].return_value
        client.metadata.side_effect = ExtractorError("Access Denied")

        title, count = await get_playlist_info("pl123")

        assert title == "playlist_pl123"
        assert count == 0

    @pytest.mark.asyncio
    async def test_get_playlist_info_private_playlist_raises(
        self, mock_extractor_client
    ):
        """Private playlists should be rejected with a clear message."""
        client = mock_extractor_client["metadata"].return_value
        client.metadata.return_value = {
            "title": "Private playlist",
            "data": {"availability": "private", "playlist_count": 1},
        }

        with pytest.raises(
            PublicAccessRequiredError,
            match="Make the playlist unlisted or public to process it",
        ):
            await get_playlist_info("pl123")


class TestMetadataAccessHelpers:
    @pytest.mark.parametrize(
        "availability", ["private", "login_required", "unavailable", "age_restricted"]
    )
    def test_video_access_helper_raises_for_restricted_status(self, availability):
        with pytest.raises(PublicAccessRequiredError):
            _raise_if_video_data_requires_public_access({"availability": availability})

    def test_video_access_helper_allows_public(self):
        _raise_if_video_data_requires_public_access({"availability": "public"})

    def test_playlist_access_helper_private_raises(self):
        with pytest.raises(PublicAccessRequiredError):
            _raise_if_playlist_data_requires_public_access({"availability": "private"})

    def test_playlist_access_helper_non_private_passes(self):
        _raise_if_playlist_data_requires_public_access({"availability": "public"})

    @pytest.mark.parametrize(
        "message",
        [
            "this is a private video",
            "members only",
            "age restricted",
            "requires login to view",
        ],
    )
    def test_raise_if_public_access_required_detects_known_messages(self, message):
        with pytest.raises(PublicAccessRequiredError):
            _raise_if_public_access_required(message)

    def test_raise_if_public_access_required_ignores_unknown(self):
        _raise_if_public_access_required("random network error")
