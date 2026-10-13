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


def _mb_rec(
    rec_id: str,
    title: str,
    artist: str,
    album: str | None = None,
    year: str | None = None,
    score: int = 100,
) -> dict:
    item: dict = {
        "id": rec_id,
        "title": title,
        "score": score,
        "artist-credit": [{"name": artist}],
    }
    if album or year:
        item["releases"] = [{"id": f"rel-{rec_id}", "title": album, "date": year}]
    return item


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


def test_scoring_demotes_cover_version() -> None:
    """同名不同歌手的翻唱，即使平台名次更高，也应低于原唱。"""
    query = ScrapeQuery(title="夜曲", artist="周杰伦", duration=227)
    original = Candidate(
        provider="netease",
        external_id="1",
        title="夜曲",
        artist="周杰伦",
        album="十一月的萧邦",
        duration=227,
        score=0.9,
    )
    cover = Candidate(
        provider="netease",
        external_id="2",
        title="夜曲",
        artist="某翻唱歌手",
        album="翻唱合集",
        duration=240,
        score=1.0,  # 平台第 1 名也不能压过原唱
    )
    assert score_candidate(original, query) > score_candidate(cover, query)


def test_scoring_demotes_version_markers() -> None:
    """标题带 Live/翻唱/伴奏 等版本标记时应降级（用户未主动检索该版本时）。"""
    query = ScrapeQuery(title="告白气球", artist="周杰伦")
    studio = Candidate(
        provider="qqmusic", external_id="a", title="告白气球", artist="周杰伦", score=0.8
    )
    live = Candidate(
        provider="qqmusic", external_id="b", title="告白气球 (Live)", artist="周杰伦", score=1.0
    )
    assert score_candidate(studio, query) > score_candidate(live, query)


def test_scoring_penalizes_duration_mismatch() -> None:
    query = ScrapeQuery(title="X", artist="A", duration=200)
    same = Candidate(provider="p", external_id="1", title="X", artist="A", duration=200, score=0.8)
    diff = Candidate(provider="p", external_id="2", title="X", artist="A", duration=120, score=0.8)
    assert score_candidate(same, query) > score_candidate(diff, query)


def test_build_query_strips_filename_noise(track_factory) -> None:
    from app.services.scrape_orchestrator import ScrapeOrchestrator

    track = track_factory(filename="07 - 夜曲.flac", title=None, artist=None)
    query = ScrapeOrchestrator.build_query(track)
    assert query.filename_hint == "夜曲"


def test_musicbrainz_build_queries() -> None:
    # 有标签 → 单条字段限定查询
    tagged = MusicBrainzProvider._build_queries(
        ScrapeQuery(title="Rolling in the Deep", artist="Adele")
    )
    assert tagged == ['recording:"Rolling in the Deep" AND artist:"Adele"']

    # 无标签 + 「A - B」 → 两种顺序各一条（兼容 Title-Artist 与 Artist-Title）
    untagged = MusicBrainzProvider._build_queries(ScrapeQuery(filename_hint="1965 - Zella Day"))
    assert untagged == [
        'recording:"1965" AND artist:"Zella Day"',
        'recording:"Zella Day" AND artist:"1965"',
    ]

    # 无分隔符 → 宽松检索兜底
    assert MusicBrainzProvider._build_queries(ScrapeQuery(filename_hint="夜曲")) == ["夜曲"]


async def test_musicbrainz_search_stops_after_first_hit() -> None:
    """第一种解释命中后不再发第二次查询（省一次请求）。"""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.params.get("query", ""))
        return httpx.Response(
            200,
            json={
                "recordings": [
                    _mb_rec("r1", "1965", "Zella Day", album="Kicker", year="2015-06-01"),
                    _mb_rec("r1", "1965", "Zella Day"),  # 重复 id，验证去重
                ]
            },
        )

    provider = MusicBrainzProvider()
    provider.bind(_client(handler))
    results = await provider.search(ScrapeQuery(filename_hint="1965 - Zella Day"))

    assert len(calls) == 1
    assert [item.external_id for item in results] == ["r1"]


async def test_musicbrainz_tries_second_order_when_first_empty() -> None:
    """文件名是「艺术家 - 标题」时，第一种解释为空，应再试第二种。"""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params.get("query", "")
        calls.append(query)
        if 'recording:"Levitating"' in query:  # 第二种解释（把 Levitating 当标题）
            return httpx.Response(
                200, json={"recordings": [_mb_rec("r9", "Levitating", "Dua Lipa")]}
            )
        return httpx.Response(200, json={"recordings": []})

    provider = MusicBrainzProvider()
    provider.bind(_client(handler))
    results = await provider.search(ScrapeQuery(filename_hint="Dua Lipa - Levitating"))

    assert [item.title for item in results] == ["Levitating"]
    assert len(calls) == 2


async def test_musicbrainz_falls_back_to_filename_when_tags_yield_nothing() -> None:
    """标签里的艺术家拼写有误时，应回退到文件名解析再查。"""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params.get("query", "")
        calls.append(query)
        if 'artist:"Zella Day"' in query:
            return httpx.Response(200, json={"recordings": [_mb_rec("r1", "1965", "Zella Day")]})
        return httpx.Response(200, json={"recordings": []})

    provider = MusicBrainzProvider()
    provider.bind(_client(handler))
    # 用户把艺术家填成了 Zelly Day（拼写错误），文件名才是对的
    query = ScrapeQuery(title="1965", artist="Zelly Day", filename_hint="1965 - Zella Day")
    results = await provider.search(query)

    assert [item.title for item in results] == ["1965"]
    assert len(calls) == 2  # 先按标签查（无果），再按文件名兜底
    assert calls[0] == 'recording:"1965" AND artist:"Zelly Day"'
    assert calls[1] == 'recording:"1965" AND artist:"Zella Day"'


async def test_musicbrainz_search_survives_one_failed_query() -> None:
    """单条查询失败（如 MB 限流 503）不应丢弃其他查询的结果。"""

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params.get("query", "")
        if 'recording:"1965"' in query:
            return httpx.Response(200, json={"recordings": [_mb_rec("r1", "1965", "Zella Day")]})
        return httpx.Response(503, text="rate limited")

    provider = MusicBrainzProvider()
    provider.max_retries = 1  # 测试中不等待退避
    provider.bind(_client(handler))
    results = await provider.search(ScrapeQuery(filename_hint="1965 - Zella Day"))

    assert [item.external_id for item in results] == ["r1"]


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
