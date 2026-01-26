"""Test configuration and fixtures."""

import pytest


@pytest.fixture
def sample_video_id():
    """Sample YouTube video ID for testing."""
    return "dQw4w9WgXcQ"


@pytest.fixture
def sample_playlist_id():
    """Sample YouTube playlist ID for testing."""
    return "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
