"""Single-source CLI processing flow."""

from __future__ import annotations

from typing import cast

from notewise.cli._context import CliProcessContext
from notewise.cli._display import (
    build_dashboard_config_items,
    build_ui_event_handler,
    emit_headless_event,
    print_single_run_summary,
    restore_console_after_live,
    should_clear_dashboard_after_run,
    use_transient_live_display,
)
from notewise.cli._formatters import print_cost_summary
from notewise.cli._source_resolution import failure_rows_for_result, prepare_source
from notewise.cli._types import _WorkerSlotManager
from notewise.domain.results import PipelineResult
from notewise.errors import UserVisibleCliError
from notewise.logging import get_session_log_path


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
    configured_chapter_concurrency = getattr(
        context.config,
        "max_concurrent_chapters",
        0,
    )
    chapter_concurrency = (
        configured_chapter_concurrency
        if isinstance(configured_chapter_concurrency, int)
        else 0
    )
    dashboard = context.dashboard_cls(
        total_videos=len(prepared.video_ids),
        concurrency=concurrency,
        playlist_name=prepared.playlist_name,
        model_name=context.selected_model,
        chapter_concurrency=chapter_concurrency,
        run_label=prepared.playlist_name,
        output_path=str(prepared.output_dir),
        config_items=build_dashboard_config_items(
            context,
            output_dir=prepared.output_dir,
            video_workers=concurrency,
            chapter_workers=chapter_concurrency,
        ),
    )
    slot_manager = _WorkerSlotManager(concurrency)
    on_event = build_ui_event_handler(dashboard, slot_manager)

    live = context.live_cls(
        dashboard,
        refresh_per_second=10,
        console=context.console,
        screen=False,
        transient=use_transient_live_display(),
    )
    try:
        with live:
            result = cast(
                PipelineResult,
                await pipeline.run(prepared.video_ids, on_event=on_event),
            )
            if should_clear_dashboard_after_run(dashboard, result):
                live.transient = True
    finally:
        stop_live = getattr(live, "stop", None)
        if callable(stop_live):
            stop_live()
        restore_console_after_live(context.console)

    print_single_run_summary(context, result, dashboard)
    return result.failure_count == 0
