"""Telemetry module for tracking application usage and errors with PostHog."""

import contextlib
import json
import os
import platform
import re
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

import posthog
import structlog

from ..config import config


logger = structlog.get_logger(__name__)

# PostHog Public API Key (Standard OSS practice for telemetry)
POSTHOG_API_KEY = "phc_84al8IgA5g3ATbomr3VB7sDXsgdlp9gT3J9njqpbUj7"
POSTHOG_HOST = "https://us.i.posthog.com"

SENSITIVE_KEYS = {"api_key", "token", "password", "secret", "credential", "key"}
ALLOWLISTED_KEYS = {
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "temperature",
    "duration",
    "timestamp",
}


def redact_pii(data: Any) -> Any:
    """
    Redact personally identifiable information from data.

    Scrubs:
    - User home directory paths
    - Sensitive keys in dictionaries
    - Potential API keys in strings
    """
    # Skip redaction for metrics and numbers
    if isinstance(data, (int, float, bool)) or data is None:
        return data

    if isinstance(data, dict):
        return {
            k: (
                "<REDACTED>"
                if k.lower() not in ALLOWLISTED_KEYS
                and any(s in k.lower() for s in SENSITIVE_KEYS)
                and not isinstance(v, (int, float, bool))
                else redact_pii(v)
            )
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [redact_pii(v) for v in data]
    if isinstance(data, str):
        # Redact home directory
        try:
            home = str(Path.home())
            if home in data:
                data = data.replace(home, "<HOME>")
        except Exception:
            pass

        # Redact common Windows user path patterns
        data = re.sub(r"[a-zA-Z]:\\Users\\[^\\]+", r"<USER_PATH>", data)

        # Redact potential API keys (simple heuristic: long alphanumeric strings)
        # Only if they look like random tokens (not words)
        key_pattern = r"(?i)((?:key|token|api|auth)[-_\s]*[=:][-_\s]*)[a-zA-Z0-9]{20,}"
        data = re.sub(key_pattern, r"\1<REDACTED>", data)

    return data


class Telemetry:
    """
    Handles telemetry event logging for the application.

    Supports local logging and optional remote tracking via PostHog.
    """

    def __init__(self) -> None:
        self.telemetry_dir = Path.home() / ".yt-study" / "telemetry"
        self.events_file = self.telemetry_dir / "events.jsonl"
        self._ensure_dir()

        self.enabled = config.telemetry_enabled
        self.distinct_id = self._get_distinct_id()

        if self.enabled:
            posthog.api_key = POSTHOG_API_KEY
            posthog.host = POSTHOG_HOST
            # Enable automatic exception tracking for unhandled errors
            posthog.enable_exception_autocapture = True
            # Disable posthog's internal logger to avoid noise
            posthog.disabled = False
        else:
            posthog.disabled = True

    def _get_distinct_id(self) -> str:
        """Get or create a persistent distinct ID for this installation."""
        id_file = self.telemetry_dir / "id"
        if id_file.exists():
            return id_file.read_text().strip()

        import uuid

        new_id = str(uuid.uuid4())
        with contextlib.suppress(Exception):
            id_file.write_text(new_id)
        return new_id

    def _ensure_dir(self) -> None:
        """Ensure the telemetry directory exists."""
        try:
            self.telemetry_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            # Fallback to local directory if home is not writable
            self.telemetry_dir = Path.cwd() / ".telemetry"
            self.events_file = self.telemetry_dir / "events.jsonl"
            self.telemetry_dir.mkdir(parents=True, exist_ok=True)

    @property
    def is_enabled(self) -> bool:
        """Check if telemetry is enabled in config and environment."""
        if os.getenv("YT_STUDY_NO_TELEMETRY"):
            return False
        return config.telemetry_enabled

    def capture_event(
        self, name: str, properties: dict[str, Any] | None = None
    ) -> None:
        """Capture a telemetry event."""
        if not self.is_enabled:
            return

        # Ensure posthog is initialized (it might have been disabled in __init__)
        if posthog.disabled:
            posthog.api_key = POSTHOG_API_KEY
            posthog.host = POSTHOG_HOST
            posthog.disabled = False

        props = properties or {}
        props = redact_pii(props)

        # Add system info
        props.update(
            {
                "os": platform.system(),
                "os_release": platform.release(),
                "python_version": sys.version.split()[0],
                "app_version": self._get_app_version(),
            }
        )

        # Local log
        self._log_locally(name, props)

        # Remote log
        # We use keywords for all arguments to satisfy mypy's strictness
        # and accommodate potential variations in the posthog-python library.
        with contextlib.suppress(Exception):
            posthog.capture(distinct_id=self.distinct_id, event=name, properties=props)

    def capture_exception(
        self, exception: Exception, context: dict[str, Any] | None = None
    ) -> None:
        """Capture an exception event for PostHog Error Tracking."""
        if not self.is_enabled:
            return

        # Align with PostHog Error Tracking schema:
        # https://posthog.com/docs/errors-exceptions/manual-error-tracking
        error_data = {
            "$exception_type": type(exception).__name__,
            "$exception_message": str(exception),
            "$exception_stack_trace": "".join(
                traceback.format_exception(
                    type(exception), exception, exception.__traceback__
                )
            ),
        }
        if context:
            error_data.update(context)

        self.capture_event("$exception", error_data)

    def _get_app_version(self) -> str:
        try:
            from .. import __version__

            return __version__
        except ImportError:
            return "unknown"

    def _log_locally(self, event_type: str, data: dict[str, Any]) -> None:
        """Log a telemetry event to the local events file."""
        event = {
            "timestamp": datetime.now().isoformat(),
            "event": event_type,
            **data,
        }
        try:
            with self.events_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
        except Exception:
            pass

    def track_command(self, command_name: str) -> Any:
        """Decorator or context manager to track command execution."""

        class CommandTracker:
            def __init__(self, telemetry_inst: "Telemetry", name: str) -> None:
                self.telemetry = telemetry_inst
                self.name = name
                self.start_time = 0.0

            def __enter__(self) -> "CommandTracker":
                self.start_time = time.time()
                self.telemetry.capture_event("command_start", {"command": self.name})
                return self

            def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
                duration = time.time() - self.start_time
                if exc_type and exc_type is not SystemExit:
                    self.telemetry.capture_exception(
                        exc_val, {"command": self.name, "duration": duration}
                    )
                    self.telemetry.capture_event(
                        "command_fail",
                        {
                            "command": self.name,
                            "duration": duration,
                            "error": str(exc_val),
                        },
                    )
                elif exc_type is None:
                    self.telemetry.capture_event(
                        "command_success", {"command": self.name, "duration": duration}
                    )

        return CommandTracker(self, command_name)

    def get_stats(self) -> dict[str, Any]:
        """Retrieve telemetry statistics from local log."""
        stats: dict[str, Any] = {
            "total_commands": 0,
            "success_count": 0,
            "fail_count": 0,
            "commands": {},
        }

        if not self.events_file.exists():
            return stats

        try:
            with self.events_file.open(encoding="utf-8") as f:
                for line in f:
                    try:
                        event = json.loads(line)
                        cmd = event.get("command")
                        if not cmd:
                            continue

                        event_type = event.get("event")

                        if event_type == "command_start":
                            stats["total_commands"] += 1
                            if cmd not in stats["commands"]:
                                stats["commands"][cmd] = {
                                    "starts": 0,
                                    "successes": 0,
                                    "fails": 0,
                                }
                            stats["commands"][cmd]["starts"] += 1
                        elif event_type == "command_success":
                            stats["success_count"] += 1
                            if cmd in stats["commands"]:
                                stats["commands"][cmd]["successes"] += 1
                        elif event_type == "command_fail":
                            stats["fail_count"] += 1
                            if cmd in stats["commands"]:
                                stats["commands"][cmd]["fails"] += 1
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass

        return stats


# Global telemetry instance
telemetry = Telemetry()
