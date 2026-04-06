"""Brand banner helpers for the NoteWise CLI."""

from __future__ import annotations

import time

from rich.console import Console
from rich.text import Text


# Avatar-font ASCII art (patorjk.com/software/taag — Avatar, "Note Wise")
_BANNER_LINES = [
    r"$$\   $$\             $$\                     $$\      $$\ $$\                     ",
    r"$$$\  $$ |            $$ |                    $$ | $\  $$ |\__|                    ",
    r"$$$$\ $$ | $$$$$$\  $$$$$$\    $$$$$$\        $$ |$$$\ $$ |$$\  $$$$$$$\  $$$$$$\  ",
    r"$$ $$\$$ |$$  __$$\ \_$$  _|  $$  __$$\       $$ $$ $$\$$ |$$ |$$  _____|$$  __$$\ ",
    r"$$ \$$$$ |$$ /  $$ |  $$ |    $$$$$$$$ |      $$$$  _$$$$ |$$ |\$$$$$$\  $$$$$$$$ |",
    r"$$ |\$$$ |$$ |  $$ |  $$ |$$\ $$   ____|      $$$  / \$$$ |$$ | \____$$\ $$   ____|",
    r"$$ | \$$ |\$$$$$$  |  \$$$$  |\$$$$$$$\       $$  /   \$$ |$$ |$$$$$$$  |\$$$$$$$\ ",
    r"\__|  \__| \______/    \____/  \_______|      \__/     \__|\__|\_______/  \_______|",
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

_RULE_STYLE_TOP = "color(45)"
_RULE_STYLE_BOT = "color(25)"
_RULE_CHAR = "─"
_RULE_WIDTH = 88
_ANIM_DELAY = 0.045  # seconds between each banner line


def _get_version() -> str:
    try:
        from notewise import __version__

        return __version__
    except ImportError:
        return "dev"


def _tagline(version: str) -> Text:
    t = Text("  ", style="color(240)")
    t.append("AI-powered YouTube study notes", style="bright_white")
    t.append("   ", style="")
    t.append(f"v{version}", style="bold color(87)")
    return t


def _print_rule(console: Console, *, style: str) -> None:
    """Unicode box-drawing rule; falls back to dashes on legacy terminals."""
    try:
        console.print(_RULE_CHAR * _RULE_WIDTH, style=style, highlight=False)
    except UnicodeEncodeError:
        console.print("-" * _RULE_WIDTH, style=style, highlight=False)


def _print_banner_lines(console: Console, *, animate: bool = True) -> None:
    for line, color in zip(_BANNER_LINES, _LINE_COLORS, strict=True):
        console.print(line, style=color, highlight=False)
        if animate:
            time.sleep(_ANIM_DELAY)


def print_banner(console: Console, *, animate: bool = True) -> None:
    """Print the primary NoteWise banner.

    Args:
        console:  Rich Console instance.
        animate:  When *True* each line is revealed with a short delay.
                  Pass *False* for tests or redirected output.
    """
    console.print()
    _print_banner_lines(console, animate=animate)
    console.print()
    _print_rule(console, style=_RULE_STYLE_TOP)
    console.print(_tagline(_get_version()))
    _print_rule(console, style=_RULE_STYLE_BOT)
    console.print()


def print_help_banner(console: Console) -> None:
    """Print the help banner."""
    print_banner(console)
