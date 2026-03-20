"""Batch-file CLI processing flow."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

import structlog

from yt_study.cli._context import CliProcessContext
from yt_study.cli._display import UI_STATUS_MAP, print_batch_summary
from yt_study.cli._source_resolution import (
    batch_failure_label,
    ordered_batch_failures_from_error,
    prepare_source,
)
from yt_study.cli._types import _BatchJobResult, _BatchVideoJob, _OrderedBatchFailure
from yt_study.domain.events import PipelineEvent
from yt_study.domain.results import PipelineResult
from yt_study.errors import UserVisibleCliError
from yt_study.pipeline.core import PipelineSharedState


async def run_batch_file(
    context: CliProcessContext,
    input_path: Path,
    urls: list[str],
) -> bool:
    """Process batch URLs through one shared video worker pool."""
    if not context.ensure_api_key_available():
        return True

    batch_workers = max(1, context.config.max_concurrent_videos)
    dashboard = None
    if not context.no_ui:
        dashboard = context.dashboard_cls(
            total_videos=0,
            concurrency=batch_workers,
            playlist_name=f"Batch File: {input_path.name}",
            model_name=context.selected_model,
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
                    dashboard.update_worker(worker_index, "[dim]Idle[/dim]")
                job_queue.task_done()
                return

            latest_title = job.video_id
            fallback_video_id = job.video_id
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
                    if event.title:
                        latest_title = event.title
                    if dashboard is None or event.event_type not in UI_STATUS_MAP:
                        return
                    status_fn = UI_STATUS_MAP[event.event_type]
                    dashboard.update_worker(
                        worker_index,
                        status_fn((latest_title or _fallback_video_id)[:40], event),
                    )

                result = cast(
                    PipelineResult,
                    await pipeline.run(
                        [fallback_video_id],
                        on_event=on_batch_event if dashboard is not None else None,
                    ),
                )
                display_title = latest_title or fallback_video_id

                if dashboard is not None:
                    dashboard.update_worker(worker_index, "[dim]Idle[/dim]")
                    if result.failure_count:
                        dashboard.add_failure(display_title)
                    else:
                        dashboard.add_completion(display_title)

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
                    dashboard.update_worker(worker_index, "[dim]Idle[/dim]")
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
                                "yt-study hit an unexpected internal error "
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
        for item_index, batch_url in enumerate(urls, start=1):
            if dashboard is not None:
                dashboard.update_overall_status(
                    f"Resolving batch entry {item_index}/{len(urls)}"
                )
            try:
                prepared = await prepare_source(context, batch_url)
            except UserVisibleCliError as error:
                early_failures.extend(
                    ordered_batch_failures_from_error(item_index, batch_url, error)
                )
                continue

            for video_index, video_id in enumerate(prepared.video_ids, start=1):
                total_jobs += 1
                if dashboard is not None:
                    dashboard.set_total_videos(total_jobs)
                await job_queue.put(
                    _BatchVideoJob(
                        sort_key=(item_index, video_index),
                        video_id=video_id,
                        output_dir=prepared.output_dir,
                        source_label=prepared.label,
                        is_playlist_video=prepared.is_playlist,
                    )
                )

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
        with context.live_cls(
            dashboard,
            refresh_per_second=10,
            console=context.console,
            screen=False,
            transient=True,
        ):
            await run_batch_queue()
    else:
        await run_batch_queue()

    return print_batch_summary(
        context,
        batch_results,
        early_failures,
        total_jobs=total_jobs,
    )
