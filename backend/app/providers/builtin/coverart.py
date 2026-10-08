"""Cover Art Archive 封面源（基于 MusicBrainz release mbid）。

M1 实现：``coverartarchive.org/release/{mbid}`` 拉取 front 封面。
"""

from __future__ import annotations

from app.providers.base import AlbumBundle, Candidate, CoverBytes, Lyrics, ScrapeQuery

_MILESTONE = "该 Provider 能力将在 M1 实现"


class CoverArtArchiveProvider:
    key = "coverart"
    name = "Cover Art Archive"
    capabilities = {"cover"}
    default_enabled = True
    default_priority = 20

    async def search(self, q: ScrapeQuery) -> list[Candidate]:
        return []

    async def fetch(self, external_id: str) -> AlbumBundle:
        raise NotImplementedError(_MILESTONE)

    async def fetch_cover(self, external_id: str) -> CoverBytes | None:
        raise NotImplementedError(_MILESTONE)

    async def fetch_lyrics(self, q: ScrapeQuery) -> Lyrics | None:
        return None

    async def identify(self, fingerprint: str, duration: int) -> list[Candidate]:
        return []
