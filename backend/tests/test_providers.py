"""刮削 Provider 解析与打分测试（httpx.MockTransport，不访问网络）。"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from app.providers.base import Candidate, ScrapeQuery
from app.providers.builtin.coverart import CoverArtArchiveProvider
from app.providers.builtin.lrclib import LRCLIBProvider
from app.providers.builtin.musicbrainz import MusicBrainzProvider
from app.services.scrape_orchestrator import score_candidate


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _mb_body() -> dict:
    return {
        "recordings": [
            {
                "id": "rec-1",
                "title": "Rolling in the Deep",
                "score": 95,
                "artist-credit": [{"name": "Adele"}],
                "releases": [{"id": "rel-1", "title": "21", "date": "2011-01-24"}],
            }
        ]
    }


async def test_musicbrainz_search_parsing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/recording")
        assert request.url.params.get("query")
        return httpx.Response(200, json=_mb_body())

    provider = MusicBrainzProvider()
    provider.bind(_client(handler))
    results = await provider.search(ScrapeQuery(title="Rolling in the Deep", artist="Adele"))

    assert len(results) == 1
    candidate = results[0]
    assert candidate.external_id == "rec-1"
    assert candidate.artist == "Adele"
    assert candidate.album == "21"
    assert candidate.year == "2011"
    assert candidate.score == pytest.approx(0.95)
    assert candidate.cover_url and "rel-1" in candidate.cover_url


async def test_musicbrainz_fetch_bundle() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "rec-1",
                "title": "Rolling",
                "artist-credit": [{"name": "Adele"}],
                "releases": [{"id": "rel-1", "title": "21", "date": "2011-01-24"}],
            },
        )

    provider = MusicBrainzProvider()
    provider.bind(_client(handler))
    bundle = await provider.fetch("rec-1")
    assert bundle.title == "Rolling"
    assert bundle.album == "21"
    assert bundle.extra["release_id"] == "rel-1"


async def test_lrclib_exact_then_fallback() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/api/get"):
            return httpx.Response(404)
        return httpx.Response(200, json=[{"trackName": "X", "syncedLyrics": "[00:01.00]hi"}])

    provider = LRCLIBProvider()
    provider.bind(_client(handler))
    lyrics = await provider.fetch_lyrics(ScrapeQuery(title="X", artist="Y"))

    assert lyrics is not None
    assert lyrics.format == "lrc"
    assert lyrics.content == "[00:01.00]hi"
    assert len(calls) == 2  # 先精确、失败后模糊


async def test_coverart_fetch_cover() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/release/rel-1/front-500" in str(request.url)
        return httpx.Response(
            200, content=b"\xff\xd8\xff\xd9", headers={"content-type": "image/jpeg"}
        )

    provider = CoverArtArchiveProvider()
    provider.bind(_client(handler))
    cover = await provider.fetch_cover("rel-1")
    assert cover is not None
    assert cover.data == b"\xff\xd8\xff\xd9"
    assert cover.mime == "image/jpeg"


async def test_provider_without_client_raises() -> None:
    provider = MusicBrainzProvider()
    with pytest.raises(RuntimeError):
        await provider.search(ScrapeQuery(title="x"))


def test_scoring_prefers_similar_candidate() -> None:
    query = ScrapeQuery(title="Rolling in the Deep", artist="Adele", album="21")
    good = Candidate(
        provider="musicbrainz",
        external_id="a",
        title="Rolling in the Deep",
        artist="Adele",
        album="21",
        score=0.95,
    )
    bad = Candidate(
        provider="musicbrainz",
        external_id="b",
        title="Totally Different",
        artist="Nobody",
        score=0.2,
    )
    assert score_candidate(good, query) > score_candidate(bad, query)
    assert score_candidate(good, query) <= 1.0


def test_build_query_strips_filename_noise(track_factory) -> None:
    from app.services.scrape_orchestrator import ScrapeOrchestrator

    track = track_factory(filename="07 - 夜曲.flac", title=None, artist=None)
    query = ScrapeOrchestrator.build_query(track)
    assert query.filename_hint == "夜曲"


def test_musicbrainz_query_prefers_tags_then_falls_back_to_filename() -> None:
    # 有标签 → 字段限定查询
    tagged = MusicBrainzProvider._build_query(
        ScrapeQuery(title="Rolling in the Deep", artist="Adele")
    )
    assert tagged == 'recording:"Rolling in the Deep" AND artist:"Adele"'

    # 无标签 → 宽松通用检索（分隔符替换为空格）
    untagged = MusicBrainzProvider._build_query(ScrapeQuery(filename_hint="1965 - Zella Day"))
    assert untagged == "1965 Zella Day"
    assert '"' not in untagged


def test_split_filename_hint() -> None:
    from app.providers.builtin.lrclib import split_filename_hint

    assert split_filename_hint("1965 - Zella Day") == ("1965", "Zella Day")
    assert split_filename_hint("夜曲") == ("夜曲", None)
    assert split_filename_hint(None) == (None, None)


async def test_lrclib_uses_filename_hint_when_no_tags() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json={"syncedLyrics": "[00:01.00]hi"})

    provider = LRCLIBProvider()
    provider.bind(_client(handler))
    lyrics = await provider.fetch_lyrics(ScrapeQuery(filename_hint="1965 - Zella Day"))

    assert lyrics is not None
    assert seen["track_name"] == "1965"
    assert seen["artist_name"] == "Zella Day"
