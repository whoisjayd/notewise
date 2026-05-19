"""Batch-file CLI processing flow."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

import structlog
from rich.markup import escape

from notewise._constants import (
    BATCH_SOURCE_UNEXPECTED_ERROR_MESSAGE,
    BATCH_SOURCE_UNEXPECTED_ERROR_TITLE,
    DASHBOARD_IDLE_MARKUP,
    DASHBOARD_REFRESH_PER_SECOND,
)
from notewise.cli._display import (
    UI_STATUS_MAP,
    build_dashboard_config_items,
    emit_headless_event,
    print_batch_summary,
    restore_console_after_live,
    should_clear_dashboard_after_run,
    update_dashboard_chapter_slot,
    update_dashboard_worker_for_event,
    use_transient_live_display,
)
from notewise.cli._source_resolution import (
    batch_failure_label,
    ordered_batch_failures_from_error,
    prepare_source,
)
from notewise.cli._types import (
    ResolvedSource,
    _BatchJobResult,
    _BatchVideoJob,
    _OrderedBatchFailure,
)
from notewise.domain.events import EventType, PipelineEvent
from notewise.domain.results import PipelineResult
from notewise.errors import UserVisibleCliError
from notewise.pipeline.core import PipelineSharedState


if TYPE_CHECKING:
    from pathlib import Path

    from notewise.cli._context import CliProcessContext


BATCH_CHAPTER_EVENT_TYPES = (
    EventType.CHAPTER_GENERATING,
    EventType.CHAPTER_CHUNK_GENERATING,
    EventType.CHAPTER_COMBINING,
    EventType.CHAPTER_COMPLETE,
)


def _set_dashboard_worker_idle(dashboard: object, worker_index: int) -> None:
    cast("Any", dashboard).update_worker(worker_index, DASHBOARD_IDLE_MARKUP)


def _finish_dashboard_video(
    dashboard: object,
    worker_index: int,
    fallback_video_id: str,
) -> None:
    if hasattr(dashboard, "clear_chapter_workers"):
        cast("Any", dashboard).clear_chapter_workers(fallback_video_id)
    if hasattr(dashboard, "clear_worker_state"):
        cast("Any", dashboard).clear_worker_state(worker_index)
    _set_dashboard_worker_idle(dashboard, worker_index)


async def run_batch_file(
    context: CliProcessContext,
    input_path: Path,
    urls: list[str],
) -> bool:
    """Process batch URLs through one shared video worker pool."""
    if not context.ensure_api_key_available():
        return True

    ensure_output_dir = getattr(context, "ensure_selected_output_dir", None)
    if callable(ensure_output_dir):
        ensure_output_dir()
    else:
        context.selected_output.mkdir(parents=True, exist_ok=True)
    batch_workers = max(1, context.config.max_concurrent_videos)
    batch_label = f"Batch File: {input_path.name}"
    dashboard = None
    if not context.no_ui:
        dashboard = context.dashboard_cls(
            total_videos=0,
            concurrency=batch_workers,
            playlist_name=batch_label,
            model_name=context.selected_model,
            chapter_concurrency=context.config.max_concurrent_chapters,
            run_label=batch_label,
            output_path=str(context.selected_output),
            config_items=build_dashboard_config_items(
                context,
                output_dir=context.selected_output,
                video_workers=batch_workers,
                chapter_workers=context.config.max_concurrent_chapters,
            ),
        )

    shared_state = PipelineSharedState(semaphore=asyncio.Semaphore(batch_workers))
    job_queue: asyncio.Queue[_BatchVideoJob | None] = asyncio.Queue()
    batch_results: list[_BatchJobResult] = []
    early_failures: list[_OrderedBatchFailure] = []
    total_jobs = 0

    async def run_batch_job(worker_index: int) -> None:
        while True:
            job = await job_queue.get()
            if job is None:
                if dashboard is not None:
                    _set_dashboard_worker_idle(dashboard, worker_index)
                job_queue.task_done()
                return

            latest_title = job.video_id
            fallback_video_id = job.video_id
            was_skipped = False
            try:
                pipeline = context.build_pipeline(
                    job.output_dir,
                    shared_state=shared_state,
                )

                def on_batch_event(
                    event: PipelineEvent,
                    *,
                    _fallback_video_id: str = fallback_video_id,
                ) -> None:
                    nonlocal latest_title
                    nonlocal was_skipped
                    if event.title:
                        latest_title = event.title
                    if event.event_type == EventType.VIDEO_SKIPPED:
                        was_skipped = True
                    if dashboard is None:
                        emit_headless_event(context, event)
                        return
                    if event.event_type == EventType.METADATA_START and hasattr(
                        dashboard,
                        "clear_chapter_workers",
                    ):
                        dashboard.clear_chapter_workers(_fallback_video_id)
                    if event.event_type in BATCH_CHAPTER_EVENT_TYPES:
                        update_dashboard_chapter_slot(
                            dashboard,
                            escape((latest_title or _fallback_video_id)[:40]),
                            event,
                        )
                    if event.event_type not in UI_STATUS_MAP:
                        return
                    update_dashboard_worker_for_event(
                        dashboard,
                        worker_index,
                        (latest_title or _fallback_video_id)[:40],
                        event,
                    )

                result = cast(
                    "PipelineResult",
                    await pipeline.run(
                        [fallback_video_id],
                        on_event=on_batch_event,
                    ),
                )
                display_title = latest_title or fallback_video_id
                completion_title = (
                    f"{display_title} (skipped)" if was_skipped else display_title
                )

                if dashboard is not None:
                    _finish_dashboard_video(dashboard, worker_index, fallback_video_id)
                    if result.failure_count:
                        dashboard.add_failure(display_title)
                    elif was_skipped and hasattr(dashboard, "add_skipped"):
                        dashboard.add_skipped(display_title)
                    else:
                        dashboard.add_completion(completion_title)

                failure_row = None
                if result.failure_count:
                    failure_message = next(
                        iter(result.errors.values()),
                        "We couldn't process this batch video. Check the current "
                        "session log for details.",
                    )
                    failure_row = _OrderedBatchFailure(
                        sort_key=job.sort_key,
                        item=batch_failure_label(job, display_title),
                        message=failure_message,
                    )

                batch_results.append(
                    _BatchJobResult(
                        sort_key=job.sort_key,
                        success=result.failure_count == 0,
                        display_title=display_title,
                        failure_row=failure_row,
                        metrics=result.metrics,
                    )
                )
            except Exception:
                display_title = latest_title or fallback_video_id
                structlog.get_logger(__name__).exception("batch.video_failure")
                if dashboard is not None:
                    _finish_dashboard_video(dashboard, worker_index, fallback_video_id)
                    dashboard.add_failure(display_title)
                batch_results.append(
                    _BatchJobResult(
                        sort_key=job.sort_key,
                        success=False,
                        display_title=display_title,
                        failure_row=_OrderedBatchFailure(
                            sort_key=job.sort_key,
                            item=batch_failure_label(job, display_title),
                            message=(
                                "notewise hit an unexpected internal error "
                                "for this video. Check the current log "
                                "for details."
                            ),
                        ),
                    )
                )
            finally:
                job_queue.task_done()

    async def enqueue_batch_jobs() -> None:
        nonlocal total_jobs
        resolution_concurrency = min(3, max(1, len(urls)))
        resolution_gate = asyncio.Semaphore(resolution_concurrency)
        resolved_sources: asyncio.Queue[
            tuple[int, str, ResolvedSource | None, UserVisibleCliError | None]
        ] = asyncio.Queue()

        async def resolve_source(
            item_index: int,
            batch_url: str,
        ) -> None:
            async with resolution_gate:
                try:
                    prepared = await prepare_source(context, batch_url)
                except UserVisibleCliError as error:
                    await resolved_sources.put((item_index, batch_url, None, error))
                    return
                except Exception:
                    structlog.get_logger(__name__).exception("batch.source_failure")
                    await resolved_sources.put(
                        (
                            item_index,
                            batch_url,
                            None,
                            UserVisibleCliError(
                                BATCH_SOURCE_UNEXPECTED_ERROR_TITLE,
                                [
                                    (
                                        batch_url,
                                        BATCH_SOURCE_UNEXPECTED_ERROR_MESSAGE,
                                    )
                                ],
                            ),
                        )
                    )
                    return
                await resolved_sources.put((item_index, batch_url, prepared, None))

        if context.no_ui and len(urls) >= 10:
            context.console.print(
                f"Preflight: resolving {len(urls)} batch entries with up to "
                f"{resolution_concurrency} concurrent lookups."
            )

        def update_preflight_status(resolved_count: int) -> None:
            if dashboard is None:
                return
            dashboard.update_overall_status(
                "Preflight: "
                f"{resolved_count}/{len(urls)} sources resolved • "
                f"{total_jobs} videos queued"
            )

        tasks = [
            asyncio.create_task(resolve_source(item_index, batch_url))
            for item_index, batch_url in enumerate(urls, start=1)
        ]

        try:
            for resolved_count in range(1, len(urls) + 1):
                (
                    item_index,
                    batch_url,
                    prepared_obj,
                    error,
                ) = await resolved_sources.get()
                update_preflight_status(resolved_count)
                if error is not None:
                    early_failures.extend(
                        ordered_batch_failures_from_error(item_index, batch_url, error)
                    )
                    continue

                prepared = prepared_obj
                if prepared is None or not prepared.video_ids:
                    label = batch_url if prepared is None else prepared.label
                    early_failures.append(
                        _OrderedBatchFailure(
                            sort_key=(item_index, 1),
                            item=label,
                            message="No videos found to process.",
                        )
                    )
                    continue

                for video_index, video_id in enumerate(prepared.video_ids, start=1):
                    total_jobs += 1
                    if dashboard is not None:
                        dashboard.set_total_videos(total_jobs)
                        update_preflight_status(resolved_count)
                    await job_queue.put(
                        _BatchVideoJob(
                            sort_key=(item_index, video_index),
                            video_id=video_id,
                            output_dir=prepared.output_dir,
                            source_label=prepared.label,
                            is_playlist_video=prepared.is_playlist,
                        )
                    )
        finally:
            await asyncio.gather(*tasks)

        if dashboard is not None:
            dashboard.update_overall_status("")
        for _ in range(batch_workers):
            await job_queue.put(None)

    async def run_batch_queue() -> None:
        workers = [
            asyncio.create_task(run_batch_job(worker_index))
            for worker_index in range(batch_workers)
        ]
        await enqueue_batch_jobs()
        await job_queue.join()
        await asyncio.gather(*workers)

    if dashboard is not None:
        live = context.live_cls(
            dashboard,
            refresh_per_second=DASHBOARD_REFRESH_PER_SECOND,
            console=context.console,
            screen=False,
            transient=use_transient_live_display(),
        )
        try:
            with live:
                await run_batch_queue()
                failure_rows = [
                    result.failure_row
                    for result in batch_results
                    if result.failure_row is not None
                ]
                synthetic_result = PipelineResult(
                    success_count=sum(1 for result in batch_results if result.success),
                    failure_count=len(early_failures) + len(failure_rows),
                    total_count=total_jobs,
                    video_ids=[result.display_title for result in batch_results],
                    errors={},
                )
                if should_clear_dashboard_after_run(dashboard, synthetic_result):
                    live.transient = True
        finally:
            stop_live = getattr(live, "stop", None)
            if callable(stop_live):
                stop_live()
            restore_console_after_live(context.console)
    else:
        await run_batch_queue()

    return print_batch_summary(
        context,
        batch_results,
        early_failures,
        total_jobs=total_jobs,
    )
