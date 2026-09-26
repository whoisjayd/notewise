"""Private playlist extraction helpers for the native YouTube extractor."""

from __future__ import annotations

from typing import Any

import structlog

from notewise.errors import ExtractionError
from notewise.youtube._constants import (
    ANDROID_CLIENT_OVERRIDE,
    LOCKUP_CONTENT_TYPE_VIDEO,
    LOCKUP_METADATA,
    LOCKUP_VIEW_MODEL,
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


logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


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
            expected_count=playlist_count,
        )
        if playlist_count and len(entries) < playlist_count:
            # Never truncate silently: a short playlist looks complete unless
            # the gap is stated.
            logger.warning(
                "playlist.extracted_fewer_than_declared",
                playlist_id=playlist_id,
                extracted=len(entries),
                declared=playlist_count,
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


def _fetch_continuation_pages(
    client: Any,
    api_key: str,
    ytcfg: dict[str, Any] | None,
    token: str | None,
    out: list[dict[str, Any]],
    seen: set[str],
    client_override: dict[str, Any] | None = None,
) -> tuple[bool, bool]:
    """Follow a continuation chain, appending new entries to ``out``.

    Returns ``(server_stopped, last_page_added)``: whether the chain ended
    because the server stopped issuing tokens rather than the page budget
    running out, and whether the final page actually yielded new entries.
    """
    seen_tokens: set[str] = set()
    last_page_added = False
    for _ in range(MAX_PLAYLIST_PAGES):
        if not token:
            return True, last_page_added
        if token in seen_tokens:
            return False, last_page_added
        seen_tokens.add(token)
        try:
            page = client._call_innertube(
                endpoint="browse",
                api_key=api_key,
                ytcfg=ytcfg or {},
                body={"continuation": token},
                client_override=client_override,
            )
        except Exception as error:
            raise ExtractionError(
                f"Failed to fetch playlist continuation page: {error}"
            ) from error
        before = len(out)
        out.extend(client._extract_playlist_entries(page, seen))
        last_page_added = len(out) > before
        token = client._extract_continuation_token(page)
    return False, last_page_added


def _extract_playlist_entries_paginated(
    client: Any,
    data: dict[str, Any],
    api_key: str | None,
    ytcfg: dict[str, Any] | None,
    expected_count: int | None = None,
) -> list[dict[str, Any]]:
    """Collect every playlist entry, following continuations as needed.

    The web client stops issuing continuation tokens at roughly 200 entries, so
    a longer playlist is only complete if the chain is resumed with the Android
    client, which keeps paginating and answers with ``playlistVideoRenderer``.
    Entries already collected are skipped, so the resumed chain can safely
    replay the pages the web client already saw.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    out.extend(client._extract_playlist_entries(data, seen))

    if not api_key:
        return out

    def complete() -> bool:
        return expected_count is not None and len(out) >= expected_count

    first_token = client._extract_continuation_token(data)
    server_stopped, last_page_added = _fetch_continuation_pages(
        client, api_key, ytcfg, first_token, out, seen
    )
    if not server_stopped or complete():
        return out
    # The ~200 ceiling looks like the chain dying while it was still yielding
    # entries. A chain that ended on an empty page has nothing left to fetch,
    # so replaying it under the Android client only costs round-trips - unless
    # a declared count says we are genuinely short.
    if expected_count is None and not last_page_added:
        return out

    logger.debug(
        "Web continuation chain ended early; resuming with the Android client",
        collected=len(out),
        expected=expected_count,
    )
    _fetch_continuation_pages(
        client,
        api_key,
        ytcfg,
        first_token,
        out,
        seen,
        client_override=ANDROID_CLIENT_OVERRIDE,
    )
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
    for obj in _find_key(data, LOCKUP_VIEW_MODEL):
        r = obj[LOCKUP_VIEW_MODEL]
        if r.get("contentType") != LOCKUP_CONTENT_TYPE_VIDEO:
            continue
        vid = r.get("contentId")
        if not isinstance(vid, str) or not vid or vid in seen:
            continue
        seen.add(vid)
        metadata = (r.get("metadata") or {}).get(LOCKUP_METADATA) or {}
        out.append(
            {
                "id": vid,
                "title": _get_text(metadata.get("title")) or "",
                "url": f"https://www.youtube.com/watch?v={vid}",
                # The lockup layout omits length and byline; a badge overlay
                # carries the duration only on some renderings.
                "duration": None,
                "channel": None,
                "uploader": None,
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
        expected_count: int | None = None,
    ) -> list[dict[str, Any]]:
        return _extract_playlist_entries_paginated(
            self, data, api_key, ytcfg, expected_count
        )

    def _extract_playlist_entries(
        self,
        data: dict[str, Any],
        seen: set[str],
    ) -> list[dict[str, Any]]:
        return _extract_playlist_entries(data, seen)

    def _extract_continuation_token(self, node: Any) -> str | None:
        return _extract_continuation_token(node)
