"""Tests for SQLite cache database manager."""

from yt_study.db import DatabaseManager


def test_database_manager_singleton_for_same_path(tmp_path):
    """Same db path should return the same singleton instance."""
    db_path = tmp_path / ".yt_study_cache.db"
    manager_one = DatabaseManager.get_instance(db_path)
    manager_two = DatabaseManager.get_instance(db_path)

    assert manager_one is manager_two


def test_database_manager_singleton_normalizes_equivalent_paths(tmp_path):
    """Equivalent paths should map to the same singleton instance."""
    normalized = tmp_path / "cache.db"
    alternate = tmp_path / "subdir" / ".." / "cache.db"

    manager_one = DatabaseManager.get_instance(normalized)
    manager_two = DatabaseManager.get_instance(alternate)

    assert manager_one is manager_two


def test_database_manager_uses_distinct_instances_per_path(tmp_path):
    """Different db paths should not share singleton instances."""
    manager_one = DatabaseManager.get_instance(tmp_path / "one.db")
    manager_two = DatabaseManager.get_instance(tmp_path / "two.db")

    assert manager_one is not manager_two


def test_upsert_video_cache_persists_video_transcript_and_run_stats(tmp_path):
    """Upsert should persist core records for a processed video."""
    db = DatabaseManager.get_instance(tmp_path / "cache.db")

    db.upsert_video_cache(
        video_id="video-1",
        title="Video One",
        duration=120,
        transcript_content="hello world transcript",
        language="en",
        tokens_used=42,
        model="gemini/gemini-2.0-flash",
    )

    assert db.has_video("video-1") is True
    video = db.get_video("video-1")
    transcript = db.get_transcript("video-1")
    stats = db.get_run_stats("video-1")

    assert video is not None
    assert video.title == "Video One"
    assert video.duration == 120
    assert transcript is not None
    assert transcript.content == "hello world transcript"
    assert transcript.language == "en"
    assert len(stats) == 1
    assert stats[0].tokens_used == 42


def test_upsert_video_cache_updates_existing_video_and_transcript(tmp_path):
    """Upsert should update metadata/transcript while appending run stats."""
    db = DatabaseManager.get_instance(tmp_path / "cache.db")

    db.upsert_video_cache(
        video_id="video-1",
        title="Old Title",
        duration=100,
        transcript_content="old transcript",
        language="en",
        tokens_used=10,
        model="old-model",
    )
    db.upsert_video_cache(
        video_id="video-1",
        title="New Title",
        duration=220,
        transcript_content="new transcript",
        language="hi",
        tokens_used=30,
        model="new-model",
    )

    video = db.get_video("video-1")
    transcript = db.get_transcript("video-1")
    stats = db.get_run_stats("video-1")

    assert video is not None
    assert video.title == "New Title"
    assert video.duration == 220
    assert transcript is not None
    assert transcript.content == "new transcript"
    assert transcript.language == "hi"
    assert len(stats) == 2
    assert any(row.model == "new-model" for row in stats)


def test_database_manager_close_instance_evicts_singleton(tmp_path):
    """close_instance should dispose and recreate singleton cleanly."""
    db_path = tmp_path / "cache.db"
    manager_one = DatabaseManager.get_instance(db_path)

    DatabaseManager.close_instance(db_path)
    manager_two = DatabaseManager.get_instance(db_path)

    assert manager_one is not manager_two
