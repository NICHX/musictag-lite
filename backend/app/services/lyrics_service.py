"""歌词服务：内嵌歌词 + 同名边车（``.lrc`` / ``.nilyric``）读写。

最终产物只有一份文本（逐字 LRC，含译文行时即为「逐字 + 译文」），可写入：

- **内嵌**（音频标签容器）；
- **同名边车** ``.nilyric``（逐字，含字级时间轴）或 ``.lrc``（通用）。

内嵌与边车互不干扰，写入目标由调用方选择。
"""

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
    """同名 ``.lrc`` 边车路径。"""
    return Path(track.path).with_suffix(".lrc")


def nilyric_path_for(track: Track) -> Path:
    """同名 ``.nilyric`` 边车路径（逐字歌词）。"""
    return Path(track.path).with_suffix(".nilyric")


class LyricsService:
    """歌词读取与写入。"""

    def __init__(self, audio: AudioIO | None = None) -> None:
        self.audio = audio or audio_io

    def read(self, track: Track) -> tuple[str | None, str | None]:
        """返回 (歌词, 来源)：优先内嵌，其次同名 ``.lrc``、``.nilyric``。"""
        try:
            embedded = self.audio.read_lyrics(Path(track.path))
        except Exception:  # noqa: BLE001
            embedded = None
        if embedded:
            return embedded, "embedded"

        for path, source in ((lrc_path_for(track), "lrc"), (nilyric_path_for(track), "word")):
            if path.is_file():
                content = path.read_text(encoding="utf-8", errors="replace")
                if content.strip():
                    return content, source
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
        """写入通用歌词文本；target ∈ {embedded, lrc, both}。"""
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

    def write_final(
        self,
        session: Session,
        track: Track,
        content: str,
        *,
        targets: list[str],
        source: str = "scrape",
    ) -> None:
        """写入最终歌词（逐字 LRC，含译文行时即「逐字 + 译文」）到所选目标。

        ``targets`` ⊆ {``embedded``, ``nilyric``, ``lrc``}。
        """
        if "embedded" in targets:
            self.audio.write_lyrics(Path(track.path), content)
            track.has_embedded_lyrics = True
        if "nilyric" in targets:
            nilyric_path_for(track).write_text(content, encoding="utf-8")
            track.has_word_lyrics = True
        if "lrc" in targets:
            lrc_path_for(track).write_text(content, encoding="utf-8")
            track.has_lyrics_file = True

        track.has_lyrics = True
        track.has_word_lyrics = True
        track.updated_at = utcnow()
        session.add(track)
        oplog.record(
            session,
            track_id=track.id,
            action="lyrics.write",
            field="lyrics",
            new=f"{'+'.join(targets) or 'none'} ({len(content)} 字)",
            source=source,
        )
        session.commit()
        session.refresh(track)
