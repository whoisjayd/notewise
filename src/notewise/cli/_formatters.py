"""Rich rendering helpers for CLI output panels and summaries."""

from __future__ import annotations

from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from notewise._constants import (
    CLI_COST_DECIMAL_PLACES,
    CLI_LOG_PATH_UNAVAILABLE_LABEL,
    CLI_SECONDS_DECIMAL_PLACES,
)
from notewise.domain.results import PipelineMetrics, PipelineResult
from notewise.logging import get_session_log_path
from notewise.utils import coerce_non_negative_float, coerce_non_negative_int


def print_failure_panel(
    console: Console,
    title: str,
    rows: list[tuple[str, str]],
    *,
    intro: str | None = None,
) -> None:
    """Render a user-facing failure summary panel."""
    failure_table = Table(
        box=None,
        show_header=False,
        show_edge=False,
        pad_edge=False,
        padding=(0, 1),
    )
    failure_table.add_column("Item", style="bold red", no_wrap=True)
    failure_table.add_column("Message", overflow="fold")
    for item, message in rows:
        failure_table.add_row(item, message)

    renderables: list[RenderableType] = []
    if intro:
        renderables.append(Text(intro, style="bold"))
    renderables.append(failure_table)
    log_path = get_session_log_path()
    renderables.append(
        Text(f"Current log: {log_path or CLI_LOG_PATH_UNAVAILABLE_LABEL}", style="dim")
    )

    console.print("\n")
    console.print(
        Panel(
            Group(*renderables),
            title=f"[bold red]{title}[/bold red]",
            border_style="red",
        )
    )
    console.print()


def print_single_failure(
    console: Console,
    title: str,
    message: str,
    *,
    item_label: str = "Issue",
    intro: str | None = None,
) -> None:
    """Render a one-item failure panel."""
    print_failure_panel(console, title, [(item_label, message)], intro=intro)


def print_cost_summary(console: Console, metrics: PipelineMetrics) -> None:
    """Render token/timing metrics table."""
    if not metrics:
        return

    cost_table = Table(
        title="Cost Summary",
        border_style="green",
        show_header=True,
        header_style="bold green",
    )
    cost_table.add_column("Metric", style="cyan")
    cost_table.add_column("Value", justify="right")
    cost_table.add_row(
        "Prompt Tokens",
        f"{coerce_non_negative_int(getattr(metrics, 'prompt_tokens', 0)):,}",
    )
    cost_table.add_row(
        "Completion Tokens",
        f"{coerce_non_negative_int(getattr(metrics, 'completion_tokens', 0)):,}",
    )
    cost_table.add_row(
        "Total Tokens",
        f"{coerce_non_negative_int(getattr(metrics, 'total_tokens', 0)):,}",
    )
    cost_table.add_row(
        "Estimated Cost (USD)",
        "$"
        + format(
            coerce_non_negative_float(getattr(metrics, "cost_usd", 0.0)),
            f".{CLI_COST_DECIMAL_PLACES}f",
        ),
    )
    cost_table.add_row(
        "Transcript Time (s)",
        format(
            coerce_non_negative_float(getattr(metrics, "transcript_seconds", 0.0)),
            f".{CLI_SECONDS_DECIMAL_PLACES}f",
        ),
    )
    cost_table.add_row(
        "Generation Time (s)",
        format(
            coerce_non_negative_float(getattr(metrics, "generation_seconds", 0.0)),
            f".{CLI_SECONDS_DECIMAL_PLACES}f",
        ),
    )
    console.print("\n")
    console.print(cost_table)


def print_run_summary(
    console: Console,
    result: PipelineResult,
    recent_failures: list[str],
    recent_completions: list[str],
) -> None:
    """Render final run summary after Live display closes."""
    if not result.total_count:
        return

    if result.failure_count:
        intro = None
        if result.success_count:
            intro = (
                f"Completed successfully: {result.success_count}/{result.total_count}"
            )
        print_failure_panel(
            console,
            "Processing Failed",
            list(result.errors.items()),
            intro=intro,
        )
        return

    summary_table = Table(
        title="Processing Summary",
        border_style="cyan",
        show_header=True,
        header_style="bold magenta",
    )
    summary_table.add_column("Status", justify="center")
    summary_table.add_column("Video Title", style="dim")
    for title in recent_failures:
        summary_table.add_row("[bold red]FAILED[/bold red]", title)
    for title in recent_completions:
        summary_table.add_row("[green]SUCCESS[/green]", title)

    console.print("\n")
    console.print(summary_table)
    console.print(
        f"\n[bold]Total Completed:[/bold] {result.success_count}/{result.total_count}"
    )
    print_cost_summary(console, result.metrics)

    log_path = get_session_log_path()
    if log_path:
        console.print(f"[dim]Current log: {log_path}[/dim]\n")
