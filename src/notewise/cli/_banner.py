"""Brand banner helpers for the NoteWise CLI."""

from __future__ import annotations

from rich.console import Console
from rich.text import Text


_BANNER_LINES = [
    r"N   N  OOO  TTTTT EEEEE W   W III  SSS  EEEEE",
    r"NN  N O   O   T   E     W   W  I  S     E    ",
    r"N N N O   O   T   EEE   W W W  I   SSS  EEE  ",
    r"N  NN O   O   T   E     WW WW  I      S E    ",
    r"N   N  OOO    T   EEEEE W   W III  SSS  EEEEE",
]

_LINE_COLORS = [
    "bold color(159)",
    "bold color(117)",
    "bold color(75)",
    "bold color(33)",
    "bold color(27)",
]

_RULE_WIDTH = 45


def _get_version() -> str:
    try:
        from notewise import __version__

        return __version__
    except ImportError:
        return "dev"


def _tagline(version: str) -> Text:
    tagline = Text("  ", style="color(240)")
    tagline.append("AI-powered YouTube study notes", style="bright_white")
    tagline.append("   ", style="")
    tagline.append(f"v{version}", style="bold color(159)")
    return tagline


def _print_rule(console: Console, *, style: str) -> None:
    """Render an ASCII-safe separator for Windows and redirected output."""
    console.print("-" * _RULE_WIDTH, style=style, highlight=False)


def _print_banner_lines(console: Console) -> None:
    for line, color in zip(_BANNER_LINES, _LINE_COLORS, strict=True):
        console.print(line, style=color, highlight=False)


def print_banner(console: Console) -> None:
    """Print the primary NoteWise banner."""
    console.print()
    _print_banner_lines(console)
    console.print()
    _print_rule(console, style="color(75)")
    console.print(_tagline(_get_version()))
    _print_rule(console, style="color(27)")
    console.print()


def print_help_banner(console: Console) -> None:
    """Print the help banner."""
    print_banner(console)
