"""MusicBrainz 元数据源（WS/2 API）。

M1 实现：search / fetch，遵守 1 req/s 限速并带磁盘缓存，需设置 User-Agent。
"""

from __future__ import annotations

from app.providers.base import AlbumBundle, Candidate, CoverBytes, Lyrics, ScrapeQuery

_MILESTONE = "该 Provider 能力将在 M1 实现"


class MusicBrainzProvider:
    key = "musicbrainz"
    name = "MusicBrainz"
    capabilities = {"metadata"}
    default_enabled = True
    default_priority = 10

    async def search(self, q: ScrapeQuery) -> list[Candidate]:
        raise NotImplementedError(_MILESTONE)

    async def fetch(self, external_id: str) -> AlbumBundle:
        raise NotImplementedError(_MILESTONE)

    async def fetch_cover(self, external_id: str) -> CoverBytes | None:
        return None

    async def fetch_lyrics(self, q: ScrapeQuery) -> Lyrics | None:
        return None

    async def identify(self, fingerprint: str, duration: int) -> list[Candidate]:
        return []
