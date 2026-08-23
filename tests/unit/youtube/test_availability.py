"""Tests for shared YouTube metadata availability checks."""

import pytest

from notewise.errors import VideoUnavailableError
from notewise.youtube._availability import (
    raise_for_playlist_availability,
    raise_for_video_availability,
)


class TestVideoAvailability:
    """Test video availability error raising."""

    @pytest.mark.parametrize(
        ("availability", "reason"),
        [
            ("private", "private"),
            ("login_required", "login_required"),
            ("unavailable", "unavailable"),
            ("age_restricted", "age_restricted"),
        ],
    )
    def test_raises_for_restricted_availability(self, availability, reason):
        """Each restricted video availability state raises with its reason."""
        with pytest.raises(VideoUnavailableError) as excinfo:
            raise_for_video_availability({"availability": availability})
        assert excinfo.value.context["reason"] == reason

    @pytest.mark.parametrize(
        "availability", ["PRIVATE", "Login_Required", "UNAVAILABLE"]
    )
    def test_matching_is_case_insensitive(self, availability):
        """Uppercase or mixed-case restricted states still raise."""
        with pytest.raises(VideoUnavailableError):
            raise_for_video_availability({"availability": availability})

    @pytest.mark.parametrize(
        "availability", ["public", "unlisted", "", None, "needs_login"]
    )
    def test_passes_for_available_or_unknown_states(self, availability):
        """Public/unlisted/unknown/empty availability values never raise."""
        data = {} if availability is None else {"availability": availability}
        raise_for_video_availability(data)

    def test_missing_availability_key_passes(self):
        """A payload without an availability key is treated as available."""
        raise_for_video_availability({"title": "Some Video"})

    def test_none_availability_value_passes(self):
        """An explicit None availability value falls back to no restriction."""
        raise_for_video_availability({"availability": None})


class TestPlaylistAvailability:
    """Test playlist availability error raising."""

    @pytest.mark.parametrize(
        ("availability", "reason"),
        [
            ("private", "private"),
            ("unavailable", "unavailable"),
        ],
    )
    def test_raises_for_restricted_availability(self, availability, reason):
        """Each restricted playlist availability state raises with its reason."""
        with pytest.raises(VideoUnavailableError) as excinfo:
            raise_for_playlist_availability({"availability": availability})
        assert excinfo.value.context["reason"] == reason

    def test_login_required_does_not_raise(self):
        """Playlists do not treat login_required as a hard failure."""
        raise_for_playlist_availability({"availability": "login_required"})

    def test_age_restricted_does_not_raise(self):
        """Playlists do not treat age_restricted as a hard failure."""
        raise_for_playlist_availability({"availability": "age_restricted"})

    def test_available_state_passes(self):
        """Public playlist availability never raises."""
        raise_for_playlist_availability({"availability": "public"})

    def test_missing_availability_key_passes(self):
        """A payload without an availability key is treated as available."""
        raise_for_playlist_availability({"title": "Some Playlist"})

    def test_error_message_mentions_playlist(self):
        """Raised errors describe the artifact as a playlist, not a video."""
        with pytest.raises(VideoUnavailableError) as excinfo:
            raise_for_playlist_availability({"availability": "private"})
        assert "playlist" in str(excinfo.value).lower()

    def test_error_message_mentions_video(self):
        """Raised errors describe the artifact as a video for video checks."""
        with pytest.raises(VideoUnavailableError) as excinfo:
            raise_for_video_availability({"availability": "age_restricted"})
        assert "video" in str(excinfo.value).lower()
