"""歌词：读取/写入（内嵌 / .lrc）（F6）+ AI 双语翻译。"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.api.deps import ensure_track_path, get_track_or_404
from app.core.db import get_session
from app.models.schemas import (
    LyricsRead,
    LyricsTranslateRequest,
    LyricsTranslateResponse,
    LyricsWriteRequest,
)
from app.services import ai_config
from app.services.lyrics_service import LyricsService, validate_lrc
from app.services.lyrics_translate import LyricsTranslateError, translate_lyrics
from app.services.scrape_orchestrator import scrape_orchestrator

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


@router.post("/tracks/{track_id}/lyrics/translate", response_model=LyricsTranslateResponse)
async def translate_lyrics_endpoint(
    track_id: int,
    payload: LyricsTranslateRequest,
    session: Session = Depends(get_session),
) -> LyricsTranslateResponse:
    """AI 歌词翻译：返回「原文 + 译文」双语对照 LRC（不落盘，由前端确认后再写入）。"""
    track = get_track_or_404(session, track_id)
    ensure_track_path(session, track)

    content = payload.content
    if content is None:
        content, _source = LyricsService().read(track)
    if not content:
        raise HTTPException(status_code=400, detail="没有可翻译的歌词（请先获取或填写歌词）")

    try:
        result = await translate_lyrics(
            content, target=payload.target, config=ai_config.resolve(session)
        )
    except LyricsTranslateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"翻译失败：{exc}") from exc
    return LyricsTranslateResponse(track_id=track_id, target=payload.target, content=result)


@router.post("/tracks/{track_id}/lyrics/word", response_model=LyricsRead)
async def save_word_lyrics(
    track_id: int, session: Session = Depends(get_session)
) -> LyricsRead:
    """逐字歌词 → 双文件边车：``.lrc``（标准逐行）+ ``.nilyric``（逐字标记格式）。

    ``.lrc`` 兼容所有播放器；``.nilyric`` 含 ``[行时间][[字时间]]字`` 字级时间轴，
    需支持逐字标记的播放器。需要已启用支持逐字的源（酷狗 / QQ / 网易云）。
    """
    track = get_track_or_404(session, track_id)
    ensure_track_path(session, track)
    _source, plain, word = await scrape_orchestrator.word_lyrics_bundle(session, track)
    if not word:
        raise HTTPException(
            status_code=404,
            detail="未找到逐字歌词（需在「设置 → 刮削源」启用支持逐字的源：酷狗 / QQ / 网易云）",
        )
    LyricsService().write_word_sidecars(session, track, plain=plain, word=word)
    return LyricsRead(
        track_id=track_id, available=True, format="lrc", source="lrc", content=plain
    )
