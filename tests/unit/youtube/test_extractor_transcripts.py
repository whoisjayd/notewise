"""Unit tests for native transcript parsing and track selection helpers."""

from __future__ import annotations

import json

from notewise.youtube.extractor import _parsers as tx


class TestSelectTrack:
    def test_select_track_prefers_requested_manual_language(self):
        subtitles = {
            "en": [{"ext": "vtt", "url": "https://x/sub?v=1"}],
            "fr": [{"ext": "json3", "url": "https://x/sub?fmt=json3"}],
        }

        selection = tx.select_track(
            subtitles=subtitles,
            automatic_captions={},
            languages=["fr"],
        )

        assert selection is not None
        assert selection.source == "subtitles"
        assert selection.language_code == "fr"
        assert selection.is_generated is False
        assert selection.track["ext"] == "json3"

    def test_select_track_uses_automatic_when_manual_missing(self):
        selection = tx.select_track(
            subtitles={},
            automatic_captions={"en": [{"ext": "srv3", "url": "https://x/auto.srv3"}]},
            languages=["en"],
            include_automatic=True,
        )

        assert selection is not None
        assert selection.source == "automatic_captions"
        assert selection.is_generated is True

    def test_select_track_returns_none_when_automatic_disabled(self):
        selection = tx.select_track(
            subtitles={},
            automatic_captions={"en": [{"ext": "srv3", "url": "https://x/auto.srv3"}]},
            languages=["en"],
            include_automatic=False,
        )

        assert selection is None

    def test_select_track_matches_language_prefix_variants(self):
        selection = tx.select_track(
            subtitles={"en-US": [{"ext": "vtt", "url": "https://x/sub.vtt"}]},
            automatic_captions={},
            languages=["en"],
        )

        assert selection is not None
        assert selection.language_code == "en-US"

    def test_select_track_logs_when_forced_to_fallback_language(self, monkeypatch):
        subtitles = {"fr": [{"ext": "json3", "url": "https://x/sub?fmt=json3"}]}
        warning_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

        def _warning(*args, **kwargs):
            warning_calls.append((args, kwargs))

        monkeypatch.setattr(tx.logger, "warning", _warning)

        selection = tx.select_track(
            subtitles=subtitles,
            automatic_captions={},
            languages=["en"],
        )

        assert selection is not None
        assert selection.language_code == "fr"
        assert warning_calls == [
            (
                ("transcript.language_fallback",),
                {
                    "requested": ["en"],
                    "available": ["fr"],
                    "selected": "fr",
                },
            )
        ]


class TestParsePayload:
    def test_parse_transcript_payload_json3(self):
        payload = json.dumps(
            {
                "events": [
                    {
                        "tStartMs": 500,
                        "dDurationMs": 1500,
                        "segs": [{"utf8": "Hello"}, {"utf8": " world"}],
                    }
                ]
            }
        )

        segments = tx.parse_transcript_payload(payload, "json3")

        assert len(segments) == 1
        assert segments[0].start == 0.5
        assert segments[0].duration == 1.5
        assert segments[0].text == "Hello world"

    def test_parse_transcript_payload_xml_srv3(self):
        payload = (
            "<transcript><text start='1.2' dur='2.8'>"
            "Hi &amp; <b>all</b></text></transcript>"
        )

        segments = tx.parse_transcript_payload(payload, "srv3")

        assert len(segments) == 1
        assert segments[0].start == 1.2
        assert segments[0].duration == 2.8
        assert segments[0].text == "Hi & all"

    def test_parse_transcript_payload_vtt(self):
        payload = (
            "WEBVTT\n\n"
            "1\n"
            "00:00:01.000 --> 00:00:03.000\n"
            "First line\n\n"
            "2\n"
            "00:00:04.000 --> 00:00:05.500\n"
            "Second <i>line</i>\n"
        )

        segments = tx.parse_transcript_payload(payload, "vtt")

        assert len(segments) == 2
        assert segments[0].text == "First line"
        assert segments[1].duration == 1.5
        assert segments[1].text == "Second line"

    def test_parse_transcript_payload_unknown_ext_fallback(self):
        payload = "<transcript><text t='1000' d='2000'>Fallback</text></transcript>"

        segments = tx.parse_transcript_payload(payload, "unknown")

        assert len(segments) == 1
        assert segments[0].start == 1.0
        assert segments[0].duration == 2.0
        assert segments[0].text == "Fallback"

    def test_parse_transcript_payload_returns_empty_when_unparseable(self):
        segments = tx.parse_transcript_payload("not-json-or-xml", "unknown")
        assert segments == []

    def test_parse_transcript_payload_ignores_wrong_json_shape(self):
        segments = tx.parse_transcript_payload("[]", "unknown")
        assert segments == []


class TestHelpers:
    def test_transcript_segment_to_dict(self):
        segment = tx.TranscriptSegment(start=1.0, duration=2.0, text="hello")
        assert segment.to_dict() == {"start": 1.0, "duration": 2.0, "text": "hello"}

    def test_pick_best_track_prefers_known_ext_priority(self):
        best = tx._pick_best_track(
            [
                {"url": "https://x/sub.vtt"},
                {"url": "https://x/sub?fmt=json3"},
                {"url": "https://x/sub.srv3"},
            ]
        )

        assert best is not None
        assert tx._infer_ext(best).lower() == "json3"

    def test_infer_ext_from_explicit_and_url(self):
        assert tx._infer_ext({"ext": "TTML"}) == "TTML"
        assert tx._infer_ext({"url": "https://x/sub?fmt=srv1"}) == "srv1"
        assert tx._infer_ext({"url": "https://x/sub.vtt"}) == "vtt"
        assert tx._infer_ext({"url": "https://x/nohint"}) == "unknown"

    def test_parse_vtt_time_variants(self):
        assert tx._parse_vtt_time("01:02:03.5") == 3723.5
        assert tx._parse_vtt_time("02:03.5") == 123.5
        assert tx._parse_vtt_time("bogus") == 0.0

    def test_parse_time_or_seconds_paths(self):
        assert tx._parse_time_or_seconds("1:30", None, scale_ms=True) == 90.0
        assert tx._parse_time_or_seconds(None, "2500", scale_ms=True) == 2.5
        assert tx._parse_time_or_seconds("2.75", None, scale_ms=True) == 2.75
        assert tx._parse_time_or_seconds(None, None, scale_ms=True) == 0.0

    def test_local_tag_and_clean_text(self):
        assert tx._local_tag("{urn:x}text") == "text"
        assert tx._local_tag("text") == "text"
        assert tx._clean_text(" a\n<b>Hi</b>\r&amp;  all ") == "a Hi & all"
