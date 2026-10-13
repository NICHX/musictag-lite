"""Provider 抽象接口与数据结构（对应设计文档 §9.1）。"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import httpx

from app.core.cache import response_cache

Capability = str  # "metadata" | "cover" | "lyrics" | "fingerprint"

# 超过该体积的响应（多为封面）不入缓存，避免内存膨胀
_MAX_CACHED_BYTES = 512 * 1024

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
    # 每个请求都会附带的头（如部分平台要求的 Referer / UA）；空的键不覆盖共享客户端默认值
    extra_headers: dict[str, str] = {}

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

    def _cache_key(self, url: str, params: dict[str, Any] | None) -> tuple[Any, ...]:
        """按 Provider 隔离的缓存键（同 URL 在不同源下语义可能不同）。"""
        if not params:
            return (self.key, url)
        return (self.key, url, tuple(sorted((k, str(v)) for k, v in params.items())))

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
            response = await self.client.get(url, params=params, headers=self.extra_headers or None)
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
        """GET JSON（带缓存）；404 返回 None，其余非 2xx 抛出。"""
        key = self._cache_key(url, params)
        hit, cached = response_cache().get(key)
        if hit:
            return cached
        response = await self._get(url, params)
        if response.status_code == 404:
            result: Any | None = None
        else:
            response.raise_for_status()
            result = response.json()
        response_cache().set(key, result)
        return result

    async def _get_bytes(self, url: str, params: dict[str, Any] | None = None) -> CoverBytes | None:
        """GET 二进制（带缓存，用于封面）；404 返回 None。"""
        key = self._cache_key(url, params)
        hit, cached = response_cache().get(key)
        if hit:
            return cached
        response = await self._get(url, params)
        if response.status_code == 404:
            response_cache().set(key, None)
            return None
        response.raise_for_status()
        mime = response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        result = CoverBytes(data=response.content, mime=mime or "image/jpeg")
        if len(result.data) <= _MAX_CACHED_BYTES:
            response_cache().set(key, result)
        return result

    async def _post(self, url: str, data: dict[str, Any] | None = None) -> httpx.Response:
        """带限速与退避重试的 POST（表单编码；用于指纹等长参数）。"""
        response: httpx.Response | None = None
        for attempt in range(self.max_retries):
            await self._throttle()
            response = await self.client.post(url, data=data, headers=self.extra_headers or None)
            if response.status_code not in self.retry_statuses:
                return response
            if attempt < self.max_retries - 1:
                await asyncio.sleep(self._retry_delay(attempt, response))
        assert response is not None
        return response

    async def _post_json(self, url: str, data: dict[str, Any] | None = None) -> Any | None:
        """POST 表单并解析 JSON；404 返回 None。"""
        response = await self._post(url, data=data)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    async def _post_payload(self, url: str, payload: Any) -> Any | None:
        """POST JSON 请求体并解析 JSON 响应（带限速与退避重试）；404 返回 None。"""
        response: httpx.Response | None = None
        for attempt in range(self.max_retries):
            await self._throttle()
            response = await self.client.post(
                url, json=payload, headers=self.extra_headers or None
            )
            if response.status_code not in self.retry_statuses:
                break
            if attempt < self.max_retries - 1:
                await asyncio.sleep(self._retry_delay(attempt, response))
        if response is None or response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
