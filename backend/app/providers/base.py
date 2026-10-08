"""Provider 抽象接口与数据结构（对应设计文档 §9.1）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

Capability = str  # "metadata" | "cover" | "lyrics" | "fingerprint"


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
