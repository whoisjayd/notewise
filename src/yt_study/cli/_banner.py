"""Brand banner helpers for the yt-study CLI."""

from __future__ import annotations

from rich.console import Console
from rich.text import Text


_BANNER_LINES = [
    r" __   __ _______       _______ _______ _     _ ______  _     _",
    r" \ \ / /   |          |______   |     |     | |     \  \   / ",
    r"  \ V /    |          ______|   |     |_____| |_____/   \_/  ",
    r"   \_/     |          _______   |     _     _ ______  _     _",
    r"    |      |          |______   |     |     | |     \  \___/ ",
    r"    |      |_____     ______|   |     |_____| |_____/ _/   \_",
]

# Light → deep blue step — all vivid, all readable
_LINE_COLORS = [
    "bold color(159)",  # pale sky blue
    "bold color(117)",  # light blue
    "bold color(75)",  # cornflower blue
    "bold color(33)",  # bright blue
    "bold color(27)",  # royal blue
    "bold color(21)",  # deep blue
]

_ASCII_RULE_WIDTH = 78


def _get_version() -> str:
    try:
        from yt_study import __version__

        return __version__
    except ImportError:
        return "dev"


def _tagline(version: str) -> Text:
    t = Text("> ", style="color(240)")
    t.append("AI-powered YouTube study notes", style="bright_white")
    t.append(" - ", style="")
    t.append(f"v{version}", style="bold color(159)")
    t.append(" - ", style="")
    t.append("playlists", style="color(75)")
    t.append(" - ", style="color(240)")
    t.append("batches", style="color(75)")
    t.append(" - ", style="color(240)")
    t.append("quizzes", style="color(75)")
    return t


def _print_rule(console: Console, *, style: str) -> None:
    """Render an ASCII-safe separator for Windows legacy consoles."""
    console.print("-" * _ASCII_RULE_WIDTH, style=style, highlight=False)


def print_banner(console: Console) -> None:
    """Print the yt-study brand banner."""
    version = _get_version()

    for line, color in zip(_BANNER_LINES, _LINE_COLORS, strict=True):
        console.print(line, style=color, highlight=False)
    _print_rule(console, style="color(75)")
    console.print(_tagline(version))
    _print_rule(console, style="color(27)")


def print_help_banner(console: Console) -> None:
    """Print the help banner with the full brand treatment."""
    print_banner(console)
