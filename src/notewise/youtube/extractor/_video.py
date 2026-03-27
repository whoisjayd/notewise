"""Private video extraction helpers for the native YouTube extractor."""

from __future__ import annotations

import json
import re
from typing import Any

from notewise.errors import ExtractionError
from notewise.youtube._constants import (
    YOUTUBE_CHANNEL_URL,
    YOUTUBE_WATCH_URL,
)


def _extract_video(client: Any, target: str) -> dict[str, Any]:
    video_id = client._extract_video_id(target)
    webpage_url = YOUTUBE_WATCH_URL.format(video_id=video_id)
    html = client._fetch_text(webpage_url)
    ytcfg = client._extract_ytcfg(html) or {}
    api_key = client._extract_innertube_api_key(html, ytcfg)
    initial_data = client._extract_initial_data(html)
    player = client._extract_player_response(html)

    details = player.get("videoDetails") or {}
    micro = (player.get("microformat") or {}).get("playerMicroformatRenderer") or {}
    captions = (player.get("captions") or {}).get(
        "playerCaptionsTracklistRenderer"
    ) or {}
    subtitles, automatic = client._build_subtitles(captions)
    if not subtitles and not automatic and api_key:
        api_player = client._player_response_from_innertube(video_id, api_key, ytcfg)
        if api_player:
            api_captions = (api_player.get("captions") or {}).get(
                "playerCaptionsTracklistRenderer"
            ) or {}
            subtitles, automatic = client._build_subtitles(api_captions)
    duration = client._to_int(details.get("lengthSeconds"))
    description = (
        details.get("shortDescription")
        or client._get_text(micro.get("description"))
        or ""
    )

    chapters = client._extract_chapters(
        initial_data, duration
    ) or client._extract_description_chapters(description, duration)

    return {
        "id": video_id,
        "title": details.get("title") or "",
        "description": description,
        "duration": duration,
        "upload_date": client._date_to_yyyymmdd(micro.get("uploadDate")),
        "timestamp": client._iso_to_unix(micro.get("uploadDate")),
        "release_date": client._date_to_yyyymmdd(micro.get("publishDate")),
        "view_count": client._to_int(details.get("viewCount")),
        "like_count": None,
        "comment_count": None,
        "uploader": details.get("author"),
        "uploader_id": None,
        "uploader_url": None,
        "channel": details.get("author"),
        "channel_id": details.get("channelId"),
        "channel_url": (
            YOUTUBE_CHANNEL_URL.format(channel_id=details.get("channelId"))
            if details.get("channelId")
            else None
        ),
        "availability": client._availability(player.get("playabilityStatus") or {}),
        "age_limit": 0,
        "is_live": bool(details.get("isLive")),
        "live_status": "is_live" if details.get("isLive") else "not_live",
        "language": "en",
        "tags": details.get("keywords") or [],
        "categories": [micro.get("category")] if micro.get("category") else [],
        "thumbnail": client._best_thumbnail(
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


def _build_subtitles(
    client: Any,
    captions: dict[str, Any],
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
        url = client._with_fmt_json3(base)
        item = {
            "ext": "json3",
            "url": url,
            "name": client._get_text(track.get("name")) or lang,
        }
        if track.get("kind") == "asr":
            autos.setdefault(lang, []).append(item)
        else:
            subs.setdefault(lang, []).append(item)
    return subs, autos


def _extract_chapters(
    client: Any,
    data: dict[str, Any] | None,
    duration: int | None,
) -> list[dict[str, Any]]:
    if not data:
        return []
    chapters: list[tuple[float, str]] = []
    for obj in client._find_key(data, "chapterRenderer"):
        ch = obj["chapterRenderer"]
        start_ms = ch.get("timeRangeStartMillis")
        if start_ms is None:
            continue
        chapters.append(
            (float(start_ms) / 1000.0, client._get_text(ch.get("title")) or "Chapter")
        )
    for obj in client._find_key(data, "macroMarkersListItemRenderer"):
        ch = obj["macroMarkersListItemRenderer"]
        parsed_start = client._parse_duration(
            client._get_text(ch.get("timeDescription"))
        )
        if parsed_start is None:
            continue
        chapters.append(
            (float(parsed_start), client._get_text(ch.get("title")) or "Chapter")
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
    client: Any,
    description: str,
    duration: int | None,
) -> list[dict[str, Any]]:
    found: list[tuple[float, str]] = []
    for line in description.splitlines():
        m = re.search(r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})", line)
        if not m:
            continue
        ts = m.group(0)
        sec = client._parse_duration(ts)
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


def _extract_initial_data(_client: Any, html: str) -> dict[str, Any] | None:
    return _extract_json_by_markers(
        html,
        ("var ytInitialData = ", "ytInitialData = "),
    )


def _extract_player_response(_client: Any, html: str) -> dict[str, Any]:
    data = _extract_json_by_markers(
        html,
        ("var ytInitialPlayerResponse = ", "ytInitialPlayerResponse = "),
    )
    if not isinstance(data, dict):
        raise ExtractionError("Unable to parse ytInitialPlayerResponse")
    return data


def _extract_ytcfg(_client: Any, html: str) -> dict[str, Any] | None:
    return _extract_json_by_markers(html, ("ytcfg.set(",))


def _extract_innertube_api_key(
    _client: Any,
    html: str,
    ytcfg: dict[str, Any] | None,
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
    text: str,
    markers: tuple[str, ...],
) -> dict[str, Any] | None:
    for marker in markers:
        idx = text.find(marker)
        if idx < 0:
            continue
        start = text.find("{", idx + len(marker))
        if start < 0:
            continue
        raw = _extract_balanced_json(text, start)
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        if isinstance(obj, dict):
            return obj
    return None


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


class _VideoMixin:
    def _extract_video(self, target: str) -> dict[str, Any]:
        return _extract_video(self, target)

    def _build_subtitles(
        self,
        captions: dict[str, Any],
    ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
        return _build_subtitles(self, captions)

    def _extract_chapters(
        self,
        data: dict[str, Any] | None,
        duration: int | None,
    ) -> list[dict[str, Any]]:
        return _extract_chapters(self, data, duration)

    def _extract_description_chapters(
        self,
        description: str,
        duration: int | None,
    ) -> list[dict[str, Any]]:
        return _extract_description_chapters(self, description, duration)

    def _extract_initial_data(self, html: str) -> dict[str, Any] | None:
        return _extract_initial_data(self, html)

    def _extract_player_response(self, html: str) -> dict[str, Any]:
        return _extract_player_response(self, html)

    def _extract_ytcfg(self, html: str) -> dict[str, Any] | None:
        return _extract_ytcfg(self, html)

    def _extract_innertube_api_key(
        self,
        html: str,
        ytcfg: dict[str, Any] | None,
    ) -> str | None:
        return _extract_innertube_api_key(self, html, ytcfg)

    def _extract_json_by_markers(
        self,
        text: str,
        markers: tuple[str, ...],
    ) -> dict[str, Any] | None:
        return _extract_json_by_markers(text, markers)

    @staticmethod
    def _extract_balanced_json(text: str, start: int) -> str | None:
        return _extract_balanced_json(text, start)
