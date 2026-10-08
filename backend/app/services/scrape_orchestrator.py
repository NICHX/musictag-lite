"""刮削编排：并发查询多 Provider、打分合并、应用候选（F7 / §9.4）。M1 实现。"""

from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.providers.base import Candidate, ScrapeQuery
from app.providers.registry import ProviderRegistry, provider_registry

_MILESTONE = "刮削编排将在 M1 实现"

logger = get_logger(__name__)


class ScrapeOrchestrator:
    """统一出口：所有 Provider 共用同一 httpx 客户端（超时/重试/限流/缓存）。"""

    def __init__(self, registry: ProviderRegistry | None = None) -> None:
        self.registry = registry or provider_registry
        self._settings = get_settings()
        self._client: httpx.AsyncClient | None = None

    def client(self) -> httpx.AsyncClient:
        """惰性创建共享的异步 HTTP 客户端。"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._settings.http_timeout,
                headers={"User-Agent": self._settings.musicbrainz_user_agent},
                follow_redirects=True,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def search(
        self, query: ScrapeQuery, providers: list[str] | None = None
    ) -> list[Candidate]:
        raise NotImplementedError(_MILESTONE)

    async def apply(
        self, track_id: int, candidate_ids: list[str], *, only_missing: bool = False
    ) -> list[str]:
        raise NotImplementedError(_MILESTONE)


scrape_orchestrator = ScrapeOrchestrator()
