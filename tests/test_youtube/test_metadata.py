"""Tests for video metadata extraction."""

from unittest.mock import MagicMock, PropertyMock

from yt_study.youtube.metadata import (
    get_playlist_info,
    get_video_chapters,
    get_video_duration,
    get_video_title,
)


class TestVideoMetadata:
    """Test video metadata extraction functions."""

    def test_get_video_chapters_success(self, mock_pytube):
        """Test successful chapter extraction."""
        mock_yt_cls, _ = mock_pytube
        mock_yt_instance = mock_yt_cls.return_value

        # Mock chapters as objects
        chap1 = MagicMock()
        chap1.title = "Intro"
        chap1.start_seconds = 0

        chap2 = MagicMock()
        chap2.title = "Middle"
        chap2.start_seconds = 60

        # Configure the chapters property
        type(mock_yt_instance).chapters = PropertyMock(return_value=[chap1, chap2])

        chapters = get_video_chapters("video123")

        assert len(chapters) == 2
        assert chapters[0].title == "Intro"
        assert chapters[0].end_seconds == 60

    def test_get_video_chapters_dict_format(self, mock_pytube):
        """Test chapter extraction when returned as dicts."""
        mock_yt_cls, _ = mock_pytube
        mock_yt_instance = mock_yt_cls.return_value

        chapters_data = [
            {"title": "Start", "start_seconds": 0},
            {"title": "End", "start_seconds": 100},
        ]
        type(mock_yt_instance).chapters = PropertyMock(return_value=chapters_data)

        chapters = get_video_chapters("video123")

        assert len(chapters) == 2
        assert chapters[0].title == "Start"

    def test_get_video_chapters_none(self, mock_pytube):
        """Test when no chapters are available."""
        mock_yt_cls, _ = mock_pytube
        mock_yt_instance = mock_yt_cls.return_value
        type(mock_yt_instance).chapters = PropertyMock(return_value=None)

        chapters = get_video_chapters("video123")
        assert chapters == []

    def test_get_video_chapters_error(self, mock_pytube):
        """Test error handling during chapter extraction."""
        mock_yt_cls, _ = mock_pytube
        mock_yt_instance = mock_yt_cls.return_value
        type(mock_yt_instance).chapters = PropertyMock(
            side_effect=Exception("API Error")
        )

        chapters = get_video_chapters("video123")
        assert chapters == []

    def test_get_video_title_success(self, mock_pytube):
        """Test successful title extraction."""
        mock_yt_cls, _ = mock_pytube
        mock_yt_instance = mock_yt_cls.return_value
        type(mock_yt_instance).title = PropertyMock(return_value="Awesome Video")

        title = get_video_title("video123")
        assert title == "Awesome Video"

    def test_get_video_title_failure(self, mock_pytube):
        """Test title extraction failure falls back to ID."""
        mock_yt_cls, _ = mock_pytube
        mock_yt_instance = mock_yt_cls.return_value
        type(mock_yt_instance).title = PropertyMock(side_effect=Exception("Net Error"))

        title = get_video_title("video123")
        assert title == "video123"

    def test_get_video_duration_success(self, mock_pytube):
        """Test successful duration extraction."""
        mock_yt_cls, _ = mock_pytube
        mock_yt_instance = mock_yt_cls.return_value
        type(mock_yt_instance).length = PropertyMock(return_value=120)

        duration = get_video_duration("video123")
        assert duration == 120

    def test_get_video_duration_failure(self, mock_pytube):
        """Test duration extraction failure returns 0."""
        mock_yt_cls, _ = mock_pytube
        mock_yt_instance = mock_yt_cls.return_value
        type(mock_yt_instance).length = PropertyMock(side_effect=Exception("Error"))

        duration = get_video_duration("video123")
        assert duration == 0


class TestPlaylistMetadata:
    """Test playlist metadata extraction."""

    def test_get_playlist_info_success(self, mock_pytube):
        """Test successful playlist info extraction."""
        _, mock_pl_cls = mock_pytube
        mock_pl_instance = mock_pl_cls.return_value

        # Note: metadata.py accesses .title property
        type(mock_pl_instance).title = PropertyMock(return_value="My Course")
        # And video_urls property which returns iterator/list
        type(mock_pl_instance).video_urls = PropertyMock(
            return_value=["url1", "url2", "url3"]
        )

        title, count = get_playlist_info("pl123")

        assert title == "My Course"
        assert count == 3

    def test_get_playlist_info_failure(self, mock_pytube):
        """Test failure handling for playlist info."""
        _, mock_pl_cls = mock_pytube

        # Simulate constructor failure or property access failure
        # metadata.py: playlist = Playlist(url) -> could fail
        mock_pl_cls.side_effect = Exception("Access Denied")

        title, count = get_playlist_info("pl123")

        assert title == "playlist_pl123"
        assert count == 0
