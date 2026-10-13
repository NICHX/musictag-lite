"""QQ 音乐（社区源，非官方接口，默认关闭）。

接口：
- 检索：GET ``c.y.qq.com/soso/fcgi-bin/client_search_cp``（需 Referer: y.qq.com）
- 歌词：GET ``c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg``（``nobase64=1`` 取明文）
- 封面：``y.gtimg.cn/music/photo_new/T002R300x300M000{album_mid}.jpg``

接口由第三方所有、非官方且可能随时变更；仅供个人本地元数据整理使用。
"""

from __future__ import annotations

import html
from typing import Any

from app.providers.base import (
    AlbumBundle,
    Candidate,
    CoverBytes,
    HTTPProvider,
    Lyrics,
    ScrapeQuery,
)
from app.providers.community._common import BROWSER_UA, rank_score, search_keyword
from app.providers.community._crypto import decrypt_qrc
from app.providers.community._lyrics import merge_lrc
from app.providers.community._qrc import extract_qrc, parse_qrc

_SEARCH = "https://c.y.qq.com/soso/fcgi-bin/client_search_cp"
_LYRIC = "https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg"
_QRC_API = "https://u.y.qq.com/cgi-bin/musicu.fcg"
_COVER = "https://y.gtimg.cn/music/photo_new/T002R300x300M000{album_mid}.jpg"


class QQMusicProvider(HTTPProvider):
    key = "qqmusic"
    name = "QQ 音乐"
    capabilities = {"metadata", "lyrics"}
    default_enabled = False  # 非官方接口，需显式启用
    default_priority = 62
    min_interval = 0.5
    extra_headers = {"Referer": "https://y.qq.com/", "User-Agent": BROWSER_UA}

    async def search(self, q: ScrapeQuery) -> list[Candidate]:
        songs = await self._search_songs(search_keyword(q))
        return [
            self._to_candidate(song, index)
            for index, song in enumerate(songs)
            if song.get("mid") or song.get("songmid")
        ]

    async def _search_songs(self, keyword: str) -> list[dict[str, Any]]:
        if not keyword:
            return []
        # new_json=1 才带 time_public（发行日期）等完整字段
        data = await self._get_json(
            _SEARCH,
            params={
                "w": keyword,
                "format": "json",
                "p": 1,
                "n": 10,
                "cr": 1,
                "g_tk": 5381,
                "new_json": 1,
                "inCharset": "utf8",
                "outCharset": "utf-8",
            },
        )
        if not isinstance(data, dict):
            return []
        song = ((data.get("data") or {}).get("song") or {})
        songs = song.get("list") or []
        return [item for item in songs if isinstance(item, dict)]

    @staticmethod
    def _to_candidate(song: dict[str, Any], index: int) -> Candidate:
        album = song.get("album") or {}
        album_mid = album.get("mid") or song.get("albummid")
        album_name = album.get("name") or album.get("title") or song.get("albumname")
        singers = song.get("singer") or []
        artist = ", ".join(s.get("name", "") for s in singers if s.get("name")) or None
        published = str(song.get("time_public") or "")
        year = published[:4] if len(published) >= 4 else None
        return Candidate(
            provider=QQMusicProvider.key,
            external_id=str(song.get("mid") or song.get("songmid") or ""),
            title=song.get("name") or song.get("songname") or song.get("title"),
            artist=artist,
            album=album_name,
            year=year,
            score=rank_score(index),
            cover_url=_COVER.format(album_mid=album_mid) if album_mid else None,
            payload={"album_mid": album_mid, "interval": song.get("interval")},
        )

    async def fetch(self, external_id: str) -> AlbumBundle:
        return AlbumBundle()  # 无按 songmid 的详情接口，字段以候选为准

    async def fetch_cover(self, external_id: str) -> CoverBytes | None:
        return None  # 封面随候选的 cover_url 提供

    async def fetch_lyrics(self, q: ScrapeQuery) -> Lyrics | None:
        songs = await self._search_songs(search_keyword(q))
        if not songs:
            return None
        mid = songs[0].get("mid") or songs[0].get("songmid")
        if not mid:
            return None
        data = await self._get_json(
            _LYRIC, params={"songmid": mid, "format": "json", "nobase64": 1, "g_tk": 5381}
        )
        if not isinstance(data, dict):
            return None
        main = data.get("lyric")
        if not main:
            return None
        trans = data.get("trans")
        content = merge_lrc(
            html.unescape(str(main)), html.unescape(str(trans)) if trans else None
        )
        return Lyrics(content=content, format="lrc", source=self.key)

    async def identify(self, fingerprint: str, duration: int) -> list[Candidate]:
        return []

    async def fetch_word_lyrics(self, q: ScrapeQuery) -> list[dict[str, Any]]:
        """逐字歌词（QRC）：musicu 取加密 hex → 私有 3DES 解密 → 解析。"""
        songs = await self._search_songs(search_keyword(q))
        if not songs:
            return []
        mid = songs[0].get("mid") or songs[0].get("songmid")
        if not mid:
            return []
        data = await self._post_payload(
            _QRC_API,
            {
                "comm": {
                    "ct": "11",
                    "cv": "1003006",
                    "v": "1003006",
                    "os_ver": "15",
                    "tmeAppID": "qqmusiclight",
                    "nettype": "1",
                    "uid": "0",
                },
                "req": {
                    "module": "music.musichallSong.PlayLyricInfo",
                    "method": "GetPlayLyricInfo",
                    "param": {
                        "songMID": mid,
                        "songID": 0,
                        "albumID": 0,
                        "crypt": 0,
                        "lrc_txt": 0,
                        "qrc": 1,
                        "qrc_txt": 1,
                        "format": "json",
                    },
                },
            },
        )
        encrypted = ((data or {}).get("req") or {}).get("data", {}).get("lyric")
        if not encrypted:
            return []
        return parse_qrc(extract_qrc(decrypt_qrc(str(encrypted))))
