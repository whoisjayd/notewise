from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import unescape
from typing import Any
from xml.etree import ElementTree

import structlog

from notewise._constants import SECONDS_PER_HOUR, SECONDS_PER_MINUTE
from notewise.youtube._constants import TRANSCRIPT_FORMAT_PRIORITY


EXT_PRIORITY = TRANSCRIPT_FORMAT_PRIORITY
_TAG_RE = re.compile(r"<[^>]+>")
logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)
_PARSER_FALLBACK_ERRORS = (
    json.JSONDecodeError,
    ElementTree.ParseError,
    TypeError,
    ValueError,
)


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    duration: float
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "duration": self.duration,
            "text": self.text,
        }


@dataclass(frozen=True)
class TrackSelection:
    source: str
    language_code: str
    is_generated: bool
    track: dict[str, Any]


def select_track(
    subtitles: dict[str, list[dict[str, Any]]],
    automatic_captions: dict[str, list[dict[str, Any]]],
    languages: list[str] | None,
    include_automatic: bool = True,
) -> TrackSelection | None:
    requested = [lang.strip().lower() for lang in (languages or []) if lang.strip()]
    sources: list[tuple[str, dict[str, list[dict[str, Any]]], bool]] = [
        ("subtitles", subtitles or {}, False)
    ]
    if include_automatic:
        sources.append(("automatic_captions", automatic_captions or {}, True))

    for source_name, by_lang, is_generated in sources:
        lang = _pick_language(by_lang, requested)
        if not lang:
            continue
        best = _pick_best_track(by_lang[lang])
        if not best:
            continue
        return TrackSelection(
            source=source_name,
            language_code=lang,
            is_generated=is_generated,
            track=best,
        )
    return None


def parse_transcript_payload(payload: str, ext: str | None) -> list[TranscriptSegment]:
    normalized_ext = (ext or "").lower()
    if normalized_ext.startswith("json"):
        return _parse_json3(payload)
    if normalized_ext in {"srv1", "srv2", "srv3", "xml", "ttml"}:
        return _parse_xml(payload)
    if normalized_ext == "vtt":
        return _parse_vtt(payload)

    for parser in (_parse_json3, _parse_xml, _parse_vtt):
        try:
            parsed = parser(payload)
            if parsed:
                return parsed
        except _PARSER_FALLBACK_ERRORS:
            continue
    return []


def _pick_language(
    by_lang: dict[str, list[dict[str, Any]]],
    requested: list[str],
) -> str | None:
    if not by_lang:
        return None
    if not requested:
        return sorted(by_lang.keys())[0]

    lowered = {key.lower(): key for key in by_lang}
    ordered: list[str] = []

    for lang in requested:
        if lang in lowered:
            ordered.append(lowered[lang])
            continue
        for key in by_lang:
            key_l = key.lower()
            if key_l.startswith(f"{lang}-") or lang.startswith(f"{key_l}-"):
                ordered.append(key)
    if ordered:
        seen: set[str] = set()
        for key in ordered:
            if key not in seen:
                seen.add(key)
                return key
    fallback = sorted(by_lang.keys())[0]
    logger.warning(
        "transcript.language_fallback",
        requested=requested,
        available=sorted(by_lang.keys()),
        selected=fallback,
    )
    return fallback


