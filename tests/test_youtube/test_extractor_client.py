"""Unit tests for the native YouTube extractor client."""

from __future__ import annotations

import http.cookiejar

import pytest

from yt_study.errors import ExtractionError as ExtractorError
from yt_study.infrastructure.youtube.extractor.async_client import (
    AsyncYouTubeExtractorClient,
)
from yt_study.infrastructure.youtube.extractor.client import (
    YouTubeExtractorClient as ExtractorClient,
)


def _make_cookie(
    name: str, value: str, domain: str = ".youtube.com"
) -> http.cookiejar.Cookie:
    return http.cookiejar.Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain=domain,
        domain_specified=True,
        domain_initial_dot=domain.startswith("."),
        path="/",
        path_specified=True,
        secure=False,
        expires=None,
        discard=True,
        comment=None,
        comment_url=None,
        rest={},
        rfc2109=False,
    )


class TestCookieHandling:
    def test_load_cookie_jar_missing_file_raises(self):
        client = ExtractorClient()

        with pytest.raises(ExtractorError, match="Cookie file not found"):
            client._load_cookie_jar("does-not-exist-cookies.txt")

    def test_load_cookie_jar_normalizes_session_cookie(self, tmp_path):
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text(
            "# Netscape HTTP Cookie File\n"
            ".youtube.com\tTRUE\t/\tFALSE\t0\tSAPISID\tabc123\n",
            encoding="utf-8",
        )

        client = ExtractorClient()
        jar = client._load_cookie_jar(str(cookie_file))

        cookies = list(jar)
        assert len(cookies) == 1
        assert cookies[0].name == "SAPISID"
        assert cookies[0].expires is None
        assert cookies[0].discard is True

    def test_youtube_cookies_filters_non_youtube_domains(self):
        client = ExtractorClient()
        jar = http.cookiejar.MozillaCookieJar()
        jar.set_cookie(_make_cookie("SAPISID", "yt", domain=".youtube.com"))
        jar.set_cookie(_make_cookie("OTHER", "ignore", domain=".google.com"))
        client._cookie_jar = jar

        assert client._youtube_cookies() == {"SAPISID": "yt"}


class TestAuthHeaders:
    def test_get_sid_authorization_header_builds_all_present_schemes(self, monkeypatch):
        client = ExtractorClient()
        jar = http.cookiejar.MozillaCookieJar()
        jar.set_cookie(_make_cookie("SAPISID", "sapi"))
        jar.set_cookie(_make_cookie("__Secure-1PAPISID", "onep"))
        jar.set_cookie(_make_cookie("__Secure-3PAPISID", "threep"))
        client._cookie_jar = jar
        monkeypatch.setattr(
            "yt_study.infrastructure.youtube.extractor.client.time.time", lambda: 123.0
        )

        header = client._get_sid_authorization_header(
            origin="https://www.youtube.com",
            user_session_id="user-session",
        )

        assert header is not None
        assert "SAPISIDHASH" in header
        assert "SAPISID1PHASH" in header
        assert "SAPISID3PHASH" in header

    def test_generate_cookie_auth_headers_uses_ytcfg_and_cookies(self):
        client = ExtractorClient()
        jar = http.cookiejar.MozillaCookieJar()
        jar.set_cookie(_make_cookie("SAPISID", "abc"))
        client._cookie_jar = jar

        ytcfg = {
            "DATASYNC_ID": "delegated||user-session",
            "SESSION_INDEX": "2",
            "LOGGED_IN": True,
        }

        headers = client._generate_cookie_auth_headers(
            ytcfg=ytcfg,
            origin="https://www.youtube.com",
        )

        assert headers["X-Goog-PageId"] == "delegated"
        assert headers["X-Goog-AuthUser"] == "2"
        assert "Authorization" in headers
        assert headers["X-Origin"] == "https://www.youtube.com"
        assert headers["X-Youtube-Bootstrap-Logged-In"] == "true"


