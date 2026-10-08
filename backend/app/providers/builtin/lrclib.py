"""LRCLIB 歌词源（开放 API，无需 Key，支持精确/模糊查询）。

M1 实现：``/api/get`` 与 ``/api/search``。
"""

from __future__ import annotations

from app.providers.base import AlbumBundle, Candidate, CoverBytes, Lyrics, ScrapeQuery

_MILESTONE = "该 Provider 能力将在 M1 实现"


class LRCLIBProvider:
    key = "lrclib"
    name = "LRCLIB"
    capabilities = {"lyrics"}
    default_enabled = True
    default_priority = 30

    async def search(self, q: ScrapeQuery) -> list[Candidate]:
        return []

    async def fetch(self, external_id: str) -> AlbumBundle:
        raise NotImplementedError(_MILESTONE)

    async def fetch_cover(self, external_id: str) -> CoverBytes | None:
        return None

    async def fetch_lyrics(self, q: ScrapeQuery) -> Lyrics | None:
        raise NotImplementedError(_MILESTONE)

    async def identify(self, fingerprint: str, duration: int) -> list[Candidate]:
        return []
