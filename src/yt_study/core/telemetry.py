"""Telemetry module for tracking application usage and errors."""

import json
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any


class Telemetry:
    """
    Handles telemetry event logging for the application.

    Tracks command execution, duration, and errors.
    """

    def __init__(self) -> None:
        self.telemetry_dir = Path.home() / ".yt-study" / "telemetry"
        self.events_file = self.telemetry_dir / "events.jsonl"
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Ensure the telemetry directory exists."""
        try:
            self.telemetry_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            # Fallback to local directory if home is not writable
            self.telemetry_dir = Path.cwd() / ".telemetry"
            self.events_file = self.telemetry_dir / "events.jsonl"
            self.telemetry_dir.mkdir(parents=True, exist_ok=True)

    def log_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Log a telemetry event to the local events file."""
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            **data,
        }
        try:
            with self.events_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
        except Exception:
            # Silently fail for telemetry logging to avoid interrupting main flow
            pass

    def track_command(self, command_name: str) -> Any:
        """Decorator or context manager to track command execution."""

        class CommandTracker:
            def __init__(self, telemetry: "Telemetry", name: str) -> None:
                self.telemetry = telemetry
                self.name = name
                self.start_time = 0.0

            def __enter__(self) -> "CommandTracker":
                self.start_time = time.time()
                self.telemetry.log_event("command_start", {"command": self.name})
                return self

            def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
                duration = time.time() - self.start_time
                if exc_type:
                    self.telemetry.log_event(
                        "command_fail",
                        {
                            "command": self.name,
                            "duration": duration,
                            "error": str(exc_val),
                            "stack_trace": "".join(
                                traceback.format_exception(exc_type, exc_val, exc_tb)
                            ),
                        },
                    )
                else:
                    self.telemetry.log_event(
                        "command_success", {"command": self.name, "duration": duration}
                    )

        return CommandTracker(self, command_name)

    def get_stats(self) -> dict[str, Any]:
        """Retrieve telemetry statistics."""
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
                        event_type = event.get("event_type")

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


telemetry = Telemetry()
