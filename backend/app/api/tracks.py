"""曲目：列表（筛选/排序/分页/搜索）、详情、聚合 facets；单条编辑在 M1。"""

from __future__ import annotations

import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.api.deps import ensure_track_path, get_track_or_404, not_implemented
from app.audio.mutagen_io import UnsupportedFormatError
from app.core.db import get_session
from app.models.db import Track
from app.models.schemas import Page, TrackFacets, TrackRead, TrackUpdate
from app.services.tag_service import SOURCE_MANUAL, TagService

router = APIRouter(prefix="/tracks", tags=["tracks"])

_SORT_COLUMNS = {
    "filename": Track.filename,
    "path": Track.path,
    "size": Track.size,
    "mtime": Track.mtime,
    "duration": Track.duration,
    "track_no": Track.track_no,
    "title": Track.title,
    "artist": Track.artist,
    "album": Track.album,
}


@router.get("/facets", response_model=TrackFacets)
def track_facets(session: Session = Depends(get_session)) -> TrackFacets:
    """聚合计数：用于列表筛选面板。"""

    def group(column) -> dict[str, int]:  # noqa: ANN001
        rows = session.exec(select(column, func.count()).group_by(column)).all()
        return {str(key): int(count) for key, count in rows if key is not None}

    cover_rows = session.exec(select(Track.has_cover, func.count()).group_by(Track.has_cover)).all()
    lyrics_rows = session.exec(
        select(Track.has_lyrics, func.count()).group_by(Track.has_lyrics)
    ).all()
    return TrackFacets(
        formats=group(Track.format),
        years=group(Track.year),
        artists=group(Track.artist),
        tag_status=group(Track.tag_status),
        has_cover={str(k): int(v) for k, v in cover_rows},
        has_lyrics={str(k): int(v) for k, v in lyrics_rows},
    )


@router.get("", response_model=Page[TrackRead])
def list_tracks(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort: str = Query("filename"),
    order: str = Query("asc"),
    q: str | None = Query(default=None, description="标题/艺术家/专辑/文件名模糊匹配"),
    library_id: int | None = None,
    format: str | None = None,
    tag_status: str | None = None,
    has_cover: bool | None = None,
    has_lyrics: bool | None = None,
    session: Session = Depends(get_session),
) -> Page[TrackRead]:
    filters = []
    if q:
        like = f"%{q}%"
        filters.append(
            or_(
                Track.title.ilike(like),
                Track.artist.ilike(like),
                Track.album.ilike(like),
                Track.filename.ilike(like),
            )
        )
    if library_id is not None:
        filters.append(Track.library_id == library_id)
    if format:
        filters.append(Track.format == format)
    if tag_status:
        filters.append(Track.tag_status == tag_status)
    if has_cover is not None:
        filters.append(Track.has_cover == has_cover)
    if has_lyrics is not None:
        filters.append(Track.has_lyrics == has_lyrics)

    statement = select(Track)
    count_statement = select(func.count()).select_from(Track)
    for condition in filters:
        statement = statement.where(condition)
        count_statement = count_statement.where(condition)

    column = _SORT_COLUMNS.get(sort, Track.filename)
    statement = statement.order_by(column.desc() if order == "desc" else column.asc())
    statement = statement.offset((page - 1) * page_size).limit(page_size)

    items = session.exec(statement).all()
    total = int(session.exec(count_statement).one())
    pages = max(1, math.ceil(total / page_size)) if total else 1
    return Page[TrackRead](
        items=[TrackRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/{track_id}", response_model=TrackRead)
def get_track(track_id: int, session: Session = Depends(get_session)) -> TrackRead:
    track = session.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=404, detail="曲目不存在")
    return TrackRead.model_validate(track)


@router.patch("/{track_id}", response_model=TrackRead)
def update_track(
    track_id: int, payload: TrackUpdate, session: Session = Depends(get_session)
) -> TrackRead:
    """单条编辑：写入标签落盘并记录日志。"""
    track = get_track_or_404(session, track_id)
    ensure_track_path(session, track)

    values = payload.model_dump(exclude_unset=True)
    try:
        TagService().apply_single(session, track, values, source=SOURCE_MANUAL)
    except UnsupportedFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"写入失败：{exc}") from exc
    return TrackRead.model_validate(track)


@router.get("/{track_id}/stream")
def stream_track(track_id: int):
    raise not_implemented("M2", "音频流式试听将在 M2（P1）实现")
