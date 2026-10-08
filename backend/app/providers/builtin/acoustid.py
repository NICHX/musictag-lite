"""AcoustID 指纹识别源（P1，需申请 API Key，默认关闭）。"""

from __future__ import annotations

from app.providers.base import AlbumBundle, Candidate, CoverBytes, Lyrics, ScrapeQuery

_MILESTONE = "该 Provider 能力将在 M1/M2 实现"


class AcoustIDProvider:
    key = "acoustid"
    name = "AcoustID"
    capabilities = {"fingerprint", "metadata"}
    default_enabled = False  # 需 API Key，默认关闭
    default_priority = 90

    async def search(self, q: ScrapeQuery) -> list[Candidate]:
        return []

    async def fetch(self, external_id: str) -> AlbumBundle:
        raise NotImplementedError(_MILESTONE)

    async def fetch_cover(self, external_id: str) -> CoverBytes | None:
        return None

    async def fetch_lyrics(self, q: ScrapeQuery) -> Lyrics | None:
        return None

    async def identify(self, fingerprint: str, duration: int) -> list[Candidate]:
        raise NotImplementedError(_MILESTONE)
