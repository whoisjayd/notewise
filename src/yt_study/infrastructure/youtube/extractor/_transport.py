"""Private transport helpers for the native YouTube extractor."""

from __future__ import annotations

import copy
import json
from typing import Any, cast
from urllib.request import Request

from yt_study.errors import ExtractionError
from yt_study.infrastructure.youtube._constants import (
    ANDROID_CLIENT_NAME,
    ANDROID_CLIENT_VERSION,
    ANDROID_USER_AGENT,
    DEFAULT_ACCEPT_LANGUAGE,
    INNERTUBE_CLIENT_NAME,
    INNERTUBE_CLIENT_VERSION,
    REQUEST_TIMEOUT_SECONDS,
)
from yt_study.infrastructure.youtube.extractor import _auth as _auth_ops
from yt_study.infrastructure.youtube.extractor.parsers import (
    parse_transcript_payload,
    select_track,
)


def _fetch_text(client: Any, url: str) -> str:
    req = Request(url=url, headers=_auth_ops._default_headers(), method="GET")
    try:
        with client._opener.open(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            body = resp.read()
            if isinstance(body, bytes):
                return body.decode("utf-8", errors="replace")
            return str(body)
    except Exception as exc:
        raise ExtractionError(f"Request failed for {url}: {exc}", url=url) from exc


def _fetch_json(
    client: Any,
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
        with client._opener.open(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ExtractionError(f"Unexpected JSON response type for {url}")
        return data
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"Request failed for {url}: {exc}", url=url) from exc


def _transcript_via_innertube_player(
    client: Any,
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
            "clientName": ANDROID_CLIENT_NAME,
            "clientVersion": ANDROID_CLIENT_VERSION,
            "userAgent": ANDROID_USER_AGENT,
        },
    ]
    for override in contexts:
        try:
            player = client._call_innertube(
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
        subtitles, automatic = client._build_subtitles(captions)
        selection = select_track(
            subtitles=subtitles,
            automatic_captions=automatic,
            languages=languages,
            include_automatic=include_automatic,
        )
        if not selection or not selection.track.get("url"):
            continue
        try:
            payload = client._fetch_text(selection.track["url"])
            segments = [
                s.to_dict()
                for s in parse_transcript_payload(payload, selection.track.get("ext"))
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
    client: Any,
    video_id: str,
    api_key: str,
    ytcfg: dict[str, Any],
) -> dict[str, Any] | None:
    try:
        return cast(
            dict[str, Any],
            client._call_innertube(
                endpoint="player",
                api_key=api_key,
                ytcfg=ytcfg,
                body={"videoId": video_id},
            ),
        )
    except Exception:
        return None


def _call_innertube(
    client: Any,
    endpoint: str,
    api_key: str,
    ytcfg: dict[str, Any],
    body: dict[str, Any],
    client_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = client._extract_context(ytcfg, client_override=client_override)
    payload = {"context": context}
    payload.update(body)
    headers = client._generate_api_headers(ytcfg, context)
    headers["Content-Type"] = "application/json"
    url = f"https://www.youtube.com/youtubei/v1/{endpoint}?key={api_key}&prettyPrint=false"
    return cast(dict[str, Any], client._fetch_json(url, payload, headers))


def _extract_context(
    _client: Any,
    ytcfg: dict[str, Any],
    client_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = copy.deepcopy(ytcfg.get("INNERTUBE_CONTEXT") or {})
    if not isinstance(context, dict):
        context = {}
    client_context = context.setdefault("client", {})
    if not isinstance(client_context, dict):
        client_context = {}
        context["client"] = client_context

    if client_override:
        for key in ("clientName", "clientVersion", "userAgent"):
            if client_override.get(key):
                client_context[key] = client_override[key]
    if not client_context.get("clientName"):
        client_context["clientName"] = INNERTUBE_CLIENT_NAME
    if not client_context.get("clientVersion"):
        client_context["clientVersion"] = INNERTUBE_CLIENT_VERSION
    client_context["hl"] = "en"
    client_context["timeZone"] = "UTC"
    client_context["utcOffsetMinutes"] = 0
    return context


def _generate_api_headers(
    client: Any,
    ytcfg: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, str]:
    client_context = (context.get("client") or {}) if isinstance(context, dict) else {}
    origin = "https://www.youtube.com"
    headers: dict[str, str] = {
        "Origin": origin,
        "Accept-Language": DEFAULT_ACCEPT_LANGUAGE,
        "User-Agent": (
            client_context.get("userAgent")
            or _auth_ops._default_headers()["User-Agent"]
        ),
        "X-YouTube-Client-Name": str(
            ytcfg.get("INNERTUBE_CONTEXT_CLIENT_NAME")
            or ytcfg.get("INNERTUBE_CLIENT_NAME")
            or 1
        ),
        "X-YouTube-Client-Version": str(
            client_context.get("clientVersion")
            or ytcfg.get("INNERTUBE_CONTEXT_CLIENT_VERSION")
            or INNERTUBE_CLIENT_VERSION
        ),
    }
    visitor_data = ytcfg.get("VISITOR_DATA") or (
        (ytcfg.get("INNERTUBE_CONTEXT") or {}).get("client") or {}
    ).get("visitorData")
    if visitor_data:
        headers["X-Goog-Visitor-Id"] = str(visitor_data)
    headers.update(_auth_ops._generate_cookie_auth_headers(client, ytcfg, origin))
    return headers
