"""Tests for pipeline orchestrator."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yt_study.pipeline.orchestrator import PipelineOrchestrator, sanitize_filename


def test_sanitize_filename():
    """Test filename sanitization."""
    assert sanitize_filename("Hello World") == "Hello World"
    assert sanitize_filename("foo/bar:baz") == "foobarbaz"
    assert sanitize_filename("  spaces  ") == "spaces"
    assert len(sanitize_filename("a" * 200)) == 100


class TestPipelineOrchestrator:
    """Test orchestrator logic."""

    @pytest.fixture
    def orchestrator(self, temp_output_dir, mock_llm_provider):
        with patch(
            "yt_study.pipeline.orchestrator.get_provider",
            return_value=mock_llm_provider,
        ):
            orch = PipelineOrchestrator(model="mock-model", output_dir=temp_output_dir)
            # Mock the generator inside
            orch.generator = MagicMock()
            orch.generator.generate_study_notes = AsyncMock(return_value="# Notes")
            orch.generator.generate_chapter_based_notes = AsyncMock(
                return_value="# Chapter Notes"
            )
            orch.generator.provider = (
                mock_llm_provider  # needed for direct calls in chapter loop
            )
            return orch

    def test_validate_provider_missing_key(self, orchestrator, monkeypatch):
        """Test validation fails if key is missing."""
        # Mock config to return key name but env var is empty
        with patch(
            "yt_study.config.config.get_api_key_name_for_model", return_value="TEST_KEY"
        ):
            monkeypatch.delenv("TEST_KEY", raising=False)
            assert orchestrator.validate_provider() is False

    def test_validate_provider_success(self, orchestrator, monkeypatch):
        """Test validation succeeds if key exists."""
        with patch(
            "yt_study.config.config.get_api_key_name_for_model", return_value="TEST_KEY"
        ):
            monkeypatch.setenv("TEST_KEY", "123")
            assert orchestrator.validate_provider() is True

    @pytest.mark.asyncio
    async def test_process_video_single(self, orchestrator):
        """Test processing a single video (no chapters)."""
        # Mock dependencies
        with (
            patch(
                "yt_study.pipeline.orchestrator.get_video_title",
                return_value="Test Video",
            ),
            patch(
                "yt_study.pipeline.orchestrator.get_video_duration", return_value=100
            ),
            patch("yt_study.pipeline.orchestrator.get_video_chapters", return_value=[]),
            patch(
                "yt_study.pipeline.orchestrator.fetch_transcript",
                new_callable=AsyncMock,
            ) as mock_fetch,
        ):
            mock_transcript = MagicMock()
            mock_transcript.to_text.return_value = "Transcript text"
            mock_fetch.return_value = mock_transcript

            video_id = "vid123"
            output_path = orchestrator.output_dir / "notes.md"

            success = await orchestrator.process_video(video_id, output_path)

            assert success is True
            assert output_path.exists()
            assert output_path.read_text(encoding="utf-8") == "# Notes"
            orchestrator.generator.generate_study_notes.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_video_with_chapters(self, orchestrator):
        """Test processing a video with chapters."""
        # Mock dependencies
        # Duration > 3600 (1h) + Chapters present
        with (
            patch(
                "yt_study.pipeline.orchestrator.get_video_title",
                return_value="Long Video",
            ),
            patch(
                "yt_study.pipeline.orchestrator.get_video_duration", return_value=4000
            ),
            patch(
                "yt_study.pipeline.orchestrator.get_video_chapters",
                return_value=["chap1"],
            ),
            patch(
                "yt_study.pipeline.orchestrator.fetch_transcript",
                new_callable=AsyncMock,
            ) as mock_fetch,
            patch(
                "yt_study.pipeline.orchestrator.split_transcript_by_chapters",
                return_value={"Ch1": "text"},
            ),
        ):
            mock_transcript = MagicMock()
            mock_fetch.return_value = mock_transcript

            video_id = "vid123"
            output_path = (
                orchestrator.output_dir / "ignored.md"
            )  # Folder structure used instead

            success = await orchestrator.process_video(video_id, output_path)

            assert success is True
            # Verify folder creation
            expected_folder = orchestrator.output_dir / "Long Video"
            assert expected_folder.exists()
            # Verify individual chapter file created (mock provider returns
            # default text)
            assert (expected_folder / "01_Ch1.md").exists()

    @pytest.mark.asyncio
    async def test_run_video_flow(self, orchestrator):
        """Test run() method flow for a video URL."""
        with (
            patch("yt_study.pipeline.orchestrator.parse_youtube_url") as mock_parse,
            patch.object(
                orchestrator, "_process_with_dashboard", new_callable=AsyncMock
            ) as mock_dash,
        ):
            mock_parsed = MagicMock()
            mock_parsed.url_type = "video"
            mock_parsed.video_id = "vid1"
            mock_parse.return_value = mock_parsed

            mock_dash.return_value = 1  # 1 success

            await orchestrator.run("http://url")

            mock_dash.assert_called_once()
            args = mock_dash.call_args
            assert args[0][0] == ["vid1"]  # Video IDs list
            assert args[1]["is_single_video"] is True