class TestUrlParsing:
    @pytest.mark.parametrize(
        ("target", "video_id"),
        [
            ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ],
    )
    def test_extract_video_id_variants(self, target, video_id):
        assert ExtractorClient._extract_video_id(target) == video_id

    def test_extract_video_id_invalid_url_raises(self):
        with pytest.raises(ExtractorError, match="Unable to determine video id"):
            ExtractorClient._extract_video_id(
                "https://www.youtube.com/watch?list=PL123"
            )

    @pytest.mark.parametrize(
        ("target", "expected"),
        [
            ("https://www.youtube.com/playlist?list=PL123", True),
            ("https://www.youtube.com/watch?list=PL123", True),
            ("https://www.youtube.com/watch?v=abc&list=PL123", False),
            ("https://www.youtube.com/watch?v=abc", False),
            ("abc123", False),
        ],
    )
    def test_looks_like_playlist_url(self, target, expected):
        assert ExtractorClient._looks_like_playlist_url(target) is expected


class TestPlaylistAndParsingHelpers:
    def test_extract_playlist_entries_deduplicates_and_maps_fields(self):
        client = ExtractorClient()
        data = {
            "items": [
                {
                    "playlistVideoRenderer": {
                        "videoId": "id1",
                        "title": {"simpleText": "Video 1"},
                        "lengthText": {"simpleText": "1:23"},
                        "shortBylineText": {"simpleText": "Uploader"},
                    }
                },
                {
                    "playlistVideoRenderer": {
                        "videoId": "id1",
                        "title": {"simpleText": "Duplicate"},
                        "lengthText": {"simpleText": "1:23"},
                        "shortBylineText": {"simpleText": "Uploader"},
                    }
                },
                {
                    "playlistVideoRenderer": {
                        "videoId": "id2",
                        "title": {"simpleText": "Video 2"},
                        "lengthText": {"simpleText": "2:00"},
                    }
                },
            ]
        }

        entries = client._extract_playlist_entries(data, seen=set())

        by_id = {entry["id"]: entry for entry in entries}

        assert set(by_id.keys()) == {"id1", "id2"}
        assert by_id["id1"]["duration"] == 83
        assert by_id["id1"]["uploader"] == "Uploader"

    def test_extract_continuation_token_checks_supported_shapes(self):
        client = ExtractorClient()

        from_continuation_command = client._extract_continuation_token(
            {"continuationCommand": {"token": "abc"}}
        )
        from_next = client._extract_continuation_token(
            {"nextContinuationData": {"continuation": "def"}}
        )
        from_reload = client._extract_continuation_token(
            {"reloadContinuationData": {"continuation": "ghi"}}
        )

        assert from_continuation_command == "abc"
        assert from_next == "def"
        assert from_reload == "ghi"

    def test_extract_json_by_markers_returns_first_valid_dict(self):
        client = ExtractorClient()
        text = 'noise var ytInitialData = {"a": 1}; ytcfg.set({"b": 2});'

        parsed = client._extract_json_by_markers(
            text, ("var ytInitialData = ", "ytcfg.set(")
        )

        assert parsed == {"a": 1}

    def test_extract_description_chapters_requires_multiple_timestamps(self):
        client = ExtractorClient()
        description = "00:00 Intro\n01:30 Middle\n03:00 End"

        chapters = client._extract_description_chapters(description, duration=240)

        assert len(chapters) == 3
        assert chapters[0]["title"] == "Intro"
        assert chapters[0]["start_time"] == 0.0
        assert chapters[-1]["end_time"] == 240.0


class TestAvailability:
    @pytest.mark.parametrize(
        ("playability", "expected"),
        [
            ({"status": "OK"}, "public"),
            (
                {"status": "LOGIN_REQUIRED", "reason": "This is a private video"},
                "private",
            ),
            (
                {"status": "LOGIN_REQUIRED", "reason": "Sign in to confirm your age"},
                "login_required",
            ),
            (
                {"status": "ERROR", "reason": "This video is age restricted"},
                "age_restricted",
            ),
            ({"status": "ERROR", "reason": "Something else"}, "unavailable"),
        ],
    )
    def test_availability_mapping(self, playability, expected):
        assert ExtractorClient._availability(playability) == expected


