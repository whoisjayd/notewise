"""Tests for playlist processing."""

from unittest.mock import MagicMock, PropertyMock

import pytest

from yt_study.core.youtube.playlist import PlaylistError, extract_playlist_videos


class TestPlaylistExtraction:
    """Test playlist video extraction."""

    @pytest.mark.asyncio
    async def test_extract_playlist_success(self, mock_pytube):
        """Test successful extraction of video IDs."""
        _, mock_pl_cls = mock_pytube
        mock_pl = mock_pl_cls.return_value

        # Use PropertyMock for video_urls since it's a property
        type(mock_pl).video_urls = PropertyMock(
            return_value=[
                "https://youtube.com/watch?v=vid1",
                "https://youtube.com/watch?v=vid2&list=pl1",
                "https://youtube.com/watch?v=vid3",
            ]
        )

        video_ids = await extract_playlist_videos("pl123")

        assert len(video_ids) == 3
        assert video_ids == ["vid1", "vid2", "vid3"]

    @pytest.mark.asyncio
    async def test_extract_playlist_retry_success(self, mock_pytube):
        """Test retry logic eventually succeeds."""
        _, mock_pl_cls = mock_pytube

        # We want:
        # Attempt 1 -> Mock that raises Exception on property access
        # Attempt 2 -> Mock that succeeds

        mock_fail = MagicMock()
        type(mock_fail).video_urls = PropertyMock(
            side_effect=Exception("Network Error")
        )

        mock_success = MagicMock()
        type(mock_success).video_urls = PropertyMock(
            return_value=["https://youtube.com/watch?v=vid1"]
        )

        # side_effect on the constructor (mock_pl_cls)
        mock_pl_cls.side_effect = [mock_fail, mock_success]

        video_ids = await extract_playlist_videos("pl123")
        assert video_ids == ["vid1"]
        assert mock_pl_cls.call_count == 2

    @pytest.mark.asyncio
    async def test_extract_playlist_empty(self, mock_pytube):
        """Test empty playlist raises error."""
        _, mock_pl_cls = mock_pytube
        mock_pl = mock_pl_cls.return_value

        type(mock_pl).video_urls = PropertyMock(return_value=[])

        # Should retry 3 times then fail
        with pytest.raises(PlaylistError, match="Could not access playlist"):
            await extract_playlist_videos("pl123")

        assert mock_pl_cls.call_count == 3

    @pytest.mark.asyncio
    async def test_extract_playlist_malformed_urls(self, mock_pytube):
        """Test skipping malformed URLs."""
        _, mock_pl_cls = mock_pytube
        mock_pl = mock_pl_cls.return_value

        type(mock_pl).video_urls = PropertyMock(
            return_value=[
                "https://youtube.com/watch?v=vid1",
                "https://broken.com/video",  # Should be skipped
                "https://youtube.com/watch?v=vid2",
            ]
        )

        video_ids = await extract_playlist_videos("pl123")
        assert video_ids == ["vid1", "vid2"]

    @pytest.mark.asyncio
    async def test_extract_playlist_forwards_oauth_kwargs(self, mock_pytube):
        """OAuth options should be forwarded into Playlist constructor."""
        _, mock_pl_cls = mock_pytube
        mock_pl = mock_pl_cls.return_value
        type(mock_pl).video_urls = PropertyMock(
            return_value=["https://youtube.com/watch?v=vid1"]
        )

        video_ids = await extract_playlist_videos(
            "pl123",
            use_oauth=True,
            token_file="token.json",
            allow_oauth_cache=False,
        )

        assert video_ids == ["vid1"]
        mock_pl_cls.assert_called_once_with(
            "https://www.youtube.com/playlist?list=pl123",
            use_oauth=True,
            allow_oauth_cache=False,
            token_file="token.json",
        )

    @pytest.mark.asyncio
    async def test_extract_playlist_clears_stale_oauth_token_once(
        self, mock_pytube, tmp_path
    ):
        """Stale token cache should be removed and retried once."""
        _, mock_pl_cls = mock_pytube
        mock_pl = MagicMock()
        type(mock_pl).video_urls = PropertyMock(
            return_value=["https://youtube.com/watch?v=vid1"]
        )

        token_file = tmp_path / "token.json"
        token_file.write_text("{}", encoding="utf-8")

        mock_pl_cls.side_effect = [KeyError("access_token"), mock_pl]

        video_ids = await extract_playlist_videos(
            "pl123",
            use_oauth=True,
            token_file=str(token_file),
            allow_oauth_cache=True,
        )

        assert video_ids == ["vid1"]
        assert mock_pl_cls.call_count == 2
        assert not token_file.exists()
