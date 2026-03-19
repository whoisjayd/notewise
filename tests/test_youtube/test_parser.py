"""Tests for YouTube URL parser."""

import pytest

from yt_study.errors import ValidationError
from yt_study.infrastructure.youtube.parser import (
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

    def test_music_subdomain_watch_url(self):
        """Music YouTube watch URLs should still parse as valid YouTube hosts."""
        url = "https://music.youtube.com/watch?v=dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_non_youtube_host_with_video_param_rejected(self):
        """Host validation should reject arbitrary sites containing a video ID."""
        url = "https://example.com/watch?v=dQw4w9WgXcQ"
        assert extract_video_id(url) is None

    def test_extract_video_id_youtube_root_without_path_returns_none(self):
        """Test that the YouTube root URL without a path returns None."""
        assert extract_video_id("https://www.youtube.com") is None


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

    def test_extract_playlist_id_handles_parse_errors_gracefully(self, monkeypatch):
        """Test that extract_playlist_id handles parse errors gracefully."""

        def _boom(_: str):
            raise RuntimeError("bad")

        monkeypatch.setattr(
            "yt_study.infrastructure.youtube.parser._parse_supported_youtube_url",
            _boom,
        )
        assert (
            extract_playlist_id("https://www.youtube.com/playlist?list=PL123") is None
        )


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
        with pytest.raises(ValidationError, match="Invalid YouTube URL"):
            parse_youtube_url("https://example.com/video")

    def test_invalid_host_with_playlist_param(self):
        """Playlist IDs on non-YouTube hosts must not parse as YouTube playlists."""
        with pytest.raises(ValidationError, match="Invalid YouTube URL"):
            parse_youtube_url("https://example.com/?list=PLtest123")

    def test_free_form_text_with_video_param_rejected(self):
        """Free-form text containing v= should not be treated as a valid URL."""
        with pytest.raises(ValidationError, match="Invalid YouTube URL"):
            parse_youtube_url("not youtube but v=dQw4w9WgXcQ")

    def test_empty_url(self):
        """Test empty URL raises error."""
        with pytest.raises(ValidationError, match="URL must be a non-empty string"):
            parse_youtube_url("")

    def test_first_query_value_returns_none_for_missing_key(self):
        """Test that first_query_value returns None for a missing key."""
        from yt_study.infrastructure.youtube.parser import _first_query_value

        assert _first_query_value({}, "v") is None