class TestHighLevelClientCommands:
    def test_metadata_for_video_payload_shape(self, monkeypatch):
        client = ExtractorClient()
        monkeypatch.setattr(client, "_looks_like_playlist_url", lambda _: False)
        monkeypatch.setattr(
            client,
            "_extract_video",
            lambda _: {
                "id": "vid1",
                "title": "Video One",
                "webpage_url": "https://youtube/watch?v=vid1",
                "chapters": [{"start_time": 0.0, "end_time": 30.0, "title": "Intro"}],
                "subtitles": {"en": [{"ext": "json3", "url": "x"}]},
                "automatic_captions": {"fr": [{"ext": "json3", "url": "x"}]},
            },
        )

        data = client.metadata("vid1")

        assert data["type"] == "video"
        assert data["id"] == "vid1"
        assert data["chapters_count"] == 1
        assert data["subtitle_languages"] == ["en"]
        assert data["automatic_caption_languages"] == ["fr"]

    def test_metadata_for_playlist_payload_shape(self, monkeypatch):
        client = ExtractorClient()
        monkeypatch.setattr(client, "_looks_like_playlist_url", lambda _: True)
        monkeypatch.setattr(
            client,
            "_extract_playlist",
            lambda _target, include_entries: {
                "id": "pl1",
                "title": "Playlist One",
                "webpage_url": "https://youtube/playlist?list=pl1",
                "description": "desc",
                "uploader": "owner",
                "channel": "owner",
                "view_count": 12,
                "availability": "public",
                "thumbnails": [],
                "playlist_count": 3,
                "entries": [] if not include_entries else [{"id": "x"}],
            },
        )

        data = client.metadata("https://www.youtube.com/playlist?list=pl1")

        assert data["type"] == "playlist"
        assert data["id"] == "pl1"
        assert data["data"]["playlist_count"] == 3

    def test_chapters_maps_indices(self, monkeypatch):
        client = ExtractorClient()
        monkeypatch.setattr(
            client,
            "_extract_video",
            lambda _: {
                "id": "v1",
                "title": "T",
                "webpage_url": "u",
                "chapters": [
                    {"title": "A", "start_time": 0.0, "end_time": 10.0},
                    {"title": "B", "start_time": 10.0, "end_time": 20.0},
                ],
            },
        )

        payload = client.chapters("v1")

        assert payload["count"] == 2
        assert payload["chapters"][0]["index"] == 1
        assert payload["chapters"][1]["title"] == "B"

    def test_playlist_payload_count(self, monkeypatch):
        client = ExtractorClient()
        monkeypatch.setattr(
            client,
            "_extract_playlist",
            lambda _target, include_entries: {
                "id": "pl1",
                "title": "P",
                "description": "",
                "uploader": "u",
                "channel": "u",
                "webpage_url": "w",
                "playlist_count": 2,
                "entries": [{"id": "v1"}, {"id": "v2"}] if include_entries else [],
            },
        )

        payload = client.playlist("pl1")

        assert payload["type"] == "playlist"
        assert payload["count"] == 2
        assert payload["entries"][0]["id"] == "v1"

    def test_transcript_raises_when_track_fetch_fails_without_fallback(
        self, monkeypatch
    ):
        client = ExtractorClient()
        monkeypatch.setattr(
            client,
            "_extract_video",
            lambda _: {
                "id": "v1",
                "title": "T",
                "webpage_url": "u",
                "subtitles": {"en": [{"ext": "json3", "url": "https://x/sub"}]},
                "automatic_captions": {},
                "_innertube_api_key": None,
                "_ytcfg": {},
            },
        )
        monkeypatch.setattr(
            client,
            "_fetch_text",
            lambda _url: (_ for _ in ()).throw(RuntimeError("boom")),
        )

        with pytest.raises(ExtractorError, match="Transcript extraction failed"):
            client.transcript("v1", ["en"])

    def test_transcript_uses_innertube_fallback(self, monkeypatch):
        client = ExtractorClient()
        monkeypatch.setattr(
            client,
            "_extract_video",
            lambda _: {
                "id": "v1",
                "title": "T",
                "webpage_url": "u",
                "subtitles": {},
                "automatic_captions": {},
                "_innertube_api_key": "k",
                "_ytcfg": {"a": 1},
            },
        )
        monkeypatch.setattr(
            client,
            "_transcript_via_innertube_player",
            lambda **_kwargs: {
                "source": "innertube:player",
                "segments": [{"text": "ok", "start": 0.0, "duration": 1.0}],
                "language_code": "en",
                "is_generated": True,
                "track": {"ext": "json3", "name": "English", "url": "u"},
            },
        )

        payload = client.transcript("v1", ["en"])

        assert payload["segment_count"] == 1
        assert payload["source"] == "innertube:player"
        assert payload["is_generated"] is True


