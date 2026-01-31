"""Tests for YouTube URL parser."""

import pytest

from yt_study.youtube.parser import (
    extract_playlist_id,
    extract_video_id,
    parse_youtube_url,
)


class TestVideoIDExtraction:
    """Test video ID extraction from various URL formats."""

    def test_standard_watch_url(self):
        """Test standard watch URL format."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_short_url(self):
        """Test short youtu.be URL format."""
        url = "https://youtu.be/dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_embed_url(self):
        """Test embed URL format."""
        url = "https://www.youtube.com/embed/dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_url_with_extra_params(self):
        """Test URL with additional query parameters."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s"
        assert extract_video_id(url) == "dQw4w9WgXcQ"


class TestPlaylistIDExtraction:
    """Test playlist ID extraction."""

    def test_playlist_url(self):
        """Test playlist URL format."""
        url = "https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
        assert extract_playlist_id(url) == "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"

    def test_watch_url_with_playlist(self):
        """Test watch URL with playlist parameter."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLtest123"
        assert extract_playlist_id(url) == "PLtest123"

    def test_no_playlist(self):
        """Test URL without playlist."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert extract_playlist_id(url) is None


class TestURLParsing:
    """Test URL parsing logic."""

    def test_video_url(self):
        """Test parsing video URL."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        parsed = parse_youtube_url(url)
        assert parsed.url_type == "video"
        assert parsed.video_id == "dQw4w9WgXcQ"
        assert parsed.playlist_id is None

    def test_playlist_url(self):
        """Test parsing playlist URL."""
        url = "https://www.youtube.com/playlist?list=PLtest123"
        parsed = parse_youtube_url(url)
        assert parsed.url_type == "playlist"
        assert parsed.playlist_id == "PLtest123"

    def test_invalid_url(self):
        """Test invalid URL raises error."""
        with pytest.raises(ValueError, match="Invalid YouTube URL"):
            parse_youtube_url("https://example.com/video")

    def test_empty_url(self):
        """Test empty URL raises error."""
        with pytest.raises(ValueError, match="URL must be a non-empty string"):
            parse_youtube_url("")
