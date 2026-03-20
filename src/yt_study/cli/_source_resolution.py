"""CLI source-resolution helpers for videos, playlists, and batch summaries."""

from __future__ import annotations

from yt_study.cli._context import CliProcessContext
from yt_study.cli._types import ResolvedSource, _BatchVideoJob, _OrderedBatchFailure
from yt_study.errors import (
    PlaylistError,
    UserVisibleCliError,
    ValidationError,
    VideoUnavailableError,
)
from yt_study.pipeline.core import dedupe_video_ids
from yt_study.utils import sanitize_filename


async def prepare_source(
    context: CliProcessContext,
    source_url: str,
) -> ResolvedSource:
    """Resolve one input URL into a runnable video or playlist source."""
    try:
        parsed = context.parse_youtube_url(source_url)
    except (ValidationError, ValueError) as error:
        raise UserVisibleCliError("Input Error", [("URL", str(error))]) from error

    if parsed.url_type == "video":
        if not parsed.video_id:
            raise UserVisibleCliError(
                "Input Error",
                [("URL", "Could not extract a video ID from this URL.")],
            )
        return ResolvedSource(
            source_url=source_url,
            label=parsed.video_id,
            playlist_name="Single Video",
            video_ids=[parsed.video_id],
            output_dir=context.selected_output,
        )

    if not parsed.playlist_id:
        raise UserVisibleCliError(
            "Input Error",
            [("URL", "Could not extract a playlist ID from this URL.")],
        )

    try:
        video_ids = await context.extract_playlist_videos(
            parsed.playlist_id,
            cookie_file=context.selected_cookie_file,
        )
    except (PlaylistError, VideoUnavailableError) as error:
        raise UserVisibleCliError(
            "Playlist Error",
            [(parsed.playlist_id, str(error))],
        ) from error

    playlist_name, _ = await context.get_playlist_info(
        parsed.playlist_id,
        context.selected_cookie_file,
    )
    deduped_video_ids = dedupe_video_ids(video_ids)
    output_dir = context.selected_output / sanitize_filename(playlist_name)
    output_dir.mkdir(parents=True, exist_ok=True)

    return ResolvedSource(
        source_url=source_url,
        label=playlist_name or parsed.playlist_id,
        playlist_name=playlist_name,
        video_ids=deduped_video_ids,
        output_dir=output_dir,
        is_playlist=True,
    )


def failure_rows_for_result(
    prepared: ResolvedSource,
    errors: dict[str, str],
) -> list[tuple[str, str]]:
    """Format user-facing failure rows for one source."""
    if errors:
        return list(errors.items())
    return [
        (
            prepared.label,
            "We couldn't process this entry. Check the current session log "
            "for details.",
        )
    ]


def ordered_batch_failures_from_error(
    item_index: int,
    batch_url: str,
    error: UserVisibleCliError,
) -> list[_OrderedBatchFailure]:
    """Normalize preparation failures into stable, sorted batch rows."""
    failures: list[_OrderedBatchFailure] = []
    for row_index, (item, message) in enumerate(error.rows, start=1):
        display_item = batch_url if item == "URL" else item
        failures.append(
            _OrderedBatchFailure(
                sort_key=(item_index, row_index),
                item=display_item,
                message=message,
            )
        )
    return failures


def batch_failure_label(job: _BatchVideoJob, display_title: str) -> str:
    """Format a batch failure label for direct videos or playlist videos."""
    if job.is_playlist_video:
        return f"{job.source_label} / {display_title}"
    return display_title
