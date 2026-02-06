"""Test telemetry shutdown functionality."""

from unittest.mock import patch

from yt_study.core.telemetry import Telemetry


def test_telemetry_shutdown_calls_posthog_flush():
    """Test that shutdown() calls posthog.flush() and posthog.shutdown()."""

    with (
        patch("yt_study.core.telemetry.posthog") as mock_posthog,
        patch("yt_study.core.telemetry.config") as mock_config,
    ):
        mock_config.telemetry_enabled = True
        mock_posthog.disabled = False

        telemetry = Telemetry()
        telemetry.shutdown()

        # Verify PostHog flush and shutdown were called
        mock_posthog.flush.assert_called_once()
        mock_posthog.shutdown.assert_called_once()


def test_telemetry_shutdown_skips_when_disabled():
    """Test that shutdown() does nothing when telemetry is disabled."""

    with (
        patch("yt_study.core.telemetry.posthog") as mock_posthog,
        patch("yt_study.core.telemetry.config") as mock_config,
    ):
        mock_config.telemetry_enabled = False

        telemetry = Telemetry()
        telemetry.shutdown()

        # Verify PostHog methods were NOT called
        mock_posthog.flush.assert_not_called()
        mock_posthog.shutdown.assert_not_called()


def test_telemetry_shutdown_handles_exceptions():
    """Test that shutdown() handles exceptions gracefully."""

    with (
        patch("yt_study.core.telemetry.posthog") as mock_posthog,
        patch("yt_study.core.telemetry.config") as mock_config,
    ):
        mock_config.telemetry_enabled = True
        mock_posthog.disabled = False
        mock_posthog.flush.side_effect = Exception("Network error")

        telemetry = Telemetry()
        # Should not raise an exception
        telemetry.shutdown()
