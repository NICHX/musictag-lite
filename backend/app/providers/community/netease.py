"""网易云音乐（社区源，非官方接口，默认关闭）。

接口：
- 检索：POST ``/api/cloudsearch/pc`` —— 返回 ``result.songs[].al.picUrl``（含封面）
- 歌词：GET  ``/api/song/lyric``

注意：**不要**改用 ``/api/search/get/web``：该接口的 ``album`` 只有 ``picId`` 而没有
``picUrl``，会导致封面取不到（picId 需专有算法才能转成图片地址）。接口为第三方所有、
非官方且可能随时变更，仅供个人本地元数据整理使用。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.providers.base import (
    AlbumBundle,
    Candidate,
    CoverBytes,
    HTTPProvider,
    Lyrics,
    ScrapeQuery,
)
from app.providers.community._common import (
    BROWSER_UA,
    join_names,
    rank_score,
    search_keyword,
    upgrade_https,
)
from app.providers.community._lyrics import merge_lrc

_SEARCH = "https://music.163.com/api/cloudsearch/pc"
_LYRIC = "https://music.163.com/api/song/lyric"


def _section(data: dict[str, Any], key: str) -> str | None:
    """取歌词接口里某个分段（lrc/tlyric/romalrc/klyric）的正文。"""
    value = (data.get(key) or {}).get("lyric")
    return str(value) if value else None


def _year_from_ms(value: Any) -> str | None:
    """``publishTime`` 为毫秒时间戳，转成 "YYYY"；非法值返回 None。"""
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    return str(datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).year)


class NeteaseProvider(HTTPProvider):
    key = "netease"
    name = "网易云音乐"
    capabilities = {"metadata", "lyrics"}
    default_enabled = False  # 非官方接口，需显式启用
    default_priority = 60
    min_interval = 0.5
    extra_headers = {"Referer": "https://music.163.com/", "User-Agent": BROWSER_UA}

    async def search(self, q: ScrapeQuery) -> list[Candidate]:
        songs = await self._search_songs(search_keyword(q))
        return [
            self._to_candidate(song, index)
            for index, song in enumerate(songs)
            if song.get("id")
        ]

    async def _search_songs(self, keyword: str) -> list[dict[str, Any]]:
        if not keyword:
            return []
        data = await self._post_json(
            _SEARCH, data={"s": keyword, "type": 1, "limit": 10, "offset": 0}
        )
        if not isinstance(data, dict):
            return []
        songs = ((data.get("result") or {}).get("songs")) or []
        return [song for song in songs if isinstance(song, dict)]

    @staticmethod
    def _to_candidate(song: dict[str, Any], index: int) -> Candidate:
        album = song.get("al") or song.get("album") or {}
        artists = song.get("ar") or song.get("artists") or []
        return Candidate(
            provider=NeteaseProvider.key,
            external_id=str(song.get("id", "")),
            title=song.get("name"),
            artist=join_names(artists),
            album=album.get("name"),
            year=_year_from_ms(song.get("publishTime")),
            score=rank_score(index),
            cover_url=upgrade_https(album.get("picUrl")),
            payload={"album_id": album.get("id")},
        )

    async def fetch(self, external_id: str) -> AlbumBundle:
        return AlbumBundle()  # 无按 id 的详情接口可复用，字段以候选为准

    async def fetch_cover(self, external_id: str) -> CoverBytes | None:
        return None  # 封面随候选的 cover_url 提供，由编排层直接下载

    async def fetch_lyrics(self, q: ScrapeQuery) -> Lyrics | None:
        songs = await self._search_songs(search_keyword(q))
        if not songs:
            return None
        song_id = songs[0].get("id")
        if not song_id:
            return None
        # lv/kv/tv/rv = -1：一次请求同时取回 原文 / 逐字 / 译文 / 罗马音
        data = await self._get_json(
            _LYRIC, params={"id": song_id, "lv": -1, "kv": -1, "tv": -1, "rv": -1}
        )
        if not isinstance(data, dict):
            return None
        main = _section(data, "lrc")
        if not main:
            return None
        content = merge_lrc(main, _section(data, "tlyric"), _section(data, "romalrc"))
        return Lyrics(content=content, format="lrc", source=self.key)

    async def identify(self, fingerprint: str, duration: int) -> list[Candidate]:
        return []
