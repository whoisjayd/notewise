"""Module entrypoint for ``python -m notewise`` and console scripts."""

from __future__ import annotations

import sys


def _is_help_invocation(argv: list[str]) -> bool:
    """Return True when the current argv explicitly asks for help output."""
    if any(arg in {"--help", "-h"} for arg in argv):
        return True
    # `notewise help` (no flag) is a plain top-level command, not an option,
    # so it only counts here in the first argv position.
    return bool(argv) and argv[0] == "help"


def main() -> None:
    """Run the NoteWise Typer application."""
    from notewise.cli._banner import print_help_banner
    from notewise.cli.app import _get_console, app

    if _is_help_invocation(sys.argv[1:]):
        console = _get_console()
        print_help_banner(console)
        console.print()

    app()


if __name__ == "__main__":
    main()