def _pick_best_track(tracks: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not tracks:
        return None
    rank = {ext: idx for idx, ext in enumerate(EXT_PRIORITY)}

    def key_fn(track: dict[str, Any]) -> tuple[int, str]:
        ext = _infer_ext(track).lower()
        return (rank.get(ext, len(EXT_PRIORITY)), ext)

    return sorted(tracks, key=key_fn)[0]


def _infer_ext(track: dict[str, Any]) -> str:
    if track.get("ext"):
        return str(track["ext"])
    url = str(track.get("url") or "")
    m = re.search(r"[?&]fmt=([^&]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"\.([a-z0-9]+)(?:[?#]|$)", url.lower())
    if m:
        return m.group(1)
    return "unknown"


def _parse_json3(payload: str) -> list[TranscriptSegment]:
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        return []
    events = parsed.get("events") or []
    segments: list[TranscriptSegment] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        segs = event.get("segs") or []
        text = "".join(
            segment.get("utf8", "") for segment in segs if isinstance(segment, dict)
        )
        text = _clean_text(text)
        if not text:
            continue
        start_ms = float(event.get("tStartMs") or 0.0)
        duration_ms = float(event.get("dDurationMs") or 0.0)
        segments.append(
            TranscriptSegment(
                start=start_ms / 1000.0,
                duration=duration_ms / 1000.0,
                text=text,
            )
        )
    return segments


def _parse_xml(payload: str) -> list[TranscriptSegment]:
    root = ElementTree.fromstring(payload)
    segments: list[TranscriptSegment] = []
    for element in root.iter():
        tag = _local_tag(element.tag)
        if tag not in {"text", "p"}:
            continue
        text = _clean_text("".join(element.itertext()))
        if not text:
            continue
        start = _parse_time_or_seconds(
            element.attrib.get("start"), element.attrib.get("t"), scale_ms=True
        )
        duration = _parse_time_or_seconds(
            element.attrib.get("dur"), element.attrib.get("d"), scale_ms=True
        )
        segments.append(TranscriptSegment(start=start, duration=duration, text=text))
    return segments


def _parse_vtt(payload: str) -> list[TranscriptSegment]:
    lines = payload.splitlines()
    segments: list[TranscriptSegment] = []
    cue_text: list[str] = []
    start = 0.0
    end = 0.0
    in_cue = False

    for raw_line in lines:
        line = raw_line.strip("\ufeff")
        if "-->" in line:
            in_cue = True
            cue_text = []
            start_str, end_str = [part.strip() for part in line.split("-->", 1)]
            start = _parse_vtt_time(start_str.split(" ")[0])
            end = _parse_vtt_time(end_str.split(" ")[0])
            continue
        if not line.strip():
            if in_cue and cue_text:
                text = _clean_text(" ".join(cue_text))
                if text:
                    segments.append(
                        TranscriptSegment(
                            start=start,
                            duration=max(0.0, end - start),
                            text=text,
                        )
                    )
            in_cue = False
            cue_text = []
            continue
        if in_cue and not line.isdigit():
            cue_text.append(line.strip())

    if in_cue and cue_text:
        text = _clean_text(" ".join(cue_text))
        if text:
            segments.append(
                TranscriptSegment(
                    start=start,
                    duration=max(0.0, end - start),
                    text=text,
                )
            )
    return segments


def _parse_vtt_time(value: str) -> float:
    parts = value.strip().split(":")
    if len(parts) == 3:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
    elif len(parts) == 2:
        hours = 0
        minutes = int(parts[0])
        seconds = float(parts[1])
    else:
        return 0.0
    return (hours * SECONDS_PER_HOUR) + (minutes * SECONDS_PER_MINUTE) + seconds


def _parse_time_or_seconds(
    primary: str | None,
    fallback: str | None,
    scale_ms: bool,
) -> float:
    raw = primary if primary not in (None, "") else fallback
    if raw in (None, ""):
        return 0.0
    text = str(raw).strip()
    if ":" in text:
        return _parse_vtt_time(text)
    value = float(text)
    if scale_ms and fallback is not None and primary in (None, ""):
        return value / 1000.0
    return value


def _local_tag(value: str) -> str:
    if "}" in value:
        return value.rsplit("}", 1)[1]
    return value


def _clean_text(text: str) -> str:
    cleaned = unescape(text)
    cleaned = _TAG_RE.sub("", cleaned)
    cleaned = cleaned.replace("\n", " ").replace("\r", " ")
    return re.sub(r"\s+", " ", cleaned).strip()
