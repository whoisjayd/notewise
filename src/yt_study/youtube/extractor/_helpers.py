"""Pure helper utilities for the native YouTube extractor."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from yt_study.errors import ExtractionError


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
    raise ExtractionError(f"Unable to determine video id from {target}")


def _looks_like_playlist_url(target: str) -> bool:
    if "://" not in target:
        return False
    p = urlparse(target)
    qs = parse_qs(p.query)
    return bool(qs.get("list")) and ("/playlist" in p.path or not qs.get("v"))


def _extract_playlist_id(target: str) -> str:
    p = urlparse(target)
    pid = parse_qs(p.query).get("list", [None])[0]
    if not pid:
        raise ExtractionError(f"Unable to determine playlist id from {target}")
    return pid


def _with_fmt_json3(url: str) -> str:
    p = urlparse(url)
    qs = parse_qs(p.query)
    qs["fmt"] = ["json3"]
    p = p._replace(query=urlencode(qs, doseq=True))
    return p.geturl()


def _to_int(v: Any) -> int | None:
    try:
        return int(str(v)) if v not in (None, "") else None
    except Exception:
        return None


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


def _best_thumbnail(items: list[dict[str, Any]] | None) -> str | None:
    if not items:
        return None
    best = max(
        items, key=lambda x: (int(x.get("width") or 0), int(x.get("height") or 0))
    )
    url = best.get("url")
    return url if isinstance(url, str) else None


def _get_text(v: Any) -> str | None:
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        simple_text = v.get("simpleText")
        if isinstance(simple_text, str):
            return simple_text
        runs = v.get("runs")
        if isinstance(runs, list):
            out = "".join(str(x.get("text", "")) for x in runs if isinstance(x, dict))
            return out or None
        text_value = v.get("text")
        if isinstance(text_value, str):
            return text_value
    return None


def _date_to_yyyymmdd(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y%m%d")
    except Exception:
        if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
            return value.replace("-", "")
        return None


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


def _parse_count(text: str | None) -> int | None:
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


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


def _first_key(node: Any, key: str) -> dict[str, Any] | None:
    found = _find_key(node, key)
    return found[0][key] if found else None


class _HelperMixin:
    @staticmethod
    def _select_simple_video_fields(video: dict[str, Any]) -> dict[str, Any]:
        return _select_simple_video_fields(video)

    @staticmethod
    def _extract_video_id(target: str) -> str:
        return _extract_video_id(target)

    @staticmethod
    def _looks_like_playlist_url(target: str) -> bool:
        return _looks_like_playlist_url(target)

    @staticmethod
    def _extract_playlist_id(target: str) -> str:
        return _extract_playlist_id(target)

    @staticmethod
    def _with_fmt_json3(url: str) -> str:
        return _with_fmt_json3(url)

    @staticmethod
    def _to_int(v: Any) -> int | None:
        return _to_int(v)

    @staticmethod
    def _parse_duration(text: str | None) -> int | None:
        return _parse_duration(text)

    @staticmethod
    def _best_thumbnail(items: list[dict[str, Any]] | None) -> str | None:
        return _best_thumbnail(items)

    @staticmethod
    def _get_text(v: Any) -> str | None:
        return _get_text(v)

    @staticmethod
    def _date_to_yyyymmdd(value: str | None) -> str | None:
        return _date_to_yyyymmdd(value)

    @staticmethod
    def _iso_to_unix(value: str | None) -> int | None:
        return _iso_to_unix(value)

    @staticmethod
    def _availability(playability: dict[str, Any]) -> str:
        return _availability(playability)

    @staticmethod
    def _parse_count(text: str | None) -> int | None:
        return _parse_count(text)

    @staticmethod
    def _find_key(node: Any, key: str) -> list[dict[str, Any]]:
        return _find_key(node, key)

    @staticmethod
    def _first_key(node: Any, key: str) -> dict[str, Any] | None:
        return _first_key(node, key)
