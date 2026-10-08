"""MusicBrainz 元数据源（WS/2 API）。

遵守 1 req/s 限速（``min_interval``）；User-Agent 由共享 httpx 客户端统一提供。
"""

from __future__ import annotations

from typing import Any

from app.providers.base import (
    AlbumBundle,
    Candidate,
    CoverBytes,
    HTTPProvider,
    Lyrics,
    ScrapeQuery,
)

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
        query = self._build_query(q)
        if not query:
            return []
        data = await self._get_json(
            f"{_BASE}/recording", params={"query": query, "fmt": "json", "limit": 10}
        )
        if not data:
            return []

        candidates: list[Candidate] = []
        for item in data.get("recordings", []):
            releases = item.get("releases") or []
            release = releases[0] if releases else {}
            mbid = release.get("id")
            candidates.append(
                Candidate(
                    provider=self.key,
                    external_id=str(item.get("id", "")),
                    title=item.get("title"),
                    artist=_artist_credit(item),
                    album=release.get("title"),
                    year=(release.get("date") or "")[:4] or None,
                    score=float(item.get("score", 0) or 0) / 100.0,
                    cover_url=_CAA_FRONT.format(mbid=mbid) if mbid else None,
                    payload={"release_id": mbid, "length_ms": item.get("length")},
                )
            )
        return candidates

    @staticmethod
    def _build_query(q: ScrapeQuery) -> str:
        parts: list[str] = []
        title = q.title or q.filename_hint
        if title:
            parts.append(f'recording:"{title}"')
        if q.artist:
            parts.append(f'artist:"{q.artist}"')
        if q.album:
            parts.append(f'release:"{q.album}"')
        return " AND ".join(parts)

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
