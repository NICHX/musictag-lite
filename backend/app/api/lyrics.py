"""歌词：读取/写入（内嵌 / 同名 ``.lrc`` / ``.nilyric``）（F6）。

最终产物只有一份文本 —— **逐字 LRC**（数据源或 AI 提供译文时，即为「逐字 + 译文」），
可写入「内嵌」与/或一个同名边车（``.nilyric`` 或 ``.lrc``）。
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.api.deps import ensure_track_path, get_track_or_404
from app.core.db import get_session
from app.models.schemas import LyricsRead, LyricsWriteRequest, WordLyricsWriteRequest
from app.services.lyrics_service import LyricsService, validate_lrc
from app.services.lyrics_translate import LyricsTranslateError
from app.services.scrape_orchestrator import scrape_orchestrator

router = APIRouter(tags=["lyrics"])

_DEFAULT_TARGETS = ["embedded", "nilyric"]


@router.get("/tracks/{track_id}/lyrics", response_model=LyricsRead)
def get_lyrics(track_id: int, session: Session = Depends(get_session)) -> LyricsRead:
    """读取歌词：内嵌优先，其次同名 ``.lrc`` / ``.nilyric``。"""
    track = get_track_or_404(session, track_id)
    ensure_track_path(session, track)
    content, source = LyricsService().read(track)
    return LyricsRead(
        track_id=track_id,
        available=content is not None,
        format="lrc" if source in {"lrc", "word"} else "embedded",
        source=source,
        content=content,
    )


@router.put("/tracks/{track_id}/lyrics", response_model=LyricsRead)
def put_lyrics(
    track_id: int, payload: LyricsWriteRequest, session: Session = Depends(get_session)
) -> LyricsRead:
    """写入歌词文本：内嵌 / .lrc / 两者。"""
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


@router.post("/tracks/{track_id}/lyrics/word", response_model=LyricsRead)
async def save_word_lyrics(
    track_id: int,
    payload: WordLyricsWriteRequest | None = None,
    session: Session = Depends(get_session),
) -> LyricsRead:
    """抓取逐字歌词并写入所选目标（内嵌 / ``.nilyric`` / ``.lrc``）。

    译文来源由 ``translation`` 决定（默认 ``source``，**不会**自动调用 AI）：

    - ``none``：不写译文；
    - ``source``：仅用**数据源自带**译文（网易云 / QQ，免费）；
    - ``ai``：显式调用 AI 生成译文（可能产生费用，需自行选择）。
    """
    targets = list(payload.targets) if payload is not None else list(_DEFAULT_TARGETS)
    translation_mode = payload.translation if payload is not None else "source"
    translate_target = payload.translate_target if payload is not None else "zh"
    if not targets:
        raise HTTPException(status_code=400, detail="请至少选择一个写入目标（内嵌 / .nilyric / .lrc）")

    track = get_track_or_404(session, track_id)
    ensure_track_path(session, track)

    # 与批量共用同一实现（scrape_orchestrator.word_lyrics_final），确保写入内容一致
    try:
        merged = await scrape_orchestrator.word_lyrics_final(
            session, track, translation=translation_mode, translate_target=translate_target
        )
    except LyricsTranslateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"译文获取失败：{exc}") from exc
    if merged is None:
        raise HTTPException(
            status_code=404,
            detail="未找到逐字歌词（需在「设置 → 刮削源」启用支持逐字的源：酷狗 / QQ / 网易云）",
        )

    LyricsService().write_final(session, track, merged, targets=targets)
    return LyricsRead(
        track_id=track_id,
        available=True,
        format="lrc",
        source="+".join(targets),
        content=merged,
    )
