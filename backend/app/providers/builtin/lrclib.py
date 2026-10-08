"""LRCLIB 歌词源（开放 API，无需 Key，支持精确/模糊查询）。"""

from __future__ import annotations

import re
from typing import Any

from app.providers.base import (
    AlbumBundle,
    Candidate,
    CoverBytes,
    HTTPProvider,
    Lyrics,
    ScrapeQuery,
)

_GET = "https://lrclib.net/api/get"
_SEARCH = "https://lrclib.net/api/search"
_SEPARATOR = re.compile(r"\s+-\s+")


def split_filename_hint(hint: str | None) -> tuple[str | None, str | None]:
    """把 "标题 - 艺术家" 形式的文件名提示拆成 (标题, 艺术家)。"""
    if not hint:
        return None, None
    parts = [part.strip() for part in _SEPARATOR.split(hint) if part.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return parts[0] if parts else None, None


class LRCLIBProvider(HTTPProvider):
    key = "lrclib"
    name = "LRCLIB"
    capabilities = {"lyrics"}
    default_enabled = True
    default_priority = 30

    async def fetch_lyrics(self, q: ScrapeQuery) -> Lyrics | None:
        title = q.title
        artist = q.artist
        if not title:
            title, hint_artist = split_filename_hint(q.filename_hint)
            artist = artist or hint_artist
        if not title:
            return None

        params: dict[str, Any] = {"track_name": title}
        if artist:
            params["artist_name"] = artist
        if q.album:
            params["album_name"] = q.album
        if q.duration:
            params["duration"] = int(q.duration)

        exact = await self._get_json(_GET, params=params)
        if isinstance(exact, dict):
            lyrics = self._to_lyrics(exact)
            if lyrics is not None:
                return lyrics

        results = await self._get_json(_SEARCH, params=params)
        if isinstance(results, list):
            for item in results:
                lyrics = self._to_lyrics(item)
                if lyrics is not None:
                    return lyrics
        return None

    @staticmethod
    def _to_lyrics(item: dict[str, Any]) -> Lyrics | None:
        synced = item.get("syncedLyrics")
        if synced:
            return Lyrics(content=str(synced), format="lrc", source="lrclib")
        plain = item.get("plainLyrics")
        if plain:
            return Lyrics(content=str(plain), format="plain", source="lrclib")
        return None

    async def search(self, q: ScrapeQuery) -> list[Candidate]:
        return []

    async def fetch(self, external_id: str) -> AlbumBundle:
        return AlbumBundle()

    async def fetch_cover(self, external_id: str) -> CoverBytes | None:
        return None

    async def identify(self, fingerprint: str, duration: int) -> list[Candidate]:
        return []
