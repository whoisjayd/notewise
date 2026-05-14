from __future__ import annotations

from pathlib import Path

import pytest
import vcr

from notewise.errors import ExtractionError
from notewise.youtube.extractor.client import YouTubeExtractorClient


def test_youtube_caption_fetch_replays_from_sanitized_cassette() -> None:
    cassette = Path(__file__).with_name("cassettes") / "caption_fetch.yaml"
    caption_url = "http://youtube.test/api/timedtext?v=VIDEO_ID&lang=en"
    video = {
        "id": "VIDEO_ID",
        "title": "Replay Video",
        "webpage_url": "https://www.youtube.com/watch?v=VIDEO_ID",
        "subtitles": {
            "en": [
                {
                    "ext": "xml",
                    "url": caption_url,
                    "name": "English",
                }
            ]
        },
        "automatic_captions": {},
        "_innertube_api_key": None,
        "_ytcfg": {},
    }

    with vcr.use_cassette(
        str(cassette),
        filter_headers=["authorization", "cookie", "host", "set-cookie"],
        record_mode="none",
    ):
        payload = YouTubeExtractorClient().transcript_from_video_data(
            "https://www.youtube.com/watch?v=VIDEO_ID",
            video,
            languages=["en"],
        )

    assert payload["source"] == "subtitles"
    assert payload["segments"][0]["text"] == "Replay safe transcript"


def test_youtube_transcript_parser_replays_json3_caption_cassette() -> None:
    cassette = Path(__file__).with_name("cassettes") / "caption_fetch_json3.yaml"
    caption_url = "http://youtube.test/api/timedtext?v=VIDEO_ID&lang=en&fmt=json3"
    video = {
        "id": "VIDEO_ID",
        "title": "Replay Video",
        "webpage_url": "https://www.youtube.com/watch?v=VIDEO_ID",
        "subtitles": {
            "en": [
                {
                    "ext": "json3",
                    "url": caption_url,
                    "name": "English",
                }
            ]
        },
        "automatic_captions": {},
        "_innertube_api_key": None,
        "_ytcfg": {},
    }

    with vcr.use_cassette(
        str(cassette),
        filter_headers=["authorization", "cookie", "host", "set-cookie"],
        record_mode="none",
    ):
        payload = YouTubeExtractorClient().transcript_from_video_data(
            "https://www.youtube.com/watch?v=VIDEO_ID",
            video,
            languages=["en"],
        )

    assert payload["source"] == "subtitles"
    assert payload["language_code"] == "en"
    assert payload["segment_count"] == 1
    assert payload["segments"][0]["text"] == "Replay JSON3 caption"


def test_youtube_video_metadata_replays_sanitized_watch_page_cassette() -> None:
    cassette = Path(__file__).with_name("cassettes") / "video_watch_page.yaml"

    with vcr.use_cassette(
        str(cassette),
        filter_headers=["authorization", "cookie", "host", "set-cookie"],
        record_mode="none",
    ):
        payload = YouTubeExtractorClient().metadata("SANITIZED_VIDEO_ID")

    assert payload["type"] == "video"
    assert payload["id"] == "SANITIZED_VIDEO_ID"
    assert payload["title"] == "Replay Metadata Video"
    assert payload["chapters_count"] == 2
    assert payload["subtitle_languages"] == ["en"]
    assert payload["data"]["view_count"] == 1234


def test_youtube_replay_mode_rejects_uncassetted_requests() -> None:
    cassette = Path(__file__).with_name("cassettes") / "caption_fetch.yaml"

    with (
        vcr.use_cassette(
            str(cassette),
            filter_headers=["authorization", "cookie", "host", "set-cookie"],
            record_mode="none",
        ),
        pytest.raises(ExtractionError, match="Can't overwrite existing cassette"),
    ):
        YouTubeExtractorClient()._fetch_text(
            "http://youtube.test/api/timedtext?v=UNCASSETTED&lang=en"
        )
