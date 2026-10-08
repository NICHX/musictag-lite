"""歌词：读取/写入（内嵌 / .lrc）（F6）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.api.deps import ensure_track_path, get_track_or_404
from app.core.db import get_session
from app.models.schemas import LyricsRead, LyricsWriteRequest
from app.services.lyrics_service import LyricsService, validate_lrc

router = APIRouter(tags=["lyrics"])


@router.get("/tracks/{track_id}/lyrics", response_model=LyricsRead)
def get_lyrics(track_id: int, session: Session = Depends(get_session)) -> LyricsRead:
    """读取歌词：内嵌优先，其次同名 .lrc。"""
    track = get_track_or_404(session, track_id)
    ensure_track_path(session, track)
    content, source = LyricsService().read(track)
    return LyricsRead(
        track_id=track_id,
        available=content is not None,
        format="lrc" if source == "lrc" else "embedded",
        source=source,
        content=content,
    )


@router.put("/tracks/{track_id}/lyrics", response_model=LyricsRead)
def put_lyrics(
    track_id: int, payload: LyricsWriteRequest, session: Session = Depends(get_session)
) -> LyricsRead:
    """写入歌词：内嵌 / .lrc / 两者。"""
    track = get_track_or_404(session, track_id)
    ensure_track_path(session, track)

    if payload.format == "lrc" and payload.validate_lrc and not validate_lrc(payload.content):
        raise HTTPException(status_code=400, detail="歌词不是合法 LRC（缺少 [mm:ss] 时间轴）")

    LyricsService().write(session, track, payload.content, target=payload.target)
    return LyricsRead(
        track_id=track_id,
        available=True,
        format="lrc" if payload.format == "lrc" else "embedded",
        source=payload.target,
        content=payload.content,
    )
