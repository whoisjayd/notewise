"""Private transport helpers for the native YouTube extractor."""

from __future__ import annotations

import copy
import json
import random
import time
from http.client import RemoteDisconnected
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request

import structlog

from yt_study._constants import HTTP_BACKOFF_BASE, HTTP_MAX_RETRIES
from yt_study.errors import ExtractionError
from yt_study.youtube._constants import (
    ANDROID_CLIENT_NAME,
    ANDROID_CLIENT_VERSION,
    ANDROID_USER_AGENT,
    DEFAULT_ACCEPT_LANGUAGE,
    INNERTUBE_CLIENT_NAME,
    INNERTUBE_CLIENT_VERSION,
    REQUEST_TIMEOUT_SECONDS,
)

from . import _auth as _auth_ops
from ._parsers import (
    parse_transcript_payload,
    select_track,
)


logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


def _is_retryable_transport_error(exc: Exception) -> bool:
    """Return whether the opener exception is safe to retry."""
    if isinstance(exc, HTTPError):
        return exc.code in {429, 500, 502, 503, 504}
    if isinstance(exc, (TimeoutError, ConnectionResetError, ConnectionAbortedError)):
        return True
    if isinstance(exc, RemoteDisconnected):
        return True
    if isinstance(exc, URLError):
        reason = exc.reason
        if isinstance(
            reason,
            (
                TimeoutError,
                ConnectionResetError,
                ConnectionAbortedError,
                RemoteDisconnected,
            ),
        ):
            return True
        lowered = str(reason).lower()
        return any(
            token in lowered
            for token in (
                "timed out",
                "timeout",
                "connection reset",
                "connection aborted",
                "remote end closed connection",
            )
        )
    return False


def _retry_backoff_seconds(attempt: int) -> float:
    """Return exponential backoff with bounded jitter for one retry attempt."""
    return float(HTTP_BACKOFF_BASE * (2**attempt) * random.uniform(0.8, 1.2))


def _fetch_with_retry(
    operation: Any,
    *,
    url: str,
) -> Any:
    """Run one transport operation with bounded transient retry/backoff."""
    for attempt in range(HTTP_MAX_RETRIES + 1):
        try:
            return operation()
        except Exception as exc:
            if not _is_retryable_transport_error(exc) or attempt >= HTTP_MAX_RETRIES:
                raise
            backoff_seconds = _retry_backoff_seconds(attempt)
            logger.warning(
                "youtube.transport_retry",
                url=url,
                attempt=attempt + 1,
                max_retries=HTTP_MAX_RETRIES,
                error=str(exc),
                backoff_seconds=round(backoff_seconds, 3),
            )
            time.sleep(backoff_seconds)


def _fetch_text(client: Any, url: str) -> str:
    req = Request(url=url, headers=_auth_ops._default_headers(), method="GET")
    try:
        with _fetch_with_retry(
            lambda: client._opener.open(req, timeout=REQUEST_TIMEOUT_SECONDS),
            url=url,
        ) as resp:
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
        with _fetch_with_retry(
            lambda: client._opener.open(req, timeout=REQUEST_TIMEOUT_SECONDS),
            url=url,
        ) as resp:
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


class _TransportMixin:
    def _fetch_text(self, url: str) -> str:
        return _fetch_text(self, url)

    def _fetch_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        return _fetch_json(self, url, payload, headers)

    def _transcript_via_innertube_player(
        self,
        video_id: str,
        api_key: str | None,
        ytcfg: dict[str, Any] | None,
        languages: list[str],
        include_automatic: bool,
    ) -> dict[str, Any] | None:
        return _transcript_via_innertube_player(
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
        return _player_response_from_innertube(self, video_id, api_key, ytcfg)

    def _call_innertube(
        self,
        endpoint: str,
        api_key: str,
        ytcfg: dict[str, Any],
        body: dict[str, Any],
        client_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _call_innertube(
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
        return _extract_context(self, ytcfg, client_override)

    def _generate_api_headers(
        self,
        ytcfg: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, str]:
        return _generate_api_headers(self, ytcfg, context)

    @staticmethod
    def _fetch_with_retry(operation: Any, *, url: str) -> Any:
        return _fetch_with_retry(operation, url=url)
