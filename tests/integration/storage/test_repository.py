"""Tests for DatabaseRepository (SQLAlchemy + Pydantic v2 persistence layer)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import create_engine

from notewise.config import get_cache_db_path
from notewise.storage import CACHE_DB_FILENAME, DatabaseRepository, VideoSchema


if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "test.db"
    r = DatabaseRepository.get_instance(path)
    yield r
    DatabaseRepository.close_instance(path)


class TestReadWrite:
    def test_has_video_false_initially(self, repo):
        assert not repo.has_video("abc123")

    def test_upsert_and_get_video(self, repo):
        repo.upsert_video_cache(
            video_id="abc123",
            title="Test Video",
            duration=120,
            transcript_content="hello world",
            language="en",
            tokens_used=100,
            model="gpt-4o",
        )
        video = repo.get_video("abc123")
        assert isinstance(video, VideoSchema)
        assert video.id == "abc123"
        assert video.title == "Test Video"
        assert video.duration == 120

    def test_has_video_true_after_upsert(self, repo):
        repo.upsert_video_cache(
            video_id="vid1",
            title="T",
            duration=10,
            transcript_content="x",
            language="en",
            tokens_used=1,
            model="m",
        )
        assert repo.has_video("vid1")

    def test_get_cached_video_ids_returns_cached_subset(self, repo):
        for video_id in ("vid1", "vid2"):
            repo.upsert_video_cache(
                video_id=video_id,
                title="T",
                duration=10,
                transcript_content="x",
                language="en",
                tokens_used=1,
                model="m",
            )

        assert repo.get_cached_video_ids(["vid1", "missing", "vid1", "vid2"]) == {
            "vid1",
            "vid2",
        }

    def test_get_video_returns_none_for_missing(self, repo):
        assert repo.get_video("nonexistent") is None

    def test_upsert_updates_existing_video(self, repo):
        for title in ("Old Title", "New Title"):
            repo.upsert_video_cache(
                video_id="vid1",
                title=title,
                duration=60,
                transcript_content="t",
                language="en",
                tokens_used=1,
                model="m",
            )
        video = repo.get_video("vid1")
        assert video.title == "New Title"

    def test_get_transcript_returns_content(self, repo):
        repo.upsert_video_cache(
            video_id="vid1",
            title="T",
            duration=10,
            transcript_content="hello transcript",
            language="English",
            tokens_used=5,
            model="m",
        )
        transcript = repo.get_transcript("vid1")
        assert transcript is not None
        assert transcript.content == "hello transcript"
        assert transcript.language == "English"

    def test_get_run_stats_ordered_by_time(self, repo):
        for _ in range(3):
            repo.upsert_video_cache(
                video_id="vid1",
                title="T",
                duration=10,
                transcript_content="t",
                language="en",
                tokens_used=10,
                model="m",
                cost_usd=0.001,
            )
        stats = repo.get_run_stats("vid1")
        assert len(stats) == 3

    def test_add_export_record(self, repo):
        repo.upsert_video_cache(
            video_id="vid1",
            title="T",
            duration=10,
            transcript_content="t",
            language="en",
            tokens_used=1,
            model="m",
        )
        repo.add_export_record(
            video_id="vid1", format="txt", output_path="/tmp/out.txt"
        )
        records = repo.get_export_records("vid1")
        assert len(records) == 1
        assert records[0].format == "txt"
        assert records[0].output_path == "/tmp/out.txt"


class TestSchemaMigration:
    def test_repair_adds_missing_runstats_columns(self, tmp_path):
        """Older cache DBs missing newer RunStats columns get them added."""
        path = tmp_path / "old.db"
        conn = sqlite3.connect(str(path))
        conn.execute(
            "CREATE TABLE video (id TEXT PRIMARY KEY, title TEXT, duration INTEGER)"
        )
        conn.execute(
            "CREATE TABLE runstats "
            "(id INTEGER PRIMARY KEY, video_id TEXT, tokens_used INTEGER, model TEXT)"
        )
        conn.commit()
        conn.close()

        # Opening via repository should trigger migration
        DatabaseRepository.get_instance(path)
        conn2 = sqlite3.connect(str(path))
        cols = {row[1] for row in conn2.execute("PRAGMA table_info(runstats)")}
        conn2.close()

        assert "prompt_tokens" in cols
        assert "completion_tokens" in cols
        assert "cost_usd" in cols
        assert "transcript_seconds" in cols
        assert "generation_seconds" in cols
        DatabaseRepository.close_instance(path)


class TestCacheDbPath:
    def test_cache_db_path_uses_state_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv("NOTEWISE_HOME", str(tmp_path / ".notewise"))
        path = get_cache_db_path()
        assert path.parent == tmp_path / ".notewise"
        assert path.name == CACHE_DB_FILENAME

    def test_cache_db_path_is_stable(self, monkeypatch, tmp_path):
        monkeypatch.setenv("NOTEWISE_HOME", str(tmp_path / ".notewise"))
        assert get_cache_db_path() == get_cache_db_path()


class TestPruneAgeBackfillCompat:
    """Prune-age behavior against rows backfilled by older cached_at migrations."""

    FROZEN_NOW = datetime(2026, 8, 23, 12, 0, 0, tzinfo=UTC)

    def _make_buggy_backfill_db(self, tmp_path: Path) -> Path:
        """Create a cache DB whose cached_at DEFAULT carries the legacy '+00:00'."""
        path = tmp_path / "backfill.db"
        engine = create_engine(f"sqlite:///{path}")
        boundary = (self.FROZEN_NOW - timedelta(days=30)).strftime(
            "%Y-%m-%d %H:%M:%S.%f"
        )
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "CREATE TABLE video ("
                "id TEXT PRIMARY KEY,"
                "title TEXT NOT NULL,"
                "duration INTEGER NOT NULL,"
                "cached_at DATETIME NOT NULL DEFAULT '2020-01-01 00:00:00+00:00')"
            )
            # 'stale' keeps the raw legacy literal written by the old backfill.
            conn.exec_driver_sql(
                "INSERT INTO video (id, title, duration) VALUES ('stale', 'Stale', 10)"
            )
            conn.exec_driver_sql(
                "INSERT INTO video (id, title, duration) VALUES "
                "('boundary', 'Boundary', 20)"
            )
            conn.exec_driver_sql(
                f"UPDATE video SET cached_at = '{boundary}' WHERE id = 'boundary'"
            )
            conn.exec_driver_sql(
                "INSERT INTO video (id, title, duration) VALUES ('fresh', 'Fresh', 30)"
            )
            conn.exec_driver_sql(
                "UPDATE video SET cached_at = '"
                + self.FROZEN_NOW.strftime("%Y-%m-%d %H:%M:%S.%f")
                + "' WHERE id = 'fresh'"
            )
        engine.dispose()
        return path

    def test_backfilled_row_is_repaired_and_pruned(self, mocker, tmp_path):
        path = self._make_buggy_backfill_db(tmp_path)
        repo = DatabaseRepository.get_instance(path)
        try:
            # migration_3 stripped the legacy suffix during repository init.
            repaired = repo.get_video("stale")
            assert repaired is not None
            assert isinstance(repaired.cached_at, datetime)

            frozen = mocker.patch("notewise.storage.repository.datetime")
            frozen.now.return_value = self.FROZEN_NOW

            deleted = repo.prune_old_entries(older_than_days=30)

            assert deleted == 1
            assert not repo.has_video("stale")
            assert repo.has_video("fresh")
            assert repo.has_video("boundary")
        finally:
            DatabaseRepository.close_instance(path)

    def test_row_exactly_at_cutoff_is_kept(self, mocker, tmp_path):
        path = self._make_buggy_backfill_db(tmp_path)
        repo = DatabaseRepository.get_instance(path)
        try:
            frozen = mocker.patch("notewise.storage.repository.datetime")
            frozen.now.return_value = self.FROZEN_NOW

            deleted = repo.prune_old_entries(older_than_days=30)

            # Only the stale row is pruned; the boundary row sits exactly on
            # the strict '<' cutoff and must survive.
            assert deleted == 1
            assert not repo.has_video("stale")
            assert repo.has_video("boundary")
            assert repo.has_video("fresh")
        finally:
            DatabaseRepository.close_instance(path)

    def test_cache_summary_reads_repaired_rows(self, tmp_path):
        path = self._make_buggy_backfill_db(tmp_path)
        repo = DatabaseRepository.get_instance(path)
        try:
            summary = repo.get_cache_summary()

            assert summary.total_videos == 3
            assert summary.oldest_cached_at == datetime(2020, 1, 1, 0, 0, 0)
            assert summary.newest_cached_at is not None
        finally:
            DatabaseRepository.close_instance(path)
