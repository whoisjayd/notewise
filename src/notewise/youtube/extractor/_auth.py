"""Private auth helpers for the native YouTube extractor."""

from __future__ import annotations

import hashlib
import http.cookiejar
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from notewise.errors import ExtractionError
from notewise.youtube._constants import DEFAULT_ACCEPT_LANGUAGE


def _load_cookie_jar(cookie_file: str | None) -> http.cookiejar.CookieJar:
    jar = http.cookiejar.MozillaCookieJar()
    if cookie_file:
        path = Path(cookie_file)
        if not path.exists():
            raise ExtractionError(f"Cookie file not found: {cookie_file}")
        try:
            jar.load(str(path), ignore_discard=True, ignore_expires=True)
            for cookie in jar:
                if cookie.expires == 0:
                    cookie.expires = None
                    cookie.discard = True
        except Exception as exc:
            raise ExtractionError(f"Failed to load cookie file: {cookie_file}") from exc
    return jar


def _youtube_cookies(client: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for cookie in client._cookie_jar:
        domain = (cookie.domain or "").lstrip(".").lower()
        if domain != "youtube.com" and not domain.endswith(".youtube.com"):
            continue
        if cookie.value is None:
            continue
        out[cookie.name] = cookie.value
    return out


def _get_sid_cookies(client: Any) -> tuple[str | None, str | None, str | None]:
    cookies = _youtube_cookies(client)
    sapisid = cookies.get("SAPISID")
    one_p = cookies.get("__Secure-1PAPISID")
    three_p = cookies.get("__Secure-3PAPISID")
    return sapisid or three_p, one_p, three_p


def _make_sid_authorization(
    scheme: str,
    sid: str,
    origin: str,
    additional_parts: dict[str, str] | None,
    now: Callable[[], float] | None = None,
) -> str:
    timestamp = str(round((now or time.time)()))
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
    client: Any,
    origin: str,
    user_session_id: str | None,
    now: Callable[[], float] | None = None,
) -> str | None:
    sapisid, one_p, three_p = _get_sid_cookies(client)
    additional = {"u": user_session_id} if user_session_id else None
    out: list[str] = []
    for scheme, sid in (
        ("SAPISIDHASH", sapisid),
        ("SAPISID1PHASH", one_p),
        ("SAPISID3PHASH", three_p),
    ):
        if sid:
            out.append(
                _make_sid_authorization(
                    scheme,
                    sid,
                    origin,
                    additional,
                    now=now,
                )
            )
    return " ".join(out) if out else None


def _extract_session_index(ytcfg: dict[str, Any]) -> int | None:
    try:
        value = ytcfg.get("SESSION_INDEX")
        if value is None:
            return None
        return int(str(value))
    except ValueError:
        return None


def _extract_data_sync_id(ytcfg: dict[str, Any]) -> str | None:
    value = ytcfg.get("DATASYNC_ID")
    return str(value) if value else None


def _parse_data_sync_id(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    first, _, second = value.partition("||")
    if second:
        return first, second
    return None, first


def _extract_user_session_id(ytcfg: dict[str, Any]) -> str | None:
    if ytcfg.get("USER_SESSION_ID"):
        return str(ytcfg["USER_SESSION_ID"])
    return _parse_data_sync_id(_extract_data_sync_id(ytcfg))[1]


def _extract_delegated_session_id(ytcfg: dict[str, Any]) -> str | None:
    if ytcfg.get("DELEGATED_SESSION_ID"):
        return str(ytcfg["DELEGATED_SESSION_ID"])
    return _parse_data_sync_id(_extract_data_sync_id(ytcfg))[0]


def _generate_cookie_auth_headers(
    client: Any,
    ytcfg: dict[str, Any],
    origin: str,
    now: Callable[[], float] | None = None,
) -> dict[str, str]:
    headers: dict[str, str] = {}
    delegated_session_id = _extract_delegated_session_id(ytcfg)
    session_index = _extract_session_index(ytcfg)
    if delegated_session_id:
        headers["X-Goog-PageId"] = delegated_session_id
    if delegated_session_id or session_index is not None:
        headers["X-Goog-AuthUser"] = str(
            session_index if session_index is not None else 0
        )

    auth = _get_sid_authorization_header(
        client,
        origin=origin,
        user_session_id=_extract_user_session_id(ytcfg),
        now=now,
    )
    if auth:
        headers["Authorization"] = auth
        headers["X-Origin"] = origin
    if ytcfg.get("LOGGED_IN"):
        headers["X-Youtube-Bootstrap-Logged-In"] = "true"
    return headers


def _default_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": DEFAULT_ACCEPT_LANGUAGE,
    }


class _AuthMixin:
    def _load_cookie_jar(self, cookie_file: str | None) -> http.cookiejar.CookieJar:
        return _load_cookie_jar(cookie_file)

    def _youtube_cookies(self) -> dict[str, str]:
        return _youtube_cookies(self)

    def _get_sid_cookies(self) -> tuple[str | None, str | None, str | None]:
        return _get_sid_cookies(self)

    @staticmethod
    def _make_sid_authorization(
        scheme: str,
        sid: str,
        origin: str,
        additional_parts: dict[str, str] | None,
    ) -> str:
        return _make_sid_authorization(
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
        return _get_sid_authorization_header(
            self,
            origin=origin,
            user_session_id=user_session_id,
            now=time.time,
        )

    def _extract_session_index(self, ytcfg: dict[str, Any]) -> int | None:
        return _extract_session_index(ytcfg)

    def _parse_data_sync_id(self, value: str | None) -> tuple[str | None, str | None]:
        return _parse_data_sync_id(value)

    def _extract_user_session_id(self, ytcfg: dict[str, Any]) -> str | None:
        return _extract_user_session_id(ytcfg)

    def _extract_delegated_session_id(self, ytcfg: dict[str, Any]) -> str | None:
        return _extract_delegated_session_id(ytcfg)

    def _generate_cookie_auth_headers(
        self,
        ytcfg: dict[str, Any],
        origin: str,
    ) -> dict[str, str]:
        return _generate_cookie_auth_headers(
            self,
            ytcfg,
            origin,
            now=time.time,
        )
