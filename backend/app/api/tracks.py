"""曲目：列表（筛选/排序/分页/搜索）、详情、聚合 facets；单条编辑在 M1。"""

from __future__ import annotations

import math
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.api.deps import ensure_track_path, get_track_or_404
from app.audio.mutagen_io import UnsupportedFormatError
from app.core.db import get_session, session_scope
from app.core.tasks import task_manager
from app.models.db import Track
from app.models.schemas import (
    FieldDiff,
    Page,
    ParsedFields,
    ParseFilenameBatchRequest,
    ParseFilenameBatchResponse,
    ParseFilenameRequest,
    ParseFilenameResponse,
    TaskAccepted,
    TrackFacets,
    TrackIds,
    TrackRead,
    TrackUpdate,
)
from app.services import ai_config
from app.services.ai_config import AIConfig
from app.services.ai_parser import AIUnavailableError, parse_filename_with_ai
from app.services.filename_parser import parse_filename
from app.services.filename_service import FilenameParseService
from app.services.scrape_orchestrator import scrape_orchestrator
from app.services.stream_service import build_stream_response
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
    word_rows = session.exec(
        select(Track.has_word_lyrics, func.count()).group_by(Track.has_word_lyrics)
    ).all()
    return TrackFacets(
        formats=group(Track.format),
        years=group(Track.year),
        artists=group(Track.artist),
        tag_status=group(Track.tag_status),
        has_cover={str(k): int(v) for k, v in cover_rows},
        has_lyrics={str(k): int(v) for k, v in lyrics_rows},
        has_word_lyrics={str(k): int(v) for k, v in word_rows},
    )


@router.get("/ids", response_model=TrackIds)
def list_track_ids(
    q: str | None = Query(default=None, description="标题/艺术家/专辑/文件名模糊匹配"),
    library_id: int | None = None,
    format: str | None = None,
    tag_status: str | None = None,
    has_cover: bool | None = None,
    has_lyrics: bool | None = None,
    has_word_lyrics: bool | None = None,
    session: Session = Depends(get_session),
) -> TrackIds:
    """返回当前筛选命中的全部曲目 id（不分页），用于跨页「选择全部」批量操作。"""
    statement = select(Track.id)
    for condition in _track_filters(
        q=q,
        library_id=library_id,
        format=format,
        tag_status=tag_status,
        has_cover=has_cover,
        has_lyrics=has_lyrics,
        has_word_lyrics=has_word_lyrics,
    ):
        statement = statement.where(condition)
    ids = [int(row) for row in session.exec(statement).all()]
    return TrackIds(ids=ids, total=len(ids))


def _track_filters(
    *,
    q: str | None,
    library_id: int | None,
    format: str | None,
    tag_status: str | None,
    has_cover: bool | None,
    has_lyrics: bool | None,
    has_word_lyrics: bool | None,
) -> list:
    """列表与 id 查询共用的筛选条件。"""
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
    if has_word_lyrics is not None:
        filters.append(Track.has_word_lyrics == has_word_lyrics)
    return filters


@router.get("", response_model=Page[TrackRead])
def list_tracks(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
    sort: str = Query("filename"),
    order: str = Query("asc"),
    q: str | None = Query(default=None, description="标题/艺术家/专辑/文件名模糊匹配"),
    library_id: int | None = None,
    format: str | None = None,
    tag_status: str | None = None,
    has_cover: bool | None = None,
    has_lyrics: bool | None = None,
    has_word_lyrics: bool | None = None,
    session: Session = Depends(get_session),
) -> Page[TrackRead]:
    filters = _track_filters(
        q=q,
        library_id=library_id,
        format=format,
        tag_status=tag_status,
        has_cover=has_cover,
        has_lyrics=has_lyrics,
        has_word_lyrics=has_word_lyrics,
    )

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
def stream_track(
    track_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> StreamingResponse:
    """音频试听（支持 HTTP Range，浏览器可拖动定位）。"""
    track = get_track_or_404(session, track_id)
    ensure_track_path(session, track)
    path = Path(track.path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="音频文件不存在")
    return build_stream_response(request, path)


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


def _resolve_ai_or_400(session: Session, use_ai: bool) -> AIConfig | None:
    """``use_ai`` 时先校验 AI 可用性，避免批量任务启动后才失败。"""
    if not use_ai:
        return None
    config = ai_config.resolve(session)
    if not config.available:
        raise HTTPException(status_code=400, detail="AI 辅助不可用：请在设置中启用并配置 API Key")
    return config


@router.post("/parse-filename/preview", response_model=ParseFilenameBatchResponse)
async def parse_filenames_preview(
    payload: ParseFilenameBatchRequest, session: Session = Depends(get_session)
) -> ParseFilenameBatchResponse:
    """批量按文件名解析标签（dry-run）：列出解析结果与将写入的差异，不写盘。"""
    config = _resolve_ai_or_400(session, payload.use_ai)
    result = await FilenameParseService().preview(
        session, payload.ids, use_ai=payload.use_ai, strategy=payload.strategy, config=config
    )
    return ParseFilenameBatchResponse(**result)


@router.post("/parse-filename", response_model=TaskAccepted)
async def parse_filenames_apply(payload: ParseFilenameBatchRequest) -> TaskAccepted:
    """批量按文件名写回标签（后台任务）。"""
    with session_scope() as session:
        config = _resolve_ai_or_400(session, payload.use_ai)

    async def runner(ctx) -> None:  # noqa: ANN001
        await ctx.set_total(len(payload.ids))
        with session_scope() as session:
            stats = await FilenameParseService().apply(
                session,
                payload.ids,
                use_ai=payload.use_ai,
                strategy=payload.strategy,
                config=config,
            )
        await ctx.message(
            f"文件名解析完成：写入 {stats['changed']} / 共 {stats['total']}，"
            f"跳过 {stats['unchanged'] + stats['invalid']}，失败 {stats['failed']}"
        )

    task_id = await task_manager.run("parse_filename", runner, total=len(payload.ids))
    return TaskAccepted(task_id=task_id)
