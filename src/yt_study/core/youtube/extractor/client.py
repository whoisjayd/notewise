from __future__ import annotations

import copy
import hashlib
import http.cookiejar
import json
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener

from .transcripts import parse_transcript_payload, select_track


WATCH_URL = "https://www.youtube.com/watch?v={video_id}"


class ExtractorError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExtractorConfig:
    cookie_file: str | None = None
    verbose: int = 0


class ExtractorClient:
    def __init__(self, config: ExtractorConfig | None = None) -> None:
        self.config = config or ExtractorConfig()
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
        language_list = [lang for lang in (languages or ["en"]) if lang]
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
                raise ExtractorError(f"Transcript extraction failed: {native_error}")
            raise ExtractorError("No transcript/subtitle track found.")

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
        video_id = self._extract_video_id(target)
        webpage_url = WATCH_URL.format(video_id=video_id)
        html = self._fetch_text(webpage_url)
        ytcfg = self._extract_ytcfg(html) or {}
        api_key = self._extract_innertube_api_key(html, ytcfg)
        initial_data = self._extract_initial_data(html)
        player = self._extract_player_response(html)

        details = player.get("videoDetails") or {}
        micro = (player.get("microformat") or {}).get("playerMicroformatRenderer") or {}
        captions = (player.get("captions") or {}).get(
            "playerCaptionsTracklistRenderer"
        ) or {}
        subtitles, automatic = self._build_subtitles(captions)
        if not subtitles and not automatic and api_key:
            api_player = self._player_response_from_innertube(video_id, api_key, ytcfg)
            if api_player:
                api_captions = (api_player.get("captions") or {}).get(
                    "playerCaptionsTracklistRenderer"
                ) or {}
                subtitles, automatic = self._build_subtitles(api_captions)
        duration = self._to_int(details.get("lengthSeconds"))
        description = (
            details.get("shortDescription")
            or self._get_text(micro.get("description"))
            or ""
        )

        chapters = self._extract_chapters(
            initial_data, duration
        ) or self._extract_description_chapters(description, duration)

        return {
            "id": video_id,
            "title": details.get("title") or "",
            "description": description,
            "duration": duration,
            "upload_date": self._date_to_yyyymmdd(micro.get("uploadDate")),
            "timestamp": self._iso_to_unix(micro.get("uploadDate")),
            "release_date": self._date_to_yyyymmdd(micro.get("publishDate")),
            "view_count": self._to_int(details.get("viewCount")),
            "like_count": None,
            "comment_count": None,
            "uploader": details.get("author"),
            "uploader_id": None,
            "uploader_url": None,
            "channel": details.get("author"),
            "channel_id": details.get("channelId"),
            "channel_url": f"https://www.youtube.com/channel/{details.get('channelId')}"
            if details.get("channelId")
            else None,
            "availability": self._availability(player.get("playabilityStatus") or {}),
            "age_limit": 0,
            "is_live": bool(details.get("isLive")),
            "live_status": "is_live" if details.get("isLive") else "not_live",
            "language": "en",
            "tags": details.get("keywords") or [],
            "categories": [micro.get("category")] if micro.get("category") else [],
            "thumbnail": self._best_thumbnail(
                details.get("thumbnail", {}).get("thumbnails")
            ),
            "thumbnails": details.get("thumbnail", {}).get("thumbnails") or [],
            "webpage_url": webpage_url,
            "chapters": chapters,
            "subtitles": subtitles,
            "automatic_captions": automatic,
            "_innertube_api_key": api_key,
            "_ytcfg": ytcfg,
        }

    def _extract_playlist(self, target: str, include_entries: bool) -> dict[str, Any]:
        playlist_id = self._extract_playlist_id(target)
        webpage_url = f"https://www.youtube.com/playlist?list={playlist_id}"
        html = self._fetch_text(webpage_url)
        ytcfg = self._extract_ytcfg(html) or {}
        api_key = self._extract_innertube_api_key(html, ytcfg)
        data = self._extract_initial_data(html) or {}

        meta_renderer = self._first_key(data, "playlistMetadataRenderer") or {}
        primary = self._first_key(data, "playlistSidebarPrimaryInfoRenderer") or {}
        secondary = self._first_key(data, "playlistSidebarSecondaryInfoRenderer") or {}

        title = meta_renderer.get("title") or self._get_text(primary.get("title")) or ""
        description = meta_renderer.get("description") or ""
        owner = self._get_text(
            ((secondary.get("videoOwner") or {}).get("videoOwnerRenderer") or {}).get(
                "title"
            )
        )

        stats = primary.get("stats") or []
        playlist_count = (
            self._parse_count(self._get_text(stats[0])) if len(stats) > 0 else None
        )
        view_count = (
            self._parse_count(self._get_text(stats[1])) if len(stats) > 1 else None
        )

        entries = []
        if include_entries:
            entries = self._extract_playlist_entries_paginated(
                data, api_key=api_key, ytcfg=ytcfg
            )
        if playlist_count is None:
            playlist_count = len(entries)

        availability = "private" if "private" in title.lower() else "public"

        return {
            "id": playlist_id,
            "title": title,
            "description": description,
            "uploader": owner,
            "channel": owner,
            "view_count": view_count,
            "availability": availability,
            "thumbnails": [],
            "webpage_url": webpage_url,
            "playlist_count": playlist_count,
            "entries": entries,
        }

    def _extract_playlist_entries_paginated(
        self,
        data: dict[str, Any],
        api_key: str | None,
        ytcfg: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        out.extend(self._extract_playlist_entries(data, seen))

        if not api_key:
            return out

        token = self._extract_continuation_token(data)
        seen_tokens: set[str] = set()
        for _ in range(250):
            if not token or token in seen_tokens:
                break
            seen_tokens.add(token)
            try:
                page = self._call_innertube(
                    endpoint="browse",
                    api_key=api_key,
                    ytcfg=ytcfg or {},
                    body={"continuation": token},
                )
            except Exception:
                break
            out.extend(self._extract_playlist_entries(page, seen))
            token = self._extract_continuation_token(page)
        return out

    def _extract_playlist_entries(
        self, data: dict[str, Any], seen: set[str]
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for obj in self._find_key(data, "playlistVideoRenderer"):
            r = obj["playlistVideoRenderer"]
            vid = r.get("videoId")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            out.append(
                {
                    "id": vid,
                    "title": self._get_text(r.get("title")) or "",
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "duration": self._parse_duration(
                        self._get_text(r.get("lengthText"))
                    ),
                    "channel": self._get_text(r.get("shortBylineText")),
                    "uploader": self._get_text(r.get("shortBylineText")),
                    "ie_key": "Youtube",
                }
            )
        return out

    def _extract_continuation_token(self, node: Any) -> str | None:
        for obj in self._find_key(node, "continuationCommand"):
            token = (obj.get("continuationCommand") or {}).get("token")
            if isinstance(token, str) and token:
                return token
        for obj in self._find_key(node, "nextContinuationData"):
            token = (obj.get("nextContinuationData") or {}).get("continuation")
            if isinstance(token, str) and token:
                return token
        for obj in self._find_key(node, "reloadContinuationData"):
            token = (obj.get("reloadContinuationData") or {}).get("continuation")
            if isinstance(token, str) and token:
                return token
        return None

    def _build_subtitles(
        self, captions: dict[str, Any]
    ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
        subs: dict[str, list[dict[str, Any]]] = {}
        autos: dict[str, list[dict[str, Any]]] = {}
        for track in captions.get("captionTracks", []):
            if not isinstance(track, dict):
                continue
            lang = track.get("languageCode")
            base = track.get("baseUrl")
            if not lang or not base:
                continue
            url = self._with_fmt_json3(base)
            item = {
                "ext": "json3",
                "url": url,
                "name": self._get_text(track.get("name")) or lang,
            }
            if track.get("kind") == "asr":
                autos.setdefault(lang, []).append(item)
            else:
                subs.setdefault(lang, []).append(item)
        return subs, autos

    def _extract_chapters(
        self, data: dict[str, Any] | None, duration: int | None
    ) -> list[dict[str, Any]]:
        if not data:
            return []
        chapters: list[tuple[float, str]] = []
        for obj in self._find_key(data, "chapterRenderer"):
            ch = obj["chapterRenderer"]
            start_ms = ch.get("timeRangeStartMillis")
            if start_ms is None:
                continue
            chapters.append(
                (float(start_ms) / 1000.0, self._get_text(ch.get("title")) or "Chapter")
            )
        for obj in self._find_key(data, "macroMarkersListItemRenderer"):
            ch = obj["macroMarkersListItemRenderer"]
            parsed_start = self._parse_duration(
                self._get_text(ch.get("timeDescription"))
            )
            if parsed_start is None:
                continue
            chapters.append(
                (float(parsed_start), self._get_text(ch.get("title")) or "Chapter")
            )
        unique = sorted({s: t for s, t in chapters}.items(), key=lambda x: x[0])
        if len(unique) < 2:
            return []
        total = float(duration or int(unique[-1][0]))
        out: list[dict[str, Any]] = []
        for i, (start, title) in enumerate(unique):
            end = total if i + 1 >= len(unique) else float(unique[i + 1][0])
            out.append({"start_time": start, "end_time": end, "title": title})
        return out

    def _extract_description_chapters(
        self, description: str, duration: int | None
    ) -> list[dict[str, Any]]:
        found: list[tuple[float, str]] = []
        for line in description.splitlines():
            m = re.search(r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})", line)
            if not m:
                continue
            ts = m.group(0)
            sec = self._parse_duration(ts)
            if sec is None:
                continue
            title = line.replace(ts, "", 1).strip(" -\t")
            found.append((float(sec), title or "Chapter"))
        found = sorted({s: t for s, t in found}.items(), key=lambda x: x[0])
        if len(found) < 2:
            return []
        total = float(duration or int(found[-1][0]))
        out = []
        for i, (start, title) in enumerate(found):
            end = total if i + 1 >= len(found) else float(found[i + 1][0])
            out.append({"start_time": start, "end_time": end, "title": title})
        return out

    def _extract_initial_data(self, html: str) -> dict[str, Any] | None:
        return self._extract_json_by_markers(
            html, ("var ytInitialData = ", "ytInitialData = ")
        )

    def _extract_player_response(self, html: str) -> dict[str, Any]:
        data = self._extract_json_by_markers(
            html, ("var ytInitialPlayerResponse = ", "ytInitialPlayerResponse = ")
        )
        if not isinstance(data, dict):
            raise ExtractorError("Unable to parse ytInitialPlayerResponse")
        return data

    def _extract_ytcfg(self, html: str) -> dict[str, Any] | None:
        return self._extract_json_by_markers(html, ("ytcfg.set(",))

    def _extract_innertube_api_key(
        self, html: str, ytcfg: dict[str, Any] | None
    ) -> str | None:
        if ytcfg:
            api_key_value = ytcfg.get("INNERTUBE_API_KEY")
            if isinstance(api_key_value, str):
                return api_key_value
        m = re.search(r'"INNERTUBE_API_KEY"\s*:\s*"([a-zA-Z0-9_-]+)"', html)
        if m:
            return m.group(1)
        return None

    def _extract_json_by_markers(
        self, text: str, markers: tuple[str, ...]
    ) -> dict[str, Any] | None:
        for marker in markers:
            idx = text.find(marker)
            if idx < 0:
                continue
            start = text.find("{", idx + len(marker))
            if start < 0:
                continue
            raw = self._extract_balanced_json(text, start)
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            if isinstance(obj, dict):
                return obj
        return None

    @staticmethod
    def _extract_balanced_json(text: str, start: int) -> str | None:
        depth = 0
        in_string = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        return None

    def _fetch_text(self, url: str) -> str:
        req = Request(url=url, headers=self._default_headers(), method="GET")
        try:
            with self._opener.open(req, timeout=30) as resp:
                body = resp.read()
                if isinstance(body, bytes):
                    return body.decode("utf-8", errors="replace")
                return str(body)
        except Exception as exc:
            raise ExtractorError(f"Request failed for {url}: {exc}") from exc

    def _fetch_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        req = Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with self._opener.open(req, timeout=30) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ExtractorError(f"Unexpected JSON response type for {url}")
            return data
        except ExtractorError:
            raise
        except Exception as exc:
            raise ExtractorError(f"Request failed for {url}: {exc}") from exc

    def _load_cookie_jar(self, cookie_file: str | None) -> http.cookiejar.CookieJar:
        jar = http.cookiejar.MozillaCookieJar()
        if cookie_file:
            path = Path(cookie_file)
            if not path.exists():
                raise ExtractorError(f"Cookie file not found: {cookie_file}")
            try:
                jar.load(str(path), ignore_discard=True, ignore_expires=True)
                for cookie in jar:
                    if cookie.expires == 0:
                        cookie.expires = None
                        cookie.discard = True
            except Exception as exc:
                raise ExtractorError(
                    f"Failed to load cookie file: {cookie_file}"
                ) from exc
        return jar

    def _transcript_via_innertube_player(
        self,
        video_id: str,
        api_key: str | None,
        ytcfg: dict[str, Any] | None,
        languages: list[str],
        include_automatic: bool,
    ) -> dict[str, Any] | None:
        if not api_key:
            return None
        contexts = [
            None,
            {
                "clientName": "ANDROID",
                "clientVersion": "20.10.38",
                "userAgent": (
                    "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/65.0.3325.181 "
                    "Mobile Safari/537.36"
                ),
            },
        ]
        for override in contexts:
            try:
                player = self._call_innertube(
                    endpoint="player",
                    api_key=api_key,
                    ytcfg=ytcfg or {},
                    body={"videoId": video_id},
                    client_override=override,
                )
            except Exception:
                continue
            captions = (player.get("captions") or {}).get(
                "playerCaptionsTracklistRenderer"
            ) or {}
            subtitles, automatic = self._build_subtitles(captions)
            selection = select_track(
                subtitles=subtitles,
                automatic_captions=automatic,
                languages=languages,
                include_automatic=include_automatic,
            )
            if not selection or not selection.track.get("url"):
                continue
            try:
                payload = self._fetch_text(selection.track["url"])
                segments = [
                    s.to_dict()
                    for s in parse_transcript_payload(
                        payload, selection.track.get("ext")
                    )
                ]
                if not segments:
                    continue
                return {
                    "source": "innertube:player",
                    "segments": segments,
                    "language_code": selection.language_code,
                    "is_generated": selection.is_generated,
                    "track": {
                        "ext": selection.track.get("ext"),
                        "name": selection.track.get("name"),
                        "url": selection.track.get("url"),
                    },
                }
            except Exception:
                continue
        return None

    def _player_response_from_innertube(
        self,
        video_id: str,
        api_key: str,
        ytcfg: dict[str, Any],
    ) -> dict[str, Any] | None:
        try:
            return self._call_innertube(
                endpoint="player",
                api_key=api_key,
                ytcfg=ytcfg,
                body={"videoId": video_id},
            )
        except Exception:
            return None

    def _call_innertube(
        self,
        endpoint: str,
        api_key: str,
        ytcfg: dict[str, Any],
        body: dict[str, Any],
        client_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = self._extract_context(ytcfg, client_override=client_override)
        payload = {"context": context}
        payload.update(body)
        headers = self._generate_api_headers(ytcfg, context)
        headers["Content-Type"] = "application/json"
        url = f"https://www.youtube.com/youtubei/v1/{endpoint}?key={api_key}&prettyPrint=false"
        return self._fetch_json(url, payload, headers)

    def _extract_context(
        self,
        ytcfg: dict[str, Any],
        client_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = copy.deepcopy(ytcfg.get("INNERTUBE_CONTEXT") or {})
        if not isinstance(context, dict):
            context = {}
        client = context.setdefault("client", {})
        if not isinstance(client, dict):
            client = {}
            context["client"] = client

        if client_override:
            for key in ("clientName", "clientVersion", "userAgent"):
                if client_override.get(key):
                    client[key] = client_override[key]
        if not client.get("clientName"):
            client["clientName"] = "WEB"
        if not client.get("clientVersion"):
            client["clientVersion"] = "2.20250626.01.00"
        client["hl"] = "en"
        client["timeZone"] = "UTC"
        client["utcOffsetMinutes"] = 0
        return context

    def _generate_api_headers(
        self,
        ytcfg: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, str]:
        client = (context.get("client") or {}) if isinstance(context, dict) else {}
        origin = "https://www.youtube.com"
        headers: dict[str, str] = {
            "Origin": origin,
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": client.get("userAgent")
            or self._default_headers()["User-Agent"],
            "X-YouTube-Client-Name": str(
                ytcfg.get("INNERTUBE_CONTEXT_CLIENT_NAME")
                or ytcfg.get("INNERTUBE_CLIENT_NAME")
                or 1
            ),
            "X-YouTube-Client-Version": str(
                client.get("clientVersion")
                or ytcfg.get("INNERTUBE_CONTEXT_CLIENT_VERSION")
                or "2.20250626.01.00"
            ),
        }
        visitor_data = ytcfg.get("VISITOR_DATA") or (
            (ytcfg.get("INNERTUBE_CONTEXT") or {}).get("client") or {}
        ).get("visitorData")
        if visitor_data:
            headers["X-Goog-Visitor-Id"] = str(visitor_data)
        headers.update(self._generate_cookie_auth_headers(ytcfg, origin))
        return headers

    def _generate_cookie_auth_headers(
        self,
        ytcfg: dict[str, Any],
        origin: str,
    ) -> dict[str, str]:
        headers: dict[str, str] = {}
        delegated_session_id = self._extract_delegated_session_id(ytcfg)
        session_index = self._extract_session_index(ytcfg)
        if delegated_session_id:
            headers["X-Goog-PageId"] = delegated_session_id
        if delegated_session_id or session_index is not None:
            headers["X-Goog-AuthUser"] = str(
                session_index if session_index is not None else 0
            )

        auth = self._get_sid_authorization_header(
            origin=origin,
            user_session_id=self._extract_user_session_id(ytcfg),
        )
        if auth:
            headers["Authorization"] = auth
            headers["X-Origin"] = origin
        if ytcfg.get("LOGGED_IN"):
            headers["X-Youtube-Bootstrap-Logged-In"] = "true"
        return headers

    def _extract_session_index(self, ytcfg: dict[str, Any]) -> int | None:
        try:
            value = ytcfg.get("SESSION_INDEX")
            if value is None:
                return None
            return int(str(value))
        except Exception:
            return None

    def _extract_data_sync_id(self, ytcfg: dict[str, Any]) -> str | None:
        value = ytcfg.get("DATASYNC_ID")
        return str(value) if value else None

    def _parse_data_sync_id(self, value: str | None) -> tuple[str | None, str | None]:
        if not value:
            return None, None
        first, _, second = value.partition("||")
        if second:
            return first, second
        return None, first

    def _extract_user_session_id(self, ytcfg: dict[str, Any]) -> str | None:
        if ytcfg.get("USER_SESSION_ID"):
            return str(ytcfg["USER_SESSION_ID"])
        return self._parse_data_sync_id(self._extract_data_sync_id(ytcfg))[1]

    def _extract_delegated_session_id(self, ytcfg: dict[str, Any]) -> str | None:
        if ytcfg.get("DELEGATED_SESSION_ID"):
            return str(ytcfg["DELEGATED_SESSION_ID"])
        return self._parse_data_sync_id(self._extract_data_sync_id(ytcfg))[0]

    @staticmethod
    def _make_sid_authorization(
        scheme: str,
        sid: str,
        origin: str,
        additional_parts: dict[str, str] | None,
    ) -> str:
        timestamp = str(round(time.time()))
        hash_parts: list[str] = []
        if additional_parts:
            hash_parts.append(":".join(additional_parts.values()))
        hash_parts.extend([timestamp, sid, origin])
        sidhash = hashlib.sha1(
            " ".join(hash_parts).encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()
        parts = [timestamp, sidhash]
        if additional_parts:
            parts.append("".join(additional_parts.keys()))
        return f"{scheme} {'_'.join(parts)}"

    def _get_sid_authorization_header(
        self,
        origin: str,
        user_session_id: str | None,
    ) -> str | None:
        sapisid, one_p, three_p = self._get_sid_cookies()
        additional = {"u": user_session_id} if user_session_id else None
        out = []
        for scheme, sid in (
            ("SAPISIDHASH", sapisid),
            ("SAPISID1PHASH", one_p),
            ("SAPISID3PHASH", three_p),
        ):
            if sid:
                out.append(
                    self._make_sid_authorization(scheme, sid, origin, additional)
                )
        return " ".join(out) if out else None

    def _get_sid_cookies(self) -> tuple[str | None, str | None, str | None]:
        cookies = self._youtube_cookies()
        sapisid = cookies.get("SAPISID")
        one_p = cookies.get("__Secure-1PAPISID")
        three_p = cookies.get("__Secure-3PAPISID")
        return sapisid or three_p, one_p, three_p

    def _youtube_cookies(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for cookie in self._cookie_jar:
            domain = (cookie.domain or "").lstrip(".").lower()
            if "youtube.com" not in domain:
                continue
            if cookie.value is None:
                continue
            out[cookie.name] = cookie.value
        return out

    @staticmethod
    def _default_headers() -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }

    @staticmethod
    def _select_simple_video_fields(video: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "id",
            "title",
            "description",
            "duration",
            "upload_date",
            "timestamp",
            "release_date",
            "view_count",
            "like_count",
            "comment_count",
            "uploader",
            "uploader_id",
            "uploader_url",
            "channel",
            "channel_id",
            "channel_url",
            "availability",
            "age_limit",
            "is_live",
            "live_status",
            "language",
            "tags",
            "categories",
            "thumbnail",
            "thumbnails",
            "webpage_url",
        )
        return {k: video.get(k) for k in keys}

    @staticmethod
    def _extract_video_id(target: str) -> str:
        if "://" not in target:
            return target
        p = urlparse(target)
        if p.netloc.endswith("youtu.be"):
            return p.path.strip("/")
        qs = parse_qs(p.query)
        if qs.get("v"):
            return qs["v"][0]
        parts = [x for x in p.path.split("/") if x]
        if len(parts) >= 2 and parts[0] in {"shorts", "embed", "live"}:
            return parts[1]
        raise ExtractorError(f"Unable to determine video id from {target}")

    @staticmethod
    def _looks_like_playlist_url(target: str) -> bool:
        if "://" not in target:
            return False
        p = urlparse(target)
        qs = parse_qs(p.query)
        return bool(qs.get("list")) and ("/playlist" in p.path or not qs.get("v"))

    @staticmethod
    def _extract_playlist_id(target: str) -> str:
        p = urlparse(target)
        pid = parse_qs(p.query).get("list", [None])[0]
        if not pid:
            raise ExtractorError(f"Unable to determine playlist id from {target}")
        return pid

    @staticmethod
    def _with_fmt_json3(url: str) -> str:
        p = urlparse(url)
        qs = parse_qs(p.query)
        qs["fmt"] = ["json3"]
        p = p._replace(query=urlencode(qs, doseq=True))
        return p.geturl()

    @staticmethod
    def _to_int(v: Any) -> int | None:
        try:
            return int(str(v)) if v not in (None, "") else None
        except Exception:
            return None

    @staticmethod
    def _parse_duration(text: str | None) -> int | None:
        if not text:
            return None
        parts = text.strip().split(":")
        try:
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            if len(parts) == 1 and parts[0].isdigit():
                return int(parts[0])
        except Exception:
            return None
        return None

    @staticmethod
    def _best_thumbnail(items: list[dict[str, Any]] | None) -> str | None:
        if not items:
            return None
        best = max(
            items, key=lambda x: (int(x.get("width") or 0), int(x.get("height") or 0))
        )
        url = best.get("url")
        return url if isinstance(url, str) else None

    @staticmethod
    def _get_text(v: Any) -> str | None:
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            simple_text = v.get("simpleText")
            if isinstance(simple_text, str):
                return simple_text
            runs = v.get("runs")
            if isinstance(runs, list):
                out = "".join(
                    str(x.get("text", "")) for x in runs if isinstance(x, dict)
                )
                return out or None
            text_value = v.get("text")
            if isinstance(text_value, str):
                return text_value
        return None

    @staticmethod
    def _date_to_yyyymmdd(value: str | None) -> str | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime(
                "%Y%m%d"
            )
        except Exception:
            return (
                value.replace("-", "")
                if re.match(r"^\d{4}-\d{2}-\d{2}$", value)
                else None
            )

    @staticmethod
    def _iso_to_unix(value: str | None) -> int | None:
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except Exception:
            return None

    @staticmethod
    def _availability(playability: dict[str, Any]) -> str:
        status = str(playability.get("status") or "").upper()
        reason = str(playability.get("reason") or "").lower()
        if status == "OK":
            return "public"
        if status == "LOGIN_REQUIRED":
            return "private" if "private" in reason else "login_required"
        if "age" in reason:
            return "age_restricted"
        return "unavailable"

    @staticmethod
    def _parse_count(text: str | None) -> int | None:
        if not text:
            return None
        digits = re.sub(r"[^\d]", "", text)
        return int(digits) if digits else None

    @staticmethod
    def _find_key(node: Any, key: str) -> list[dict[str, Any]]:
        out = []
        stack = [node]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                if key in cur:
                    out.append(cur)
                stack.extend(cur.values())
            elif isinstance(cur, list):
                stack.extend(cur)
        return out

    @staticmethod
    def _first_key(node: Any, key: str) -> dict[str, Any] | None:
        found = ExtractorClient._find_key(node, key)
        return found[0][key] if found else None
