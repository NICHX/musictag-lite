"""Provider 抽象接口与数据结构（对应设计文档 §9.1）。"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import httpx

Capability = str  # "metadata" | "cover" | "lyrics" | "fingerprint"

# 文件名里常见的「A - B」分隔（要求两侧至少一个空白，避免误切 "AC-DC"）
_FILENAME_SEPARATOR = re.compile(r"\s+-\s+")


def split_filename_hint(hint: str | None) -> tuple[str | None, str | None]:
    """把 "A - B" 形式的文件名提示拆成 (A, B)；无分隔符时返回 (hint, None)。

    命名惯例在不同曲库中可能是「标题 - 艺术家」也可能是「艺术家 - 标题」，
    调用方应两种顺序都尝试。
    """
    if not hint:
        return None, None
    parts = [part.strip() for part in _FILENAME_SEPARATOR.split(hint) if part.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return (parts[0] if parts else None), None


@dataclass
class ScrapeQuery:
    """刮削查询条件。"""

    title: str | None = None
    artist: str | None = None
    album: str | None = None
    track_no: int | None = None
    duration: int | None = None
    filename_hint: str | None = None
    fingerprint: str | None = None


@dataclass
class Candidate:
    """一条候选匹配结果。"""

    provider: str
    external_id: str
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    year: str | None = None
    track_no: int | None = None
    score: float = 0.0
    cover_url: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def uid(self) -> str:
        """全局唯一标识：``provider:external_id``。"""
        return f"{self.provider}:{self.external_id}"


@dataclass
class AlbumBundle:
    """规范化后的元数据集合。"""

    title: str | None = None
    artist: str | None = None
    album: str | None = None
    album_artist: str | None = None
    year: str | None = None
    track_no: int | None = None
    disc_no: int | None = None
    genre: str | None = None
    cover_url: str | None = None
    lyrics: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CoverBytes:
    """封面二进制数据。"""

    data: bytes
    mime: str = "image/jpeg"


@dataclass
class Lyrics:
    """歌词结果。"""

    content: str
    format: str = "lrc"
    source: str = ""


@runtime_checkable
class MetadataProvider(Protocol):
    """所有刮削源实现的统一接口。"""

    key: str
    name: str
    capabilities: set[Capability]
    default_enabled: bool
    default_priority: int

    async def search(self, q: ScrapeQuery) -> list[Candidate]: ...

    async def fetch(self, external_id: str) -> AlbumBundle: ...

    async def fetch_cover(self, external_id: str) -> CoverBytes | None: ...

    async def fetch_lyrics(self, q: ScrapeQuery) -> Lyrics | None: ...

    async def identify(self, fingerprint: str, duration: int) -> list[Candidate]: ...


class HTTPProvider:
    """带共享 httpx 客户端与限速能力的 Provider 基类。

    网络层统一出口（§9.3）：所有 Provider 复用同一个 AsyncClient，
    集中处理超时 / User-Agent / 重试 / 限流。
    """

    key: str = "provider"
    name: str = "Provider"
    capabilities: set[Capability] = set()
    default_enabled: bool = False
    default_priority: int = 100
    min_interval: float = 0.0  # 两次请求的最小间隔（秒），用于限速
    retry_statuses: set[int] = {429, 500, 502, 503, 504}  # 需要退避重试的状态码
    max_retries: int = 3

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    def bind(self, client: httpx.AsyncClient) -> None:
        self._client = client

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(f"Provider {self.key} 尚未绑定 HTTP 客户端")
        return self._client

    async def _throttle(self) -> None:
        if self.min_interval <= 0:
            return
        async with self._lock:
            elapsed = time.monotonic() - self._last_call
            wait = self.min_interval - elapsed
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
        """带限速与退避重试的 GET（对齐 MB 的限流要求：429/503 需退避）。"""
        response: httpx.Response | None = None
        for attempt in range(self.max_retries):
            await self._throttle()
            response = await self.client.get(url, params=params)
            if response.status_code not in self.retry_statuses:
                return response
            if attempt < self.max_retries - 1:
                await asyncio.sleep(self._retry_delay(attempt, response))
        assert response is not None
        return response

    @staticmethod
    def _retry_delay(attempt: int, response: httpx.Response) -> float:
        retry_after = response.headers.get("retry-after", "")
        if retry_after.isdigit():
            return min(float(retry_after), 10.0)
        return min(2.0**attempt, 8.0)

    async def _get_json(self, url: str, params: dict[str, Any] | None = None) -> Any | None:
        """GET JSON；404 返回 None，其余非 2xx 抛出。"""
        response = await self._get(url, params)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    async def _get_bytes(self, url: str, params: dict[str, Any] | None = None) -> CoverBytes | None:
        """GET 二进制（用于封面）；404 返回 None。"""
        response = await self._get(url, params)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        mime = response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        return CoverBytes(data=response.content, mime=mime or "image/jpeg")
