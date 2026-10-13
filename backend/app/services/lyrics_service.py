"""歌词服务：内嵌歌词 + .lrc 边车读取/写入，LRC 时间轴校验（F6）。"""

from __future__ import annotations

import re
from pathlib import Path

from sqlmodel import Session

from app.audio.base import AudioIO
from app.audio.mutagen_io import audio_io
from app.models.db import Track, utcnow
from app.services import oplog

# 形如 [mm:ss.xx] 或 [mm:ss]
_LRC_TIME_RE = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")


def validate_lrc(content: str) -> bool:
    """校验歌词是否为合法 LRC：至少含一行时间轴。"""
    if not content or not content.strip():
        return False
    return any(_LRC_TIME_RE.search(line) for line in content.splitlines())


def is_lrc(content: str) -> bool:
    return validate_lrc(content)


def lrc_path_for(track: Track) -> Path:
    return Path(track.path).with_suffix(".lrc")


def nilyric_path_for(track: Track) -> Path:
    """逐字歌词边车文件（`.nilyric`，需支持逐字标记的播放器）。"""
    return Path(track.path).with_suffix(".nilyric")


class LyricsService:
    """歌词读取与写入。"""

    def __init__(self, audio: AudioIO | None = None) -> None:
        self.audio = audio or audio_io

    def read(self, track: Track) -> tuple[str | None, str | None]:
        """返回 (歌词, 来源)：优先内嵌，其次同名 .lrc。"""
        try:
            embedded = self.audio.read_lyrics(Path(track.path))
        except Exception:  # noqa: BLE001
            embedded = None
        if embedded:
            return embedded, "embedded"

        sidecar = lrc_path_for(track)
        if sidecar.is_file():
            return sidecar.read_text(encoding="utf-8", errors="replace"), "lrc"
        return None, None

    def write(
        self,
        session: Session,
        track: Track,
        content: str,
        *,
        target: str = "embedded",
        source: str = "manual",
    ) -> None:
        """写入歌词；target ∈ {embedded, lrc, both}。"""
        if target in {"embedded", "both"}:
            self.audio.write_lyrics(Path(track.path), content)
            track.has_embedded_lyrics = True
        if target in {"lrc", "both"}:
            lrc_path_for(track).write_text(content, encoding="utf-8")
            track.has_lyrics_file = True

        track.has_lyrics = True
        track.updated_at = utcnow()
        session.add(track)
        oplog.record(
            session,
            track_id=track.id,
            action="lyrics.write",
            field="lyrics",
            new=f"{target} ({len(content)} 字)",
            source=source,
        )
        session.commit()
        session.refresh(track)

    def write_word_sidecars(
        self,
        session: Session,
        track: Track,
        *,
        plain: str,
        word: str,
        source: str = "scrape",
    ) -> None:
        """双文件边车：``.lrc`` 写标准逐行，``.nilyric`` 写逐字（含字级时间轴）。"""
        lrc_path_for(track).write_text(plain, encoding="utf-8")
        nilyric_path_for(track).write_text(word, encoding="utf-8")
        track.has_lyrics = True
        track.has_lyrics_file = True
        track.has_word_lyrics = True
        track.updated_at = utcnow()
        session.add(track)
        oplog.record(
            session,
            track_id=track.id,
            action="lyrics.write",
            field="lyrics",
            new=f"lrc+nilyric ({len(plain)}/{len(word)} 字)",
            source=source,
        )
        session.commit()
        session.refresh(track)
