"""Tests for video metadata extraction."""

import pytest

from yt_study.errors import (
    ExtractionError as ExtractorError,
)
from yt_study.errors import (
    PlaylistError,
)
from yt_study.errors import (
    VideoUnavailableError as PublicAccessRequiredError,
)
from yt_study.errors import (
    raise_if_video_unavailable as _raise_if_public_access_required,
)
from yt_study.youtube.metadata import (
    _check_playlist_availability as _raise_if_playlist_data_requires_public_access,
)
from yt_study.youtube.metadata import (
    _check_video_availability as _raise_if_video_data_requires_public_access,
)
from yt_study.youtube.metadata import (
    get_playlist_info,
    get_video_metadata,
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
    async def test_get_video_metadata_uses_video_id_when_title_missing(
        self, mock_extractor_client
    ):
        client = mock_extractor_client["metadata"].return_value
        client.video_metadata_full.return_value = {
            "title": "",
            "duration": None,
            "availability": "public",
            "chapters": [],
        }

        metadata = await get_video_metadata("video123")

        assert metadata.title == "video123"
        assert metadata.duration == 0
        assert metadata.chapters == []

    @pytest.mark.asyncio
    async def test_get_video_metadata_private_video_raises_clear_error(
        self, mock_extractor_client
    ):
        """Private videos should raise user-facing access errors."""
        client = mock_extractor_client["metadata"].return_value
        client.video_metadata_full.return_value = {
            "title": "Private",
            "duration": 120,
            "availability": "private",
            "chapters": [],
        }

        with pytest.raises(
            PublicAccessRequiredError,
            match="cookie-file",
        ):
            await get_video_metadata("video123")

    @pytest.mark.asyncio
    async def test_get_video_metadata_unavailable_video_raises_invalid_style_error(
        self, mock_extractor_client
    ):
        """Unavailable videos should suggest invalid/unavailable instead of sign-in."""
        client = mock_extractor_client["metadata"].return_value
        client.video_metadata_full.return_value = {
            "title": "Unavailable",
            "duration": 0,
            "availability": "unavailable",
            "chapters": [],
        }

        with pytest.raises(
            PublicAccessRequiredError,
            match="isn't available",
        ):
            await get_video_metadata("video123")

    @pytest.mark.asyncio
    async def test_get_video_metadata_extractor_error_propagates(
        self, mock_extractor_client
    ):
        client = mock_extractor_client["metadata"].return_value
        client.video_metadata_full.side_effect = ExtractorError("network issue")

        with pytest.raises(ExtractorError, match="network issue"):
            await get_video_metadata("video123")

    @pytest.mark.asyncio
    async def test_get_video_metadata_wraps_generic_error(self, mock_extractor_client):
        client = mock_extractor_client["metadata"].return_value
        client.video_metadata_full.side_effect = RuntimeError("boom")

        with pytest.raises(
            ExtractorError,
            match="Failed to fetch metadata for video123: boom",
        ):
            await get_video_metadata("video123")


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
        """Extractor failures should surface as actionable playlist errors."""
        client = mock_extractor_client["metadata"].return_value
        client.metadata.side_effect = ExtractorError("Access Denied")

        with pytest.raises(PlaylistError, match="Could not access playlist pl123"):
            await get_playlist_info("pl123")

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
            match="cookie-file",
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
