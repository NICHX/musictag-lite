"""歌词：读取/写入（内嵌 /.lrc）（F6）。落盘在 M1。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import not_implemented
from app.models.schemas import LyricsRead, LyricsWriteRequest

router = APIRouter(tags=["lyrics"])


@router.get("/tracks/{track_id}/lyrics", response_model=LyricsRead)
def get_lyrics(track_id: int) -> LyricsRead:
    raise not_implemented("M1", "歌词读取（内嵌 → .lrc 边车）将在 M1 实现")


@router.put("/tracks/{track_id}/lyrics", response_model=LyricsRead)
def put_lyrics(track_id: int, payload: LyricsWriteRequest) -> LyricsRead:
    raise not_implemented("M1", "歌词写入（内嵌 / .lrc）将在 M1 实现")
