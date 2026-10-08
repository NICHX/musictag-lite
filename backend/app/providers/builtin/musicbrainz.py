"""MusicBrainz 元数据源（WS/2 API）。

遵守 1 req/s 限速（``min_interval``）；User-Agent 由共享 httpx 客户端统一提供。
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.logging import get_logger
from app.providers.base import (
    AlbumBundle,
    Candidate,
    CoverBytes,
    HTTPProvider,
    Lyrics,
    ScrapeQuery,
    split_filename_hint,
)

logger = get_logger(__name__)

_BASE = "https://musicbrainz.org/ws/2"
_CAA_FRONT = "https://coverartarchive.org/release/{mbid}/front-500"


def _artist_credit(entity: dict[str, Any]) -> str | None:
    credits = entity.get("artist-credit") or []
    names: list[str] = []
    for credit in credits:
        name = credit.get("name") or (credit.get("artist") or {}).get("name")
        if name:
            names.append(str(name))
    joined = " ".join(names)
    return joined or None


class MusicBrainzProvider(HTTPProvider):
    key = "musicbrainz"
    name = "MusicBrainz"
    capabilities = {"metadata"}
    default_enabled = True
    default_priority = 10
    min_interval = 1.0

    async def search(self, q: ScrapeQuery) -> list[Candidate]:
        """按 §9.4 的优先级：先用已有标签查询；无结果再回退到文件名解析。"""
        merged = await self._run_queries(self._build_queries(q))
        if not merged and q.title:
            # 标签可能拼写有误/不完整 → 用文件名兜底再查一次
            merged = await self._run_queries(self._filename_queries(q))
        return list(merged.values())

    async def _run_queries(self, queries: list[str]) -> dict[str, Candidate]:
        """执行若干查询并按 MB 内部 id 合并去重（单条失败不影响其余）。"""
        merged: dict[str, Candidate] = {}
        for query in queries:
            try:
                data = await self._get_json(
                    f"{_BASE}/recording", params={"query": query, "fmt": "json", "limit": 10}
                )
            except (httpx.HTTPError, OSError, ValueError) as exc:
                # 单条查询的网络/解析失败（限流、超时）不应丢弃其他查询的结果
                logger.warning(
                    "musicbrainz.search_query_failed", extra={"query": query, "error": str(exc)}
                )
                continue
            if not data:
                continue
            for item in data.get("recordings", []):
                candidate = self._to_candidate(item)
                if candidate.external_id and candidate.external_id not in merged:
                    merged[candidate.external_id] = candidate
            if merged:
                break  # 已有命中，无需再试下一种解释（省一次请求）
        return merged

    @staticmethod
    def _fielded(title: str, artist: str | None = None, album: str | None = None) -> str:
        """构造字段限定查询，如 recording:"1965" AND artist:"Zella Day"。"""
        parts = [f'recording:"{title}"']
        if artist:
            parts.append(f'artist:"{artist}"')
        if album:
            parts.append(f'release:"{album}"')
        return " AND ".join(parts)

    @classmethod
    def _build_queries(cls, q: ScrapeQuery) -> list[str]:
        """主查询：有标签按标签；无标签则用文件名。"""
        if q.title:
            queries = [cls._fielded(q.title, q.artist, q.album)]
            # 多艺术家（"A,B"）时补一条只用首位艺术家的查询作为兜底
            if q.artist and "," in q.artist:
                first = q.artist.split(",")[0].strip()
                if first:
                    queries.append(cls._fielded(q.title, first, q.album))
            return queries
        return cls._filename_queries(q)

    @classmethod
    def _filename_queries(cls, q: ScrapeQuery) -> list[str]:
        """文件名兜底查询：两种「标题/艺术家」顺序各一条。

        MB 的 Lucene 不支持带括号的 OR，因此发两次查询后合并。
        """
        left, right = split_filename_hint(q.filename_hint)
        queries: list[str] = []
        if left and right:
            queries.append(cls._fielded(left, right))
            if right != left:
                queries.append(cls._fielded(right, left))
        elif left:
            queries.append(left)  # 无分隔符：退化为宽松检索
        return queries

    @staticmethod
    def _to_candidate(item: dict[str, Any]) -> Candidate:
        releases = item.get("releases") or []
        release = releases[0] if releases else {}
        mbid = release.get("id")
        return Candidate(
            provider=MusicBrainzProvider.key,
            external_id=str(item.get("id", "")),
            title=item.get("title"),
            artist=_artist_credit(item),
            album=release.get("title"),
            year=(release.get("date") or "")[:4] or None,
            score=float(item.get("score", 0) or 0) / 100.0,
            cover_url=_CAA_FRONT.format(mbid=mbid) if mbid else None,
            payload={"release_id": mbid, "length_ms": item.get("length")},
        )

    async def fetch(self, external_id: str) -> AlbumBundle:
        """external_id 为 recording id；返回其首个 release 的规范化数据。"""
        data = await self._get_json(
            f"{_BASE}/recording/{external_id}",
            params={"inc": "releases+artist-credits", "fmt": "json"},
        )
        if not data:
            return AlbumBundle()
        releases = data.get("releases") or []
        release = releases[0] if releases else {}
        mbid = release.get("id")
        return AlbumBundle(
            title=data.get("title"),
            artist=_artist_credit(data),
            album=release.get("title"),
            year=(release.get("date") or "")[:4] or None,
            cover_url=_CAA_FRONT.format(mbid=mbid) if mbid else None,
            extra={"release_id": mbid, "recording_id": data.get("id")},
        )

    async def fetch_cover(self, external_id: str) -> CoverBytes | None:
        return None  # 封面由 Cover Art Archive 提供

    async def fetch_lyrics(self, q: ScrapeQuery) -> Lyrics | None:
        return None

    async def identify(self, fingerprint: str, duration: int) -> list[Candidate]:
        return []
