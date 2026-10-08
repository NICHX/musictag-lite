"""LRCLIB 歌词源（开放 API，无需 Key，支持精确/模糊查询）。"""

from __future__ import annotations

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


class LRCLIBProvider(HTTPProvider):
    key = "lrclib"
    name = "LRCLIB"
    capabilities = {"lyrics"}
    default_enabled = True
    default_priority = 30

    async def fetch_lyrics(self, q: ScrapeQuery) -> Lyrics | None:
        title = q.title or q.filename_hint
        if not title:
            return None

        params: dict[str, Any] = {"track_name": title}
        if q.artist:
            params["artist_name"] = q.artist
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
