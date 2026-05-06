"""Tests for wiring safe dashboard context into CLI runners."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from notewise.cli import _batch_runner, _single_runner
from notewise.domain.results import PipelineResult
from notewise.ui.dashboard import PipelineDashboard


class _FakeLive:
    """Small Rich Live stand-in for runner unit tests."""

    def __init__(self, dashboard: object, **kwargs: object) -> None:
        self.dashboard = dashboard
        self.kwargs = kwargs
        self.transient = False

    def __enter__(self) -> _FakeLive:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def stop(self) -> None:
        return None


class _FakePipeline:
    """Pipeline stand-in returning one successful result."""

    async def run(self, video_ids: list[str], *, on_event: object) -> PipelineResult:
        _ = on_event
        return PipelineResult(
            success_count=len(video_ids),
            failure_count=0,
            total_count=len(video_ids),
            video_ids=video_ids,
            errors={},
        )


def _make_context(
    captured_dashboard_kwargs: list[dict[str, object]],
) -> SimpleNamespace:
    """Create a minimal runner context that captures dashboard constructor args."""

    def dashboard_cls(**kwargs: object) -> PipelineDashboard:
        captured_dashboard_kwargs.append(kwargs)
        return PipelineDashboard(**kwargs)

    return SimpleNamespace(
        config=SimpleNamespace(max_concurrent_videos=3, max_concurrent_chapters=4),
        console=MagicMock(),
        selected_model="gemini/gemini-2.5-pro",
        selected_output=Path("/tmp/notewise-output"),
        selected_output_formats=["md", "pdf"],
        selected_languages=["en", "hi"],
        selected_target_language="English",
        selected_temperature=0.3,
        selected_max_tokens=8192,
        selected_throttle_seconds=1.0,
        force=False,
        no_ui=False,
        quiz=True,
        use_combine_chunk=True,
        export_transcript=None,
        timestamps=True,
        chapter_directory_output=True,
        selected_cookie_file="/tmp/secret-dir/youtube-cookies.txt",
        api_key_checked=True,
        dashboard_cls=dashboard_cls,
        live_cls=_FakeLive,
        ensure_api_key_available=lambda: True,
        build_pipeline=lambda *_args, **_kwargs: _FakePipeline(),
    )


async def test_run_single_url_passes_safe_dashboard_context(mocker) -> None:
    """Single-source UI runner should pass safe config rows to the dashboard."""
    captured: list[dict[str, object]] = []
    context = _make_context(captured)
    prepared = SimpleNamespace(
        video_ids=["vid1", "vid2"],
        output_dir=Path("/tmp/notewise-notes"),
        playlist_name="Playlist A",
    )
    mocker.patch.object(
        _single_runner, "prepare_source", AsyncMock(return_value=prepared)
    )

    await _single_runner.run_single_url(
        context, "https://youtube.com/playlist?list=abc"
    )

    assert captured
    kwargs = captured[0]
    assert kwargs["run_label"] == "Playlist A"
    assert kwargs["output_path"] == str(Path("/tmp/notewise-notes"))
    rendered_config = "\n".join(
        f"{item.label}: {item.value}" for item in kwargs["config_items"]
    )
    assert "Video workers: 2" in rendered_config
    assert "Chapter workers: 4" in rendered_config
    assert "Cookies: configured: youtube-cookies.txt" in rendered_config
    assert "secret-dir" not in rendered_config


async def test_run_batch_file_passes_safe_dashboard_context() -> None:
    """Batch UI runner should pass batch label and safe config rows to dashboard."""
    captured: list[dict[str, object]] = []
    context = _make_context(captured)

    await _batch_runner.run_batch_file(context, Path("videos.txt"), [])

    assert captured
    kwargs = captured[0]
    assert kwargs["run_label"] == "Batch File: videos.txt"
    assert kwargs["output_path"] == str(Path("/tmp/notewise-output"))
    rendered_config = "\n".join(
        f"{item.label}: {item.value}" for item in kwargs["config_items"]
    )
    assert "Video workers: 3" in rendered_config
    assert "Chapter workers: 4" in rendered_config
    assert "API key: present" in rendered_config
