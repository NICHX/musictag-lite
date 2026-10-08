"""Cover Art Archive 封面源（基于 MusicBrainz release mbid）。"""

from __future__ import annotations

from app.providers.base import (
    AlbumBundle,
    Candidate,
    CoverBytes,
    HTTPProvider,
    Lyrics,
    ScrapeQuery,
)

_FRONT = "https://coverartarchive.org/release/{mbid}/front-500"


class CoverArtArchiveProvider(HTTPProvider):
    key = "coverart"
    name = "Cover Art Archive"
    capabilities = {"cover"}
    default_enabled = True
    default_priority = 20
    min_interval = 1.0

    async def fetch_cover(self, external_id: str) -> CoverBytes | None:
        """external_id 为 MusicBrainz release mbid。"""
        return await self._get_bytes(_FRONT.format(mbid=external_id))

    async def search(self, q: ScrapeQuery) -> list[Candidate]:
        return []

    async def fetch(self, external_id: str) -> AlbumBundle:
        return AlbumBundle()

    async def fetch_lyrics(self, q: ScrapeQuery) -> Lyrics | None:
        return None

    async def identify(self, fingerprint: str, duration: int) -> list[Candidate]:
        return []
