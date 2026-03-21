"""Single-source CLI processing flow."""

from __future__ import annotations

from typing import cast

from yt_study.cli._context import CliProcessContext
from yt_study.cli._display import (
    build_ui_event_handler,
    emit_headless_event,
    print_single_run_summary,
)
from yt_study.cli._formatters import print_cost_summary
from yt_study.cli._source_resolution import failure_rows_for_result, prepare_source
from yt_study.cli._types import _WorkerSlotManager
from yt_study.domain.results import PipelineResult
from yt_study.errors import UserVisibleCliError
from yt_study.logging import get_session_log_path


async def run_single_url(context: CliProcessContext, source_url: str) -> bool:
    """Parse one URL and run the pipeline in UI or headless mode."""
    try:
        prepared = await prepare_source(context, source_url)
    except UserVisibleCliError as error:
        context.print_failure_panel(error.title, error.rows, intro=error.intro)
        return False

    if not prepared.video_ids:
        context.print_single_failure(
            "Input Error",
            "No videos found to process.",
            item_label="Source",
        )
        return False

    if not context.ensure_api_key_available():
        return False

    pipeline = context.build_pipeline(prepared.output_dir)

    if context.no_ui:
        result = cast(
            PipelineResult,
            await pipeline.run(
                prepared.video_ids,
                on_event=lambda event: emit_headless_event(context, event),
            ),
        )
        if result.total_count:
            if result.failure_count:
                intro = None
                if result.success_count:
                    intro = (
                        "Completed successfully: "
                        f"{result.success_count}/{result.total_count}"
                    )
                context.print_failure_panel(
                    "Processing Failed",
                    failure_rows_for_result(prepared, result.errors),
                    intro=intro,
                )
            else:
                context.console.print(
                    f"\nDone: {result.success_count}/{result.total_count} succeeded."
                )
                print_cost_summary(context.console, result.metrics)
                context.console.print(
                    f"[dim]Current log: {get_session_log_path()}[/dim]\n"
                )
        return result.failure_count == 0

    concurrency = min(len(prepared.video_ids), context.config.max_concurrent_videos)
    dashboard = context.dashboard_cls(
        total_videos=len(prepared.video_ids),
        concurrency=concurrency,
        playlist_name=prepared.playlist_name,
        model_name=context.selected_model,
    )
    slot_manager = _WorkerSlotManager(concurrency)
    on_event = build_ui_event_handler(dashboard, slot_manager)

    with context.live_cls(
        dashboard,
        refresh_per_second=10,
        console=context.console,
        screen=False,
        transient=True,
    ):
        result = cast(
            PipelineResult,
            await pipeline.run(prepared.video_ids, on_event=on_event),
        )

    print_single_run_summary(context, result, dashboard)
    return result.failure_count == 0
