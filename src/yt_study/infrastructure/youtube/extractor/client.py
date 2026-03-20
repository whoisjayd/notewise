from __future__ import annotations

import http.cookiejar
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from urllib.request import HTTPCookieProcessor, build_opener

from yt_study._constants import DEFAULT_LANGUAGES
from yt_study.errors import ExtractionError
from yt_study.infrastructure.youtube.extractor import _auth as _auth_ops
from yt_study.infrastructure.youtube.extractor import _helpers as _helper_ops
from yt_study.infrastructure.youtube.extractor import _playlist as _playlist_ops
from yt_study.infrastructure.youtube.extractor import _transport as _transport_ops
from yt_study.infrastructure.youtube.extractor import _video as _video_ops
from yt_study.infrastructure.youtube.extractor.parsers import (
    parse_transcript_payload,
    select_track,
)


@dataclass(frozen=True)
class YouTubeExtractorConfig:
    cookie_file: str | None = None
    verbose: int = 0


class YouTubeExtractorClient:
    def __init__(self, config: YouTubeExtractorConfig | None = None) -> None:
        self.config = config or YouTubeExtractorConfig()
        self._cookie_jar = self._load_cookie_jar(self.config.cookie_file)
        self._opener = build_opener(HTTPCookieProcessor(self._cookie_jar))

    def metadata(self, target: str) -> dict[str, Any]:
        if self._looks_like_playlist_url(target):
            pl = self._extract_playlist(target, include_entries=False)
            return {
                "command": "metadata",
                "target": target,
                "type": "playlist",
                "id": pl.get("id"),
                "title": pl.get("title"),
                "webpage_url": pl.get("webpage_url"),
                "extractor": "youtube:native:playlist",
                "chapters_count": 0,
                "subtitle_languages": [],
                "automatic_caption_languages": [],
                "data": {
                    "id": pl.get("id"),
                    "title": pl.get("title"),
                    "description": pl.get("description"),
                    "uploader": pl.get("uploader"),
                    "channel": pl.get("channel"),
                    "view_count": pl.get("view_count"),
                    "availability": pl.get("availability"),
                    "thumbnails": pl.get("thumbnails") or [],
                    "webpage_url": pl.get("webpage_url"),
                    "playlist_count": pl.get("playlist_count"),
                },
            }

        video = self._extract_video(target)
        return {
            "command": "metadata",
            "target": target,
            "type": "video",
            "id": video["id"],
            "title": video["title"],
            "webpage_url": video["webpage_url"],
            "extractor": "youtube:native:video",
            "chapters_count": len(video["chapters"]),
            "subtitle_languages": sorted(video["subtitles"].keys()),
            "automatic_caption_languages": sorted(video["automatic_captions"].keys()),
            "data": self._select_simple_video_fields(video),
        }

    def chapters(self, target: str) -> dict[str, Any]:
        video = self._extract_video(target)
        chapters = [
            {
                "index": i,
                "title": ch.get("title"),
                "start_time": ch.get("start_time"),
                "end_time": ch.get("end_time"),
            }
            for i, ch in enumerate(video["chapters"], start=1)
        ]
        return {
            "command": "chapters",
            "target": target,
            "video": {
                "id": video["id"],
                "title": video["title"],
                "webpage_url": video["webpage_url"],
            },
            "count": len(chapters),
            "chapters": chapters,
        }

    def playlist(self, target: str) -> dict[str, Any]:
        pl = self._extract_playlist(target, include_entries=True)
        return {
            "command": "playlist",
            "target": target,
            "type": "playlist",
            "playlist": {
                "id": pl.get("id"),
                "title": pl.get("title"),
                "description": pl.get("description"),
                "uploader": pl.get("uploader"),
                "channel": pl.get("channel"),
                "webpage_url": pl.get("webpage_url"),
                "playlist_count": pl.get("playlist_count"),
            },
            "entries": pl.get("entries") or [],
            "count": len(pl.get("entries") or []),
        }

    def transcript(
        self,
        target: str,
        languages: Iterable[str] | None = None,
        include_automatic: bool = True,
    ) -> dict[str, Any]:
        video = self._extract_video(target)
        language_list = [lang for lang in (languages or DEFAULT_LANGUAGES) if lang]
        selection = select_track(
            subtitles=video["subtitles"],
            automatic_captions=video["automatic_captions"],
            languages=language_list,
            include_automatic=include_automatic,
        )
        native_error: Exception | None = None
        segments: list[dict[str, Any]] = []
        source = None
        language_code = None
        is_generated = None
        track = None

        if selection is not None and selection.track.get("url"):
            try:
                payload = self._fetch_text(selection.track["url"])
                segments = [
                    s.to_dict()
                    for s in parse_transcript_payload(
                        payload, selection.track.get("ext")
                    )
                ]
                source = selection.source
                language_code = selection.language_code
                is_generated = selection.is_generated
                track = {
                    "ext": selection.track.get("ext"),
                    "name": selection.track.get("name"),
                    "url": selection.track.get("url"),
                }
            except Exception as exc:
                native_error = exc

        if not segments:
            fallback = self._transcript_via_innertube_player(
                video_id=video["id"],
                api_key=video.get("_innertube_api_key"),
                ytcfg=video.get("_ytcfg"),
                languages=language_list,
                include_automatic=include_automatic,
            )
            if fallback:
                segments = fallback["segments"]
                source = fallback["source"]
                language_code = fallback["language_code"]
                is_generated = fallback["is_generated"]
                track = fallback["track"]

        if not segments:
            if native_error is not None:
                raise ExtractionError(f"Transcript extraction failed: {native_error}")
            raise ExtractionError("No transcript/subtitle track found.")

        return {
            "command": "transcript",
            "target": target,
            "video": {
                "id": video["id"],
                "title": video["title"],
                "webpage_url": video["webpage_url"],
            },
            "requested_languages": language_list,
            "source": source,
            "language_code": language_code,
            "is_generated": is_generated,
            "track": track,
            "segment_count": len(segments),
            "segments": segments,
        }

    def _extract_video(self, target: str) -> dict[str, Any]:
        return _video_ops._extract_video(self, target)

    def _extract_playlist(self, target: str, include_entries: bool) -> dict[str, Any]:
        return _playlist_ops._extract_playlist(self, target, include_entries)

    def _extract_playlist_entries_paginated(
        self,
        data: dict[str, Any],
        api_key: str | None,
        ytcfg: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        return _playlist_ops._extract_playlist_entries_paginated(
            self, data, api_key, ytcfg
        )

    def _extract_playlist_entries(
        self, data: dict[str, Any], seen: set[str]
    ) -> list[dict[str, Any]]:
        return _playlist_ops._extract_playlist_entries(self, data, seen)

    def _extract_continuation_token(self, node: Any) -> str | None:
        return _playlist_ops._extract_continuation_token(self, node)

    def _build_subtitles(
        self, captions: dict[str, Any]
    ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
        return _video_ops._build_subtitles(self, captions)

    def _extract_chapters(
        self, data: dict[str, Any] | None, duration: int | None
    ) -> list[dict[str, Any]]:
        return _video_ops._extract_chapters(self, data, duration)

    def _extract_description_chapters(
        self, description: str, duration: int | None
    ) -> list[dict[str, Any]]:
        return _video_ops._extract_description_chapters(self, description, duration)

    def _extract_initial_data(self, html: str) -> dict[str, Any] | None:
        return _video_ops._extract_initial_data(self, html)

    def _extract_player_response(self, html: str) -> dict[str, Any]:
        return _video_ops._extract_player_response(self, html)

    def _extract_ytcfg(self, html: str) -> dict[str, Any] | None:
        return _video_ops._extract_ytcfg(self, html)

    def _extract_innertube_api_key(
        self, html: str, ytcfg: dict[str, Any] | None
    ) -> str | None:
        return _video_ops._extract_innertube_api_key(self, html, ytcfg)

    def _extract_json_by_markers(
        self, text: str, markers: tuple[str, ...]
    ) -> dict[str, Any] | None:
        return _video_ops._extract_json_by_markers(text, markers)

    @staticmethod
    def _extract_balanced_json(text: str, start: int) -> str | None:
        return _video_ops._extract_balanced_json(text, start)

    def _fetch_text(self, url: str) -> str:
        return _transport_ops._fetch_text(self, url)

    def _fetch_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        return _transport_ops._fetch_json(self, url, payload, headers)

    def _load_cookie_jar(self, cookie_file: str | None) -> http.cookiejar.CookieJar:
        return _auth_ops._load_cookie_jar(cookie_file)

    def _transcript_via_innertube_player(
        self,
        video_id: str,
        api_key: str | None,
        ytcfg: dict[str, Any] | None,
        languages: list[str],
        include_automatic: bool,
    ) -> dict[str, Any] | None:
        return _transport_ops._transcript_via_innertube_player(
            self,
            video_id,
            api_key,
            ytcfg,
            languages,
            include_automatic,
        )

    def _player_response_from_innertube(
        self,
        video_id: str,
        api_key: str,
        ytcfg: dict[str, Any],
    ) -> dict[str, Any] | None:
        return _transport_ops._player_response_from_innertube(
            self, video_id, api_key, ytcfg
        )

    def _call_innertube(
        self,
        endpoint: str,
        api_key: str,
        ytcfg: dict[str, Any],
        body: dict[str, Any],
        client_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _transport_ops._call_innertube(
            self,
            endpoint,
            api_key,
            ytcfg,
            body,
            client_override=client_override,
        )

    def _extract_context(
        self,
        ytcfg: dict[str, Any],
        client_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _transport_ops._extract_context(self, ytcfg, client_override)

    def _generate_api_headers(
        self,
        ytcfg: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, str]:
        return _transport_ops._generate_api_headers(self, ytcfg, context)

    def _generate_cookie_auth_headers(
        self,
        ytcfg: dict[str, Any],
        origin: str,
    ) -> dict[str, str]:
        return _auth_ops._generate_cookie_auth_headers(
            self,
            ytcfg,
            origin,
            now=time.time,
        )

    def _extract_session_index(self, ytcfg: dict[str, Any]) -> int | None:
        return _auth_ops._extract_session_index(ytcfg)

    def _extract_data_sync_id(self, ytcfg: dict[str, Any]) -> str | None:
        return _auth_ops._extract_data_sync_id(ytcfg)

    def _parse_data_sync_id(self, value: str | None) -> tuple[str | None, str | None]:
        return _auth_ops._parse_data_sync_id(value)

    def _extract_user_session_id(self, ytcfg: dict[str, Any]) -> str | None:
        return _auth_ops._extract_user_session_id(ytcfg)

    def _extract_delegated_session_id(self, ytcfg: dict[str, Any]) -> str | None:
        return _auth_ops._extract_delegated_session_id(ytcfg)

    @staticmethod
    def _make_sid_authorization(
        scheme: str,
        sid: str,
        origin: str,
        additional_parts: dict[str, str] | None,
    ) -> str:
        return _auth_ops._make_sid_authorization(
            scheme,
            sid,
            origin,
            additional_parts,
            now=time.time,
        )

    def _get_sid_authorization_header(
        self,
        origin: str,
        user_session_id: str | None,
    ) -> str | None:
        return _auth_ops._get_sid_authorization_header(
            self,
            origin=origin,
            user_session_id=user_session_id,
            now=time.time,
        )

    def _get_sid_cookies(self) -> tuple[str | None, str | None, str | None]:
        return _auth_ops._get_sid_cookies(self)

    def _youtube_cookies(self) -> dict[str, str]:
        return _auth_ops._youtube_cookies(self)

    @staticmethod
    def _default_headers() -> dict[str, str]:
        return _auth_ops._default_headers()

    @staticmethod
    def _select_simple_video_fields(video: dict[str, Any]) -> dict[str, Any]:
        return _helper_ops._select_simple_video_fields(video)

    @staticmethod
    def _extract_video_id(target: str) -> str:
        return _helper_ops._extract_video_id(target)

    @staticmethod
    def _looks_like_playlist_url(target: str) -> bool:
        return _helper_ops._looks_like_playlist_url(target)

    @staticmethod
    def _extract_playlist_id(target: str) -> str:
        return _helper_ops._extract_playlist_id(target)

    @staticmethod
    def _with_fmt_json3(url: str) -> str:
        return _helper_ops._with_fmt_json3(url)

    @staticmethod
    def _to_int(v: Any) -> int | None:
        return _helper_ops._to_int(v)

    @staticmethod
    def _parse_duration(text: str | None) -> int | None:
        return _helper_ops._parse_duration(text)

    @staticmethod
    def _best_thumbnail(items: list[dict[str, Any]] | None) -> str | None:
        return _helper_ops._best_thumbnail(items)

    @staticmethod
    def _get_text(v: Any) -> str | None:
        return _helper_ops._get_text(v)

    @staticmethod
    def _date_to_yyyymmdd(value: str | None) -> str | None:
        return _helper_ops._date_to_yyyymmdd(value)

    @staticmethod
    def _iso_to_unix(value: str | None) -> int | None:
        return _helper_ops._iso_to_unix(value)

    @staticmethod
    def _availability(playability: dict[str, Any]) -> str:
        return _helper_ops._availability(playability)

    @staticmethod
    def _parse_count(text: str | None) -> int | None:
        return _helper_ops._parse_count(text)

    @staticmethod
    def _find_key(node: Any, key: str) -> list[dict[str, Any]]:
        return _helper_ops._find_key(node, key)

    @staticmethod
    def _first_key(node: Any, key: str) -> dict[str, Any] | None:
        return _helper_ops._first_key(node, key)
