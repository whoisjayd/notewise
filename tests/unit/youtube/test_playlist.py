"""Tests for playlist processing."""

import pytest

from notewise.errors import ExtractionError as ExtractorError
from notewise.errors import PlaylistError
from notewise.errors import VideoUnavailableError as PublicAccessRequiredError
from notewise.youtube.playlist import extract_playlist_videos


class TestPlaylistExtraction:
    """Test playlist video extraction."""

    async def test_extract_playlist_success(self, mock_extractor_client):
        """Extract video IDs from native playlist entries."""
        client = mock_extractor_client["playlist"].return_value
        client.playlist.return_value = {
            "entries": [
                {"id": "dQw4w9WgXcQ", "url": "https://youtube.com/watch?v=dQw4w9WgXcQ"},
                {"id": "J---aiyznGQ", "url": "https://youtube.com/watch?v=J---aiyznGQ"},
                {"id": "9bZkp7q19f0", "url": "https://youtube.com/watch?v=9bZkp7q19f0"},
            ]
        }

        video_ids = await extract_playlist_videos("pl123")

        assert len(video_ids) == 3
        assert video_ids == ["dQw4w9WgXcQ", "J---aiyznGQ", "9bZkp7q19f0"]

    async def test_extract_playlist_retry_success(self, mock_extractor_client):
        """Transient failures should retry and then succeed."""
        client = mock_extractor_client["playlist"].return_value
        client.playlist.side_effect = [
            ExtractorError("Network Error"),
            {
                "entries": [
                    {
                        "id": "dQw4w9WgXcQ",
                        "url": "https://youtube.com/watch?v=dQw4w9WgXcQ",
                    }
                ]
            },
        ]

        video_ids = await extract_playlist_videos("pl123")
        assert video_ids == ["dQw4w9WgXcQ"]
        assert client.playlist.call_count == 2

    async def test_extract_playlist_empty(self, mock_extractor_client):
        """Empty playlist payload should raise PlaylistError after retries."""
        client = mock_extractor_client["playlist"].return_value
        client.playlist.return_value = {"entries": []}

        with pytest.raises(PlaylistError, match="Could not access playlist"):
            await extract_playlist_videos("pl123")

        assert client.playlist.call_count == 3

    async def test_extract_private_playlist_fails_without_retry(
        self, mock_extractor_client
    ):
        """Private playlists should fail immediately with user-facing error."""
        client = mock_extractor_client["playlist"].return_value
        client.playlist.side_effect = ExtractorError(
            "This playlist is private. Please sign in"
        )

        with pytest.raises(
            PublicAccessRequiredError,
            match="cookie-file",
        ):
            await extract_playlist_videos("pl123")

        assert client.playlist.call_count == 1

    async def test_extract_signin_playlist_fails_without_retry(
        self, mock_extractor_client
    ):
        """Sign-in-only playlists should fail immediately with user-facing error."""
        client = mock_extractor_client["playlist"].return_value
        client.playlist.side_effect = ExtractorError(
            "Please sign in to view this playlist"
        )

        with pytest.raises(
            PublicAccessRequiredError,
            match="cookie-file",
        ):
            await extract_playlist_videos("pl123")

        assert client.playlist.call_count == 1

    async def test_extract_playlist_malformed_urls(self, mock_extractor_client):
        """Malformed entries should be skipped while valid IDs are kept."""
        client = mock_extractor_client["playlist"].return_value
        client.playlist.return_value = {
            "entries": [
                {"id": "dQw4w9WgXcQ", "url": "https://youtube.com/watch?v=dQw4w9WgXcQ"},
                {"url": "https://broken.com/video"},
                {"id": "J---aiyznGQ", "url": "https://youtube.com/watch?v=J---aiyznGQ"},
            ]
        }

        video_ids = await extract_playlist_videos("pl123")
        assert video_ids == ["dQw4w9WgXcQ", "J---aiyznGQ"]

    async def test_extract_playlist_rejects_path_traversal_entry_id(
        self, mock_extractor_client
    ):
        """A malicious/malformed entry `id` must not be trusted verbatim.

        `_extract_async` used to join `entry.get("id")` straight into a
        filesystem path (see `prepare_chapter_output_targets`) without
        validating it looks like a real 11-char YouTube video ID. A crafted
        `id` containing path-traversal components must be rejected and the
        video ID re-derived from the entry's `url` instead.
        """
        client = mock_extractor_client["playlist"].return_value
        client.playlist.return_value = {
            "entries": [
                {
                    "id": "../../etc/passwd",
                    "url": "https://youtube.com/watch?v=dQw4w9WgXcQ",
                },
                {
                    "id": "has/slash/oops",
                    "url": "https://broken.com/video",
                },
            ]
        }

        video_ids = await extract_playlist_videos("pl123")

        assert video_ids == ["dQw4w9WgXcQ"]
        assert all("/" not in video_id for video_id in video_ids)

    async def test_extract_async_logs_playlist_title_on_first_attempt(
        self, mock_extractor_client
    ):
        """_extract_async should log title when attempt is first and title exists."""
        from notewise.youtube.playlist import _extract_async

        client = mock_extractor_client["playlist"].return_value
        client.playlist.return_value = {
            "playlist": {"title": "My Playlist"},
            "entries": [
                {"id": "dQw4w9WgXcQ", "url": "https://youtube.com/watch?v=dQw4w9WgXcQ"}
            ],
        }

        result = await _extract_async("pl123", 0, None)

        assert result == ["dQw4w9WgXcQ"]
