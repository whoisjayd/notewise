"""Private playlist extraction helpers for the native YouTube extractor."""

from __future__ import annotations

from typing import Any

from notewise.errors import ExtractionError
from notewise.youtube._constants import (
    MAX_PLAYLIST_PAGES,
    YOUTUBE_PLAYLIST_URL,
)
from notewise.youtube.extractor._helpers import (
    _extract_playlist_id,
    _find_key,
    _first_key,
    _get_text,
    _parse_count,
    _parse_duration,
)


def _extract_playlist(
    client: Any,
    target: str,
    include_entries: bool,
) -> dict[str, Any]:
    playlist_id = _extract_playlist_id(target)
    webpage_url = YOUTUBE_PLAYLIST_URL.format(playlist_id=playlist_id)
    html = client._fetch_text(webpage_url)
    ytcfg = client._extract_ytcfg(html) or {}
    api_key = client._extract_innertube_api_key(html, ytcfg)
    data = client._extract_initial_data(html) or {}

    meta_renderer = _first_key(data, "playlistMetadataRenderer") or {}
    primary = _first_key(data, "playlistSidebarPrimaryInfoRenderer") or {}
    secondary = _first_key(data, "playlistSidebarSecondaryInfoRenderer") or {}

    title = meta_renderer.get("title") or _get_text(primary.get("title")) or ""
    description = meta_renderer.get("description") or ""
    owner = _get_text(
        ((secondary.get("videoOwner") or {}).get("videoOwnerRenderer") or {}).get(
            "title"
        )
    )

    stats = primary.get("stats") or []
    playlist_count = _parse_count(_get_text(stats[0])) if len(stats) > 0 else None
    view_count = _parse_count(_get_text(stats[1])) if len(stats) > 1 else None

    entries: list[dict[str, Any]] = []
    if include_entries:
        entries = client._extract_playlist_entries_paginated(
            data,
            api_key=api_key,
            ytcfg=ytcfg,
        )
    if playlist_count is None:
        playlist_count = len(entries)

    availability = _playlist_availability(data)

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


def _playlist_availability(data: dict[str, Any]) -> str:
    """Infer playlist availability from structured page alerts, not title text."""
    for obj in _find_key(data, "alertRenderer"):
        renderer = obj.get("alertRenderer") or {}
        if not isinstance(renderer, dict):
            continue
        text = _get_text(renderer.get("text")) or _get_text(renderer.get("title"))
        if not text:
            continue
        lowered = text.lower()
        if "private playlist" in lowered or (
            "playlist" in lowered and "private" in lowered
        ):
            return "private"
        if "sign in" in lowered or "login" in lowered:
            return "private"
    return "public"


def _extract_playlist_entries_paginated(
    client: Any,
    data: dict[str, Any],
    api_key: str | None,
    ytcfg: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    out.extend(client._extract_playlist_entries(data, seen))

    if not api_key:
        return out

    token = client._extract_continuation_token(data)
    seen_tokens: set[str] = set()
    for _ in range(MAX_PLAYLIST_PAGES):
        if not token or token in seen_tokens:
            break
        seen_tokens.add(token)
        try:
            page = client._call_innertube(
                endpoint="browse",
                api_key=api_key,
                ytcfg=ytcfg or {},
                body={"continuation": token},
            )
        except Exception as error:
            raise ExtractionError(
                f"Failed to fetch playlist continuation page: {error}"
            ) from error
        out.extend(client._extract_playlist_entries(page, seen))
        token = client._extract_continuation_token(page)
    return out


def _extract_playlist_entries(
    data: dict[str, Any],
    seen: set[str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for obj in _find_key(data, "playlistVideoRenderer"):
        r = obj["playlistVideoRenderer"]
        vid = r.get("videoId")
        if not vid or vid in seen:
            continue
        seen.add(vid)
        out.append(
            {
                "id": vid,
                "title": _get_text(r.get("title")) or "",
                "url": f"https://www.youtube.com/watch?v={vid}",
                "duration": _parse_duration(_get_text(r.get("lengthText"))),
                "channel": _get_text(r.get("shortBylineText")),
                "uploader": _get_text(r.get("shortBylineText")),
                "ie_key": "Youtube",
            }
        )
    return out


def _extract_continuation_token(node: Any) -> str | None:
    for obj in _find_key(node, "continuationCommand"):
        token = (obj.get("continuationCommand") or {}).get("token")
        if isinstance(token, str) and token:
            return token
    for obj in _find_key(node, "nextContinuationData"):
        token = (obj.get("nextContinuationData") or {}).get("continuation")
        if isinstance(token, str) and token:
            return token
    for obj in _find_key(node, "reloadContinuationData"):
        token = (obj.get("reloadContinuationData") or {}).get("continuation")
        if isinstance(token, str) and token:
            return token
    return None


class _PlaylistMixin:
    def _extract_playlist(
        self,
        target: str,
        include_entries: bool,
    ) -> dict[str, Any]:
        return _extract_playlist(self, target, include_entries)

    def _extract_playlist_entries_paginated(
        self,
        data: dict[str, Any],
        api_key: str | None,
        ytcfg: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        return _extract_playlist_entries_paginated(self, data, api_key, ytcfg)

    def _extract_playlist_entries(
        self,
        data: dict[str, Any],
        seen: set[str],
    ) -> list[dict[str, Any]]:
        return _extract_playlist_entries(data, seen)

    def _extract_continuation_token(self, node: Any) -> str | None:
        return _extract_continuation_token(node)

    def _playlist_availability(self, data: dict[str, Any]) -> str:
        return _playlist_availability(data)
