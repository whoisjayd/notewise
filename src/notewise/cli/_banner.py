"""Brand banner helpers for the NoteWise CLI."""

from __future__ import annotations

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text


_UNICODE_BANNER_LINES = [
    "███╗   ██╗ ██████╗ ████████╗███████╗██╗    ██╗██╗███████╗███████╗",
    "████╗  ██║██╔═══██╗╚══██╔══╝██╔════╝██║    ██║██║██╔════╝██╔════╝",
    "██╔██╗ ██║██║   ██║   ██║   █████╗  ██║ █╗ ██║██║███████╗█████╗  ",
    "██║╚██╗██║██║   ██║   ██║   ██╔══╝  ██║███╗██║██║╚════██║██╔══╝  ",
    "██║ ╚████║╚██████╔╝   ██║   ███████╗╚███╔███╔╝██║███████║███████╗",
    "╚═╝  ╚═══╝ ╚═════╝    ╚═╝   ╚══════╝ ╚══╝╚══╝ ╚═╝╚══════╝╚══════╝",
]

_ASCII_BANNER_LINES = [
    "NOTEWISE",
]

# Gradient: cyan-sky → deep-ocean, top to bottom
_LINE_COLORS = [
    "bold color(87)",  # bright cyan
    "bold color(81)",
    "bold color(45)",
    "bold color(39)",
    "bold color(33)",
    "bold color(27)",
    "bold color(26)",
    "bold color(25)",  # deep blue
]

_REPO_URL = "github.com/whoisjayd/notewise"


def _get_version() -> str:
    try:
        from notewise import __version__

        return __version__
    except ImportError:
        return "dev"


def _tagline(version: str, *, use_unicode: bool = True) -> Text:
    t = Text("  ", style="color(240)")
    t.append("AI-powered YouTube study notes", style="bright_white")
    t.append("\n  ", style="")
    t.append(f"v{version}", style="bold color(87)")
    t.append("  │  " if use_unicode else "  |  ", style="color(240)")
    t.append(_REPO_URL, style="color(244)")
    return t


def _supports_unicode_output(console: Console) -> bool:
    """Return whether the target console is safe for decorative Unicode output."""
    encoding = (console.encoding or "").lower()
    return bool(encoding) and "utf" in encoding and not console.is_dumb_terminal


def _banner_text(*, use_unicode: bool = True) -> Text:
    banner = Text()
    lines = _UNICODE_BANNER_LINES if use_unicode else _ASCII_BANNER_LINES
    colors = _LINE_COLORS[: len(lines)]
    for line, color in zip(lines, colors, strict=True):
        if banner:
            banner.append("\n")
        banner.append(line, style=color)
    return banner


def _banner_panel(console: Console) -> Panel:
    use_unicode = _supports_unicode_output(console)
    return Panel(
        Group(
            _banner_text(use_unicode=use_unicode),
            Text(),
            _tagline(_get_version(), use_unicode=use_unicode),
        ),
        border_style="cyan",
        box=box.ROUNDED if use_unicode else box.ASCII,
        padding=(1, 2),
        expand=False,
    )


def print_banner(console: Console) -> None:
    """Print the primary NoteWise banner.

    Args:
        console:  Rich Console instance.
    """
    console.print(_banner_panel(console), highlight=False)


def print_help_banner(console: Console) -> None:
    """Print the help banner."""
    print_banner(console)