class TestAsyncExtractorClient:
    @pytest.mark.asyncio
    async def test_video_metadata_full_forwards_target_unchanged(self, monkeypatch):
        captured: dict[str, str] = {}

        def _fake_extract_video(_self, target: str):
            captured["target"] = target
            return {"id": "vid1"}

        monkeypatch.setattr(ExtractorClient, "_extract_video", _fake_extract_video)
        client = AsyncYouTubeExtractorClient()

        payload = await client.video_metadata_full(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )

        assert payload == {"id": "vid1"}
        assert captured["target"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


class TestLowLevelHelpers:
    def test_extract_json_by_markers_skips_invalid_json(self):
        client = ExtractorClient()
        text = 'var ytInitialData = {not-valid}; ytcfg.set({"ok": true});'

        parsed = client._extract_json_by_markers(
            text, ("var ytInitialData = ", "ytcfg.set(")
        )

        assert parsed == {"ok": True}

    def test_extract_balanced_json_none_when_unclosed(self):
        assert ExtractorClient._extract_balanced_json('abc {"x":1', 4) is None

    def test_extract_context_defaults_and_overrides(self):
        client = ExtractorClient()
        context = client._extract_context(
            ytcfg={"INNERTUBE_CONTEXT": {"client": {"clientName": "WEB"}}},
            client_override={"clientVersion": "9.9", "userAgent": "UA"},
        )

        assert context["client"]["clientName"] == "WEB"
        assert context["client"]["clientVersion"] == "9.9"
        assert context["client"]["userAgent"] == "UA"
        assert context["client"]["hl"] == "en"

    def test_extract_context_recovers_from_invalid_structures(self):
        client = ExtractorClient()
        context = client._extract_context(
            ytcfg={"INNERTUBE_CONTEXT": "bad"},
            client_override=None,
        )

        assert context["client"]["clientName"] == "WEB"
        assert "clientVersion" in context["client"]

    def test_generate_api_headers_sets_visitor_and_defaults(self):
        client = ExtractorClient()
        headers = client._generate_api_headers(
            ytcfg={
                "INNERTUBE_CLIENT_NAME": 3,
                "VISITOR_DATA": "visitor-id",
            },
            context={"client": {}},
        )

        assert headers["X-YouTube-Client-Name"] == "3"
        assert headers["X-Goog-Visitor-Id"] == "visitor-id"
        assert "User-Agent" in headers

    def test_extract_session_index_invalid(self):
        client = ExtractorClient()
        assert client._extract_session_index({"SESSION_INDEX": "x"}) is None

    def test_parse_data_sync_id_shapes(self):
        client = ExtractorClient()
        assert client._parse_data_sync_id("deleg||user") == ("deleg", "user")
        assert client._parse_data_sync_id("just-user") == (None, "just-user")
        assert client._parse_data_sync_id(None) == (None, None)

    def test_extract_user_and_delegated_session_ids(self):
        client = ExtractorClient()

        ytcfg = {"DATASYNC_ID": "deleg||user"}
        assert client._extract_user_session_id(ytcfg) == "user"
        assert client._extract_delegated_session_id(ytcfg) == "deleg"

        ytcfg2 = {"USER_SESSION_ID": "u1", "DELEGATED_SESSION_ID": "d1"}
        assert client._extract_user_session_id(ytcfg2) == "u1"
        assert client._extract_delegated_session_id(ytcfg2) == "d1"

    def test_make_sid_authorization_includes_user_tag(self, monkeypatch):
        monkeypatch.setattr(
            "yt_study.infrastructure.youtube.extractor.client.time.time", lambda: 9.0
        )
        header = ExtractorClient._make_sid_authorization(
            "SAPISIDHASH",
            "sid",
            "https://www.youtube.com",
            {"u": "user"},
        )
        assert header.startswith("SAPISIDHASH ")
        assert header.endswith("_u")

    def test_get_sid_authorization_header_none_without_cookies(self):
        client = ExtractorClient()
        assert (
            client._get_sid_authorization_header("https://www.youtube.com", None)
            is None
        )

    def test_get_sid_cookies_prefers_secure_3p_for_main_slot(self):
        client = ExtractorClient()
        jar = http.cookiejar.MozillaCookieJar()
        jar.set_cookie(_make_cookie("__Secure-1PAPISID", "onep"))
        jar.set_cookie(_make_cookie("__Secure-3PAPISID", "threep"))
        client._cookie_jar = jar

        assert client._get_sid_cookies() == ("threep", "onep", "threep")

    def test_scalar_helpers(self):
        assert (
            ExtractorClient._with_fmt_json3("https://x/sub?v=1")
            == "https://x/sub?v=1&fmt=json3"
        )
        assert ExtractorClient._to_int("12") == 12
        assert ExtractorClient._to_int("not-int") is None
        assert ExtractorClient._parse_duration("1:02:03") == 3723
        assert ExtractorClient._parse_duration("2:03") == 123
        assert ExtractorClient._parse_duration("45") == 45
        assert ExtractorClient._parse_duration("x:y") is None
        assert ExtractorClient._best_thumbnail([]) is None
        assert (
            ExtractorClient._best_thumbnail(
                [
                    {"url": "a", "width": 100, "height": 100},
                    {"url": "b", "width": 200, "height": 90},
                ]
            )
            == "b"
        )

    def test_text_and_date_helpers(self):
        assert ExtractorClient._get_text("hello") == "hello"
        assert ExtractorClient._get_text({"simpleText": "x"}) == "x"
        assert (
            ExtractorClient._get_text({"runs": [{"text": "a"}, {"text": "b"}]}) == "ab"
        )
        assert ExtractorClient._get_text({"text": "z"}) == "z"
        assert ExtractorClient._get_text({"other": 1}) is None

        assert ExtractorClient._date_to_yyyymmdd("2025-01-02") == "20250102"
        assert ExtractorClient._date_to_yyyymmdd("bad") is None
        assert ExtractorClient._iso_to_unix("2025-01-02") is not None
        assert ExtractorClient._iso_to_unix("bad") is None

    def test_parse_count_and_key_helpers(self):
        assert ExtractorClient._parse_count("1,234 views") == 1234
        assert ExtractorClient._parse_count("none") is None

        node = {"a": {"target": 1}, "b": [{"target": 2}, {"x": {"target": 3}}]}
        found = ExtractorClient._find_key(node, "target")
        assert len(found) == 3
        assert ExtractorClient._first_key(node, "target") in {1, 2, 3}


class TestDeeperExtractorBranches:
    def test_extract_playlist_id_and_error(self):
        assert (
            ExtractorClient._extract_playlist_id(
                "https://www.youtube.com/playlist?list=PL123"
            )
            == "PL123"
        )
        with pytest.raises(ExtractorError, match="Unable to determine playlist id"):
            ExtractorClient._extract_playlist_id("https://www.youtube.com/playlist")

    def test_extract_playlist_entries_paginated_without_api_key(self):
        client = ExtractorClient()
        data = {
            "playlistVideoRenderer": {
                "videoId": "id1",
                "title": {"simpleText": "Title"},
            }
        }

        entries = client._extract_playlist_entries_paginated(
            data, api_key=None, ytcfg=None
        )

        assert len(entries) == 1
        assert entries[0]["id"] == "id1"

    def test_extract_playlist_entries_paginated_stops_on_repeat_token(
        self, monkeypatch
    ):
        client = ExtractorClient()
        data = {
            "continuationCommand": {"token": "tok1"},
            "playlistVideoRenderer": {
                "videoId": "id1",
                "title": {"simpleText": "Title"},
            },
        }
        monkeypatch.setattr(
            client,
            "_call_innertube",
            lambda **_kwargs: {
                "continuationCommand": {"token": "tok1"},
                "playlistVideoRenderer": {
                    "videoId": "id2",
                    "title": {"simpleText": "Title2"},
                },
            },
        )

        entries = client._extract_playlist_entries_paginated(
            data, api_key="k", ytcfg={}
        )

        assert {entry["id"] for entry in entries} == {"id1", "id2"}

    def test_build_subtitles_splits_manual_and_asr(self):
        client = ExtractorClient()
        subtitles, automatic = client._build_subtitles(
            {
                "captionTracks": [
                    {
                        "languageCode": "en",
                        "baseUrl": "https://x/sub?foo=1",
                        "name": {"simpleText": "English"},
                    },
                    {
                        "languageCode": "fr",
                        "baseUrl": "https://x/sub?bar=1",
                        "name": {"simpleText": "French"},
                        "kind": "asr",
                    },
                    "invalid",
                ]
            }
        )

        assert "en" in subtitles
        assert "fr" in automatic
        assert subtitles["en"][0]["url"].endswith("fmt=json3")

    def test_extract_chapters_from_renderers(self):
        client = ExtractorClient()
        data = {
            "chapterRenderer": {
                "timeRangeStartMillis": 0,
                "title": {"simpleText": "Intro"},
            },
            "macroMarkersListItemRenderer": {
                "timeDescription": {"simpleText": "01:00"},
                "title": {"simpleText": "Deep"},
            },
        }

        chapters = client._extract_chapters(data, duration=120)

        assert len(chapters) == 2
        assert chapters[0]["title"] == "Intro"
        assert chapters[1]["start_time"] == 60.0

    def test_extract_chapters_returns_empty_for_single_marker(self):
        client = ExtractorClient()
        chapters = client._extract_chapters(
            {
                "chapterRenderer": {
                    "timeRangeStartMillis": 0,
                    "title": {"simpleText": "Only"},
                }
            },
            duration=100,
        )
        assert chapters == []

    def test_extract_player_response_raises_when_missing(self):
        client = ExtractorClient()
        with pytest.raises(
            ExtractorError, match="Unable to parse ytInitialPlayerResponse"
        ):
            client._extract_player_response("<html></html>")

    def test_extract_innertube_api_key_paths(self):
        client = ExtractorClient()
        assert (
            client._extract_innertube_api_key("", {"INNERTUBE_API_KEY": "abc"}) == "abc"
        )
        assert (
            client._extract_innertube_api_key('"INNERTUBE_API_KEY":"xyz"', None)
            == "xyz"
        )
        assert client._extract_innertube_api_key("", None) is None

    def test_fetch_json_unexpected_type_raises(self, monkeypatch):
        client = ExtractorClient()

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b"[]"

        class _Opener:
            def open(self, req, timeout=30):
                _ = (req, timeout)
                return _Resp()

        monkeypatch.setattr(client, "_opener", _Opener())

        with pytest.raises(ExtractorError, match="Unexpected JSON response type"):
            client._fetch_json("https://x", {"a": 1}, {"h": "v"})

    def test_load_cookie_jar_invalid_file_raises(self, tmp_path):
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("not a netscape cookie file", encoding="utf-8")
        client = ExtractorClient()

        with pytest.raises(ExtractorError, match="Failed to load cookie file"):
            client._load_cookie_jar(str(cookie_file))

    def test_player_response_from_innertube_returns_none_on_error(self, monkeypatch):
        client = ExtractorClient()
        monkeypatch.setattr(
            client,
            "_call_innertube",
            lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
        )

        assert client._player_response_from_innertube("vid", "k", {}) is None

    def test_call_innertube_composes_payload_and_headers(self, monkeypatch):
        client = ExtractorClient()
        captured = {}
        monkeypatch.setattr(
            client,
            "_extract_context",
            lambda *_args, **_kwargs: {"client": {"clientName": "WEB"}},
        )
        monkeypatch.setattr(
            client, "_generate_api_headers", lambda *_args, **_kwargs: {"X": "Y"}
        )

        def _fake_fetch_json(url, payload, headers):
            captured["url"] = url
            captured["payload"] = payload
            captured["headers"] = headers
            return {"ok": True}

        monkeypatch.setattr(client, "_fetch_json", _fake_fetch_json)

        result = client._call_innertube("player", "api", {}, {"videoId": "v1"})

        assert result == {"ok": True}
        assert "player?key=api" in captured["url"]
        assert captured["payload"]["videoId"] == "v1"
        assert captured["headers"]["Content-Type"] == "application/json"

    def test_transcript_via_innertube_player_success(self, monkeypatch):
        client = ExtractorClient()
        monkeypatch.setattr(
            client,
            "_call_innertube",
            lambda **_kwargs: {
                "captions": {
                    "playerCaptionsTracklistRenderer": {
                        "captionTracks": [
                            {
                                "languageCode": "en",
                                "baseUrl": "https://x/sub?foo=1",
                                "name": {"simpleText": "English"},
                            }
                        ]
                    }
                }
            },
        )
        monkeypatch.setattr(
            client,
            "_fetch_text",
            lambda _url: (
                '{"events":[{"tStartMs":0,"dDurationMs":1000,"segs":[{"utf8":"ok"}]}]}'
            ),
        )

        fallback = client._transcript_via_innertube_player(
            video_id="v1",
            api_key="k",
            ytcfg={},
            languages=["en"],
            include_automatic=True,
        )

        assert fallback is not None
        assert fallback["language_code"] == "en"
        assert fallback["segments"][0]["text"] == "ok"

    def test_transcript_native_selection_success_path(self, monkeypatch):
        client = ExtractorClient()
        monkeypatch.setattr(
            client,
            "_extract_video",
            lambda _target: {
                "id": "v1",
                "title": "T",
                "webpage_url": "u",
                "subtitles": {
                    "en": [
                        {
                            "ext": "json3",
                            "url": "https://x/sub?fmt=json3",
                            "name": "English",
                        }
                    ]
                },
                "automatic_captions": {},
                "_innertube_api_key": None,
                "_ytcfg": {},
            },
        )
        monkeypatch.setattr(
            client,
            "_fetch_text",
            lambda _url: (
                '{"events":[{"tStartMs":0,"dDurationMs":1200,"segs":[{"utf8":"native"}]}]}'
            ),
        )

        payload = client.transcript("v1", ["en"])

        assert payload["source"] == "subtitles"
        assert payload["segment_count"] == 1
        assert payload["segments"][0]["text"] == "native"

    def test_extract_video_full_mapping_with_innertube_caption_fallback(
        self, monkeypatch
    ):
        client = ExtractorClient()
        player = {
            "videoDetails": {
                "title": "Video",
                "lengthSeconds": "120",
                "shortDescription": "00:00 Intro\n01:00 End",
                "viewCount": "42",
                "author": "Uploader",
                "channelId": "chan1",
                "isLive": False,
                "keywords": ["k1"],
                "thumbnail": {
                    "thumbnails": [{"url": "t1", "width": 100, "height": 100}]
                },
            },
            "microformat": {
                "playerMicroformatRenderer": {
                    "uploadDate": "2025-01-01",
                    "publishDate": "2025-01-02",
                    "category": "Education",
                }
            },
            "captions": {},
            "playabilityStatus": {"status": "OK"},
        }
        api_player = {
            "captions": {
                "playerCaptionsTracklistRenderer": {
                    "captionTracks": [
                        {
                            "languageCode": "en",
                            "baseUrl": "https://x/sub?foo=1",
                            "name": {"simpleText": "English"},
                        }
                    ]
                }
            }
        }

        monkeypatch.setattr(client, "_extract_video_id", lambda _target: "vid1")
        monkeypatch.setattr(client, "_fetch_text", lambda _url: "<html></html>")
        monkeypatch.setattr(
            client,
            "_extract_ytcfg",
            lambda _html: {"INNERTUBE_CONTEXT": {"client": {}}},
        )
        monkeypatch.setattr(
            client, "_extract_innertube_api_key", lambda _html, _ytcfg: "k"
        )
        monkeypatch.setattr(client, "_extract_initial_data", lambda _html: None)
        monkeypatch.setattr(client, "_extract_player_response", lambda _html: player)
        monkeypatch.setattr(
            client,
            "_player_response_from_innertube",
            lambda *_args, **_kwargs: api_player,
        )

        result = client._extract_video("anything")

        assert result["id"] == "vid1"
        assert result["duration"] == 120
        assert result["channel_url"].endswith("chan1")
        assert result["availability"] == "public"
        assert result["subtitles"]["en"][0]["url"].endswith("fmt=json3")
        assert len(result["chapters"]) == 2

    def test_extract_playlist_full_flow_private_and_entries(self, monkeypatch):
        client = ExtractorClient()
        data = {
            "playlistMetadataRenderer": {
                "title": "My Private Playlist",
                "description": "desc",
            },
            "playlistSidebarPrimaryInfoRenderer": {
                "stats": [{"simpleText": "3 videos"}, {"simpleText": "1,234 views"}],
            },
            "playlistSidebarSecondaryInfoRenderer": {
                "videoOwner": {"videoOwnerRenderer": {"title": {"simpleText": "Owner"}}}
            },
        }

        monkeypatch.setattr(client, "_extract_playlist_id", lambda _target: "pl1")
        monkeypatch.setattr(client, "_fetch_text", lambda _url: "<html></html>")
        monkeypatch.setattr(client, "_extract_ytcfg", lambda _html: {})
        monkeypatch.setattr(
            client, "_extract_innertube_api_key", lambda _html, _ytcfg: None
        )
        monkeypatch.setattr(client, "_extract_initial_data", lambda _html: data)
        monkeypatch.setattr(
            client,
            "_extract_playlist_entries_paginated",
            lambda _data, api_key, ytcfg: (
                ytcfg,
                [{"id": "v1"}, {"id": "v2"}] if api_key is None else [],
            )[1],
        )

        result = client._extract_playlist("pl1", include_entries=True)

        assert result["id"] == "pl1"
        assert result["playlist_count"] == 3
        assert result["view_count"] == 1234
        assert result["availability"] == "private"
        assert result["entries"][0]["id"] == "v1"

    def test_extract_playlist_count_falls_back_to_entry_count(self, monkeypatch):
        client = ExtractorClient()
        data = {
            "playlistMetadataRenderer": {"title": "Playlist"},
            "playlistSidebarPrimaryInfoRenderer": {"stats": []},
            "playlistSidebarSecondaryInfoRenderer": {},
        }

        monkeypatch.setattr(client, "_extract_playlist_id", lambda _target: "pl1")
        monkeypatch.setattr(client, "_fetch_text", lambda _url: "<html></html>")
        monkeypatch.setattr(client, "_extract_ytcfg", lambda _html: {})
        monkeypatch.setattr(
            client, "_extract_innertube_api_key", lambda _html, _ytcfg: None
        )
        monkeypatch.setattr(client, "_extract_initial_data", lambda _html: data)
        monkeypatch.setattr(
            client,
            "_extract_playlist_entries_paginated",
            lambda *_args, **_kwargs: [{"id": "a"}],
        )

        result = client._extract_playlist("pl1", include_entries=True)

        assert result["playlist_count"] == 1

    def test_extract_playlist_entries_paginated_breaks_on_call_error(self, monkeypatch):
        client = ExtractorClient()
        data = {
            "continuationCommand": {"token": "tok1"},
            "playlistVideoRenderer": {"videoId": "id1", "title": {"simpleText": "One"}},
        }
        monkeypatch.setattr(
            client,
            "_call_innertube",
            lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("stop")),
        )

        entries = client._extract_playlist_entries_paginated(
            data, api_key="k", ytcfg={}
        )

        assert [e["id"] for e in entries] == ["id1"]

    def test_fetch_text_success_and_error(self, monkeypatch):
        client = ExtractorClient()

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b"hello"

        class _GoodOpener:
            def open(self, req, timeout=30):
                _ = (req, timeout)
                return _Resp()

        class _BadOpener:
            def open(self, req, timeout=30):
                _ = (req, timeout)
                raise RuntimeError("boom")

        monkeypatch.setattr(client, "_opener", _GoodOpener())
        assert client._fetch_text("https://x") == "hello"

        monkeypatch.setattr(client, "_opener", _BadOpener())
        with pytest.raises(ExtractorError, match="Request failed"):
            client._fetch_text("https://x")

    def test_fetch_json_wraps_generic_exceptions(self, monkeypatch):
        client = ExtractorClient()

        class _BadOpener:
            def open(self, req, timeout=30):
                _ = (req, timeout)
                raise RuntimeError("boom")

        monkeypatch.setattr(client, "_opener", _BadOpener())
        with pytest.raises(ExtractorError, match="Request failed"):
            client._fetch_json("https://x", {"a": 1}, {"h": "v"})

    def test_transcript_via_innertube_player_no_api_key(self):
        client = ExtractorClient()
        assert (
            client._transcript_via_innertube_player(
                video_id="v",
                api_key=None,
                ytcfg={},
                languages=["en"],
                include_automatic=True,
            )
            is None
        )
