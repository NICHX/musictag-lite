"""曲目：列表（筛选/排序/分页/搜索）、详情、聚合 facets；单条编辑在 M1。"""

from __future__ import annotations

import math

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.api.deps import ensure_track_path, get_track_or_404, not_implemented
from app.audio.mutagen_io import UnsupportedFormatError
from app.core.db import get_session
from app.models.db import Track
from app.models.schemas import (
    FieldDiff,
    Page,
    ParsedFields,
    ParseFilenameRequest,
    ParseFilenameResponse,
    TrackFacets,
    TrackRead,
    TrackUpdate,
)
from app.services import ai_config
from app.services.ai_parser import AIUnavailableError, parse_filename_with_ai
from app.services.filename_parser import parse_filename
from app.services.scrape_orchestrator import scrape_orchestrator
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


@router.post("/{track_id}/parse-filename", response_model=ParseFilenameResponse)
async def parse_track_filename(
    track_id: int,
    payload: ParseFilenameRequest,
    session: Session = Depends(get_session),
) -> ParseFilenameResponse:
    """按文件名解析标签；可选 AI 辅助；``apply=false`` 时仅预览不写盘。"""
    track = get_track_or_404(session, track_id)
    ensure_track_path(session, track)

    known = scrape_orchestrator.known_artists(session)
    parsed = parse_filename(track.filename, known)
    source: str = "heuristic"
    note = parsed.note

    if payload.use_ai:
        try:
            parsed = await parse_filename_with_ai(track.filename, config=ai_config.resolve(session))
            source, note = "ai", parsed.note
        except AIUnavailableError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (httpx.HTTPError, OSError, ValueError) as exc:
            # AI 不可用时回退到本地启发式，并在 note 中说明原因
            parsed = parse_filename(track.filename, known)
            note = f"AI 解析失败，已回退到本地解析：{exc}"

    fields = ParsedFields(
        title=parsed.title,
        artist=parsed.artist,
        album=parsed.album,
        track_no=parsed.track_no,
    )
    diffs = [
        FieldDiff(field=name, old_value=getattr(track, name), new_value=new_value)
        for name in ("title", "artist", "album", "track_no")
        if (new_value := getattr(fields, name)) is not None and getattr(track, name) != new_value
    ]

    applied = False
    if payload.apply and diffs:
        values = {diff.field: diff.new_value for diff in diffs}
        try:
            TagService().apply_single(session, track, values, source=SOURCE_MANUAL)
        except UnsupportedFormatError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"写入失败：{exc}") from exc
        applied = True

    return ParseFilenameResponse(
        track_id=track_id,
        source="ai" if source == "ai" else "heuristic",
        confidence=parsed.confidence,
        note=note,
        fields=fields,
        diffs=diffs,
        applied=applied,
    )
