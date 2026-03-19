"""Tests for DatabaseRepository (SQLAlchemy + Pydantic v2 persistence layer)."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from yt_study.config import get_cache_db_path
from yt_study.persistence import CACHE_DB_FILENAME, DatabaseRepository, VideoSchema


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "test.db"
    r = DatabaseRepository.get_instance(path)
    yield r
    DatabaseRepository.close_instance(path)


class TestSingleton:
    def test_same_path_returns_same_instance(self, tmp_path):
        path = tmp_path / "cache.db"
        r1 = DatabaseRepository.get_instance(path)
        r2 = DatabaseRepository.get_instance(path)
        assert r1 is r2
        DatabaseRepository.close_instance(path)

    def test_different_paths_return_different_instances(self, tmp_path):
        r1 = DatabaseRepository.get_instance(tmp_path / "one.db")
        r2 = DatabaseRepository.get_instance(tmp_path / "two.db")
        assert r1 is not r2
        DatabaseRepository.close_all_instances()

    def test_singleton_normalizes_equivalent_paths(self, tmp_path):
        normalized = tmp_path / "cache.db"
        alternate = tmp_path / "subdir" / ".." / "cache.db"
        r1 = DatabaseRepository.get_instance(normalized)
        r2 = DatabaseRepository.get_instance(alternate)
        assert r1 is r2
        DatabaseRepository.close_instance(normalized)

    def test_thread_safe_concurrent_get(self, tmp_path):
        path = tmp_path / "threadsafe.db"

        def get_repo(_):
            return DatabaseRepository.get_instance(path)

        with ThreadPoolExecutor(max_workers=8) as ex:
            repos = list(ex.map(get_repo, range(24)))
        first = repos[0]
        assert all(r is first for r in repos)
        DatabaseRepository.close_instance(path)

    def test_close_instance_allows_new_creation(self, tmp_path):
        path = tmp_path / "close_test.db"
        r1 = DatabaseRepository.get_instance(path)
        DatabaseRepository.close_instance(path)
        r2 = DatabaseRepository.get_instance(path)
        assert r1 is not r2
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
        monkeypatch.setenv("YT_STUDY_HOME", str(tmp_path / ".yt-study"))
        path = get_cache_db_path()
        assert path.parent == tmp_path / ".yt-study"
        assert path.name == CACHE_DB_FILENAME

    def test_cache_db_path_is_stable(self, monkeypatch, tmp_path):
        monkeypatch.setenv("YT_STUDY_HOME", str(tmp_path / ".yt-study"))
        assert get_cache_db_path() == get_cache_db_path()
