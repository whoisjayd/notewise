from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.request import HTTPCookieProcessor, build_opener

from notewise._constants import DEFAULT_LANGUAGES
from notewise.errors import ExtractionError

from ._auth import _AuthMixin
from ._helpers import _looks_like_playlist_url, _select_simple_video_fields
from ._parsers import (
    parse_transcript_payload,
    select_track,
)
from ._playlist import _PlaylistMixin
from ._transport import _TransportMixin
from ._video import _VideoMixin


if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass(frozen=True)
class YouTubeExtractorConfig:
    cookie_file: str | None = None
    verbose: int = 0


class YouTubeExtractorClient(
    _TransportMixin,
    _AuthMixin,
    _VideoMixin,
    _PlaylistMixin,
):
    def __init__(self, config: YouTubeExtractorConfig | None = None) -> None:
        self.config = config or YouTubeExtractorConfig()
        self._cookie_jar = self._load_cookie_jar(self.config.cookie_file)
        self._opener = build_opener(HTTPCookieProcessor(self._cookie_jar))

    def metadata(self, target: str) -> dict[str, Any]:
        if _looks_like_playlist_url(target):
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
            "data": _select_simple_video_fields(video),
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
        return self.transcript_from_video_data(
            target,
            video,
            languages,
            include_automatic,
        )

    def transcript_from_video_data(
        self,
        target: str,
        video: dict[str, Any],
        languages: Iterable[str] | None = None,
        include_automatic: bool = True,
    ) -> dict[str, Any]:
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
