"""AcoustID 指纹识别源（F14，需申请 API Key，默认关闭）。

- 只发送 **音频指纹**（由本地 fpcalc 生成）与时长，**不上传音频本体**；
- 用 POST 表单提交（指纹字符串较长，避免 URL 超长）；
- 识别结果给出 MusicBrainz recording id，进一步可委托 MusicBrainz 取发行信息。
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.providers.base import (
    AlbumBundle,
    Candidate,
    CoverBytes,
    HTTPProvider,
    Lyrics,
    ScrapeQuery,
)

logger = get_logger(__name__)

_BASE = "https://api.acoustid.org/v2/lookup"


class AcoustIDProvider(HTTPProvider):
    key = "acoustid"
    name = "AcoustID"
    capabilities = {"fingerprint", "metadata"}
    default_enabled = False  # 需 API Key，默认关闭
    default_priority = 90
    min_interval = 0.34  # 官方建议 ≤ 3 req/s

    def __init__(self) -> None:
        super().__init__()
        self._api_key: str | None = None

    def configure(self, api_key: str | None) -> None:
        """由编排层注入生效的 API Key（界面设置 > 环境变量）。"""
        self._api_key = api_key

    def _key(self) -> str | None:
        return self._api_key or get_settings().acoustid_api_key

    async def search(self, q: ScrapeQuery) -> list[Candidate]:
        """仅在查询带指纹时生效；否则交给其他元数据源。"""
        if not q.fingerprint:
            return []
        return await self.identify(q.fingerprint, q.duration or 0)

    async def identify(self, fingerprint: str, duration: int) -> list[Candidate]:
        key = self._key()
        if not fingerprint or not key:
            if not key:
                logger.warning("acoustid.missing_key")
            return []
        data = await self._post_json(
            _BASE,
            data={
                "client": key,
                "meta": "recordings releasegroups compress",
                "duration": int(duration or 0),
                "fingerprint": fingerprint,
            },
        )
        if not data:
            return []
        return self._to_candidates(data)

    @staticmethod
    def _to_candidates(data: dict[str, Any]) -> list[Candidate]:
        candidates: list[Candidate] = []
        for result in data.get("results", []):
            score = float(result.get("score") or 0)
            acoustid_id = result.get("id")
            for recording in result.get("recordings", []):
                external_id = recording.get("id")
                if not external_id:
                    continue
                release_groups = recording.get("releasegroups") or []
                group = release_groups[0] if release_groups else {}
                candidates.append(
                    Candidate(
                        provider=AcoustIDProvider.key,
                        external_id=str(external_id),
                        title=recording.get("title"),
                        artist=_artist_names(recording.get("artists")),
                        album=group.get("title"),
                        year=(group.get("first-release-date") or "")[:4] or None,
                        score=score,
                        payload={
                            "acoustid": acoustid_id,
                            "releasegroup_id": group.get("id"),
                        },
                    )
                )
        return candidates

    async def fetch(self, external_id: str) -> AlbumBundle:
        """委托 MusicBrainz（external_id 为 recording id）取规范化数据。"""
        from app.providers.registry import provider_registry

        musicbrainz = provider_registry.get("musicbrainz")
        if musicbrainz is None:
            return AlbumBundle()
        return await musicbrainz.fetch(external_id)

    async def fetch_cover(self, external_id: str) -> CoverBytes | None:
        return None  # 封面由 Cover Art Archive 提供

    async def fetch_lyrics(self, q: ScrapeQuery) -> Lyrics | None:
        return None


def _artist_names(artists: list[dict[str, Any]] | None) -> str | None:
    names = [str(item.get("name")) for item in (artists or []) if item.get("name")]
    return ", ".join(names) or None
