"""酷狗音乐（社区源，非官方接口，默认关闭）。

接口：
- 搜索：GET ``complexsearch.kugou.com/v2/search/song``（需 md5 签名）
- 歌词候选：GET ``krcs.kugou.com/search``（按音频 ``FileHash``）
- 歌词下载：GET ``lyrics.kugou.com/download`` —— ``fmt=lrc`` 为 base64 明文 LRC，
  ``fmt=krc`` 为逐字歌词（需解密，见 ``_krc.py``）

接口为第三方所有、非官方且可能随时变更；仅供个人本地元数据整理使用。
"""

from __future__ import annotations

import base64
import hashlib
import random
import time
from typing import Any

from app.providers.base import (
    AlbumBundle,
    Candidate,
    CoverBytes,
    HTTPProvider,
    Lyrics,
    ScrapeQuery,
)
from ._common import (
    BROWSER_UA,
    rank_score,
    search_keyword,
    to_int_seconds,
    upgrade_https,
)
from ._krc import KRCError, decrypt_krc, parse_krc

_SEARCH = "https://complexsearch.kugou.com/v2/search/song"
_KRC_SEARCH = "https://krcs.kugou.com/search"
_DOWNLOAD = "https://lyrics.kugou.com/download"
# 酷狗 Web/移动端签名固定盐值
_SALT = "NVPh5oo715z5DIWAeQlhMDsWXXQV4hwt"
_COVER_SIZE = "480"


def _md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def _sign(params: dict[str, str]) -> str:
    """按 ``md5(salt + "k=v&…" + salt)`` 生成签名（键名升序、不含 signature 本身）。"""
    joined = "".join(f"{key}={params[key]}" for key in sorted(params))
    return _md5(f"{_SALT}{joined}{_SALT}")


class KugouProvider(HTTPProvider):
    key = "kugou"
    name = "酷狗音乐"
    capabilities = {"metadata", "lyrics"}
    default_enabled = False  # 非官方接口，需显式启用
    default_priority = 63
    min_interval = 0.5
    extra_headers = {"Referer": "https://www.kugou.com/", "User-Agent": BROWSER_UA}

    async def search(self, q: ScrapeQuery) -> list[Candidate]:
        songs = await self._search_songs(search_keyword(q))
        return [
            self._to_candidate(song, index)
            for index, song in enumerate(songs)
            if song.get("FileHash")
        ]

    async def _search_songs(self, keyword: str) -> list[dict[str, Any]]:
        if not keyword:
            return []
        params = {
            "appid": "1014",
            "clientver": "2000",
            "keyword": keyword,
            "page": "1",
            "pagesize": "10",
            "platform": "WebFilter",
            "userid": "-1",
            "iscorrection": "1",
            "privilege_filter": "0",
            "filter": "10",
            "srcappid": "2919",
            "mid": _md5(str(random.random())),
            "dfid": "-",
            "clienttime": str(int(time.time() * 1000)),
            "uuid": _md5(str(random.random())),
            "token": "",
        }
        params["signature"] = _sign(params)
        data = await self._get_json(_SEARCH, params=params)
        lists = ((data or {}).get("data") or {}).get("lists") if isinstance(data, dict) else None
        return [song for song in (lists or []) if isinstance(song, dict)]

    @staticmethod
    def _to_candidate(song: dict[str, Any], index: int) -> Candidate:
        image = song.get("Image") or (song.get("trans_param") or {}).get("union_cover")
        cover = upgrade_https(str(image).replace("{size}", _COVER_SIZE)) if image else None
        duration = to_int_seconds(song.get("Duration"))  # 秒
        return Candidate(
            provider=KugouProvider.key,
            external_id=str(song.get("FileHash", "")),
            title=song.get("SongName"),
            artist=song.get("SingerName"),
            album=song.get("AlbumName"),
            year=None,
            duration=duration,
            score=rank_score(index),
            cover_url=cover,
            payload={"album_id": song.get("AlbumID"), "duration": song.get("Duration")},
        )

    async def fetch(self, external_id: str) -> AlbumBundle:
        return AlbumBundle()  # 无按 hash 的详情接口，字段以候选为准

    async def fetch_cover(self, external_id: str) -> CoverBytes | None:
        return None  # 封面随候选的 cover_url 提供

    async def fetch_lyrics(self, q: ScrapeQuery) -> Lyrics | None:
        candidate = await self._find_candidate(q)
        if candidate is None:
            return None
        data = await self._download(candidate["id"], candidate["accesskey"], "lrc")
        text = data.decode("utf-8", errors="replace").strip() if data else ""
        if not text:
            return None
        return Lyrics(content=text, format="lrc", source=self.key)

    async def fetch_word_lyrics(self, q: ScrapeQuery) -> list[dict[str, Any]]:
        """逐字歌词（只读预览用）：下载 KRC → 解密 → 解析为逐行逐字结构。"""
        candidate = await self._find_candidate(q)
        if candidate is None:
            return []
        data = await self._download(candidate["id"], candidate["accesskey"], "krc")
        if not data:
            return []
        try:
            return parse_krc(decrypt_krc(data))
        except KRCError:
            return []

    async def _find_candidate(self, q: ScrapeQuery) -> dict[str, Any] | None:
        songs = await self._search_songs(search_keyword(q))
        file_hash = songs[0].get("FileHash") if songs else None
        if not file_hash:
            return None
        data = await self._get_json(
            _KRC_SEARCH,
            params={
                "ver": 1,
                "man": "yes",
                "client": "mobi",
                "keyword": "",
                "duration": "",
                "album_audio_id": "",
                "hash": file_hash,
            },
        )
        candidates = (data or {}).get("candidates") if isinstance(data, dict) else None
        if not candidates:
            return None
        # 「官方推荐歌词」优先
        ordered = sorted(
            (c for c in candidates if isinstance(c, dict)),
            key=lambda c: 0 if str(c.get("product_from", "")).startswith("官方") else 1,
        )
        return ordered[0] if ordered else None

    async def _download(self, lyric_id: Any, accesskey: Any, fmt: str) -> bytes | None:
        if lyric_id is None or not accesskey:
            return None
        data = await self._get_json(
            _DOWNLOAD,
            params={
                "ver": 1,
                "client": "pc",
                "charset": "utf8",
                "fmt": fmt,
                "id": lyric_id,
                "accesskey": accesskey,
            },
        )
        content = data.get("content") if isinstance(data, dict) else None
        if not content:
            return None
        try:
            return base64.b64decode(content)
        except (ValueError, TypeError):
            return None

    async def identify(self, fingerprint: str, duration: int) -> list[Candidate]:
        return []
