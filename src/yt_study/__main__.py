"""Module entrypoint for ``python -m yt_study`` and console scripts."""

from __future__ import annotations

from yt_study.cli.app import app


def main() -> None:
    """Run the Typer application."""
    app()


if __name__ == "__main__":
    main()
