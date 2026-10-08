"""封面：查看/替换/删除/导出（F5）；批量导出/替换（F20）。"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlmodel import Session

from app.api.deps import ensure_track_path, get_track_or_404, library_roots
from app.audio.base import CoverImage
from app.core.db import get_session, session_scope
from app.core.security import PathSecurityError, ensure_within_roots
from app.core.tasks import task_manager
from app.models.db import Track
from app.models.schemas import (
    CoverBatchExportRequest,
    CoverBatchExportResponse,
    CoverBatchPreviewRequest,
    CoverBatchPreviewResponse,
    CoverMeta,
    TaskAccepted,
)
from app.services.cover_batch import CoverBatchService
from app.services.cover_service import CoverService

router = APIRouter(tags=["covers"])

MAX_COVER_BYTES = 20 * 1024 * 1024
MAX_REPLACE_FILES = 200
MAX_REPLACE_TOTAL_BYTES = 512 * 1024 * 1024
_COVER_KINDS = {"front", "back", "other"}


@router.get("/tracks/{track_id}/cover")
def get_cover(track_id: int, session: Session = Depends(get_session)) -> Response:
    """返回封面二进制（内嵌优先，其次目录同名文件）。"""
    track = get_track_or_404(session, track_id)
    ensure_track_path(session, track)
    cover, source = CoverService().read(track)
    if cover is None:
        raise HTTPException(status_code=404, detail="该曲目没有封面")
    return Response(
        content=cover.data,
        media_type=cover.mime,
        headers={"X-Cover-Source": source or "", "Cache-Control": "no-cache"},
    )


@router.put("/tracks/{track_id}/cover", response_model=CoverMeta)
async def put_cover(
    track_id: int,
    file: UploadFile = File(...),
    kind: str = Query("front", description="front / back / other"),
    session: Session = Depends(get_session),
) -> CoverMeta:
    """上传/替换内嵌封面（multipart）。"""
    track = get_track_or_404(session, track_id)
    ensure_track_path(session, track)

    if kind not in _COVER_KINDS:
        raise HTTPException(status_code=400, detail=f"封面类型无效：{kind}")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传内容为空")
    if len(data) > MAX_COVER_BYTES:
        raise HTTPException(status_code=413, detail="封面过大（上限 20MB）")

    mime = file.content_type or "image/jpeg"
    if not mime.startswith("image/"):
        raise HTTPException(status_code=400, detail=f"仅支持图片类型，收到：{mime}")

    CoverService().write(session, track, CoverImage(data=data, mime=mime, kind=kind))
    return CoverMeta(track_id=track_id, available=True, source="embedded", mime=mime)


@router.delete("/tracks/{track_id}/cover")
def delete_cover(track_id: int, session: Session = Depends(get_session)) -> dict[str, bool]:
    """删除内嵌封面（保留目录同名文件）。"""
    track = get_track_or_404(session, track_id)
    ensure_track_path(session, track)
    return {"removed": CoverService().delete(session, track)}


@router.post("/covers/batch-export", response_model=CoverBatchExportResponse)
def batch_export(
    payload: CoverBatchExportRequest, session: Session = Depends(get_session)
) -> CoverBatchExportResponse:
    """批量导出封面到目录。"""
    if payload.target_dir:
        try:
            ensure_within_roots(payload.target_dir, library_roots(session))
        except PathSecurityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    tracks = [track for track in (session.get(Track, i) for i in payload.ids) if track]
    files = CoverService().export(
        session,
        tracks,
        target_dir=payload.target_dir,
        filename_template=payload.filename_template,
    )
    return CoverBatchExportResponse(exported=len(files), files=files)


@router.post("/covers/batch-preview", response_model=CoverBatchPreviewResponse)
def batch_preview(
    payload: CoverBatchPreviewRequest, session: Session = Depends(get_session)
) -> CoverBatchPreviewResponse:
    """按图片文件名在选中曲目内做优先级链匹配（dry-run，不写盘）。"""
    result = CoverBatchService().preview(session, payload.ids, payload.filenames)
    return CoverBatchPreviewResponse(**result)


@router.post("/covers/batch-replace", response_model=TaskAccepted)
async def batch_replace(
    files: list[UploadFile] = File(...),
    assignments: str = Form(..., description="JSON：[{index, track_ids}]"),
) -> TaskAccepted:
    """按用户确认的指派批量写入内嵌封面（后台任务）。

    指派以「文件下标 → 曲目 id」为准（与预演一致，不重新匹配）；空 ``track_ids`` 即忽略该图片。
    """
    try:
        planned = json.loads(assignments)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="assignments 不是合法 JSON") from exc
    if not isinstance(planned, list):
        raise HTTPException(status_code=400, detail="assignments 应为数组")
    if len(files) > MAX_REPLACE_FILES:
        raise HTTPException(status_code=413, detail=f"文件数过多（上限 {MAX_REPLACE_FILES}）")

    media: dict[int, tuple[bytes, str]] = {}
    total = 0
    for index, upload in enumerate(files):
        data = await upload.read()
        if not data:
            raise HTTPException(status_code=400, detail=f"第 {index + 1} 个文件为空")
        if len(data) > MAX_COVER_BYTES:
            raise HTTPException(status_code=413, detail=f"第 {index + 1} 个文件过大（上限 20MB）")
        mime = upload.content_type or "image/jpeg"
        if not mime.startswith("image/"):
            raise HTTPException(status_code=400, detail=f"第 {index + 1} 个文件不是图片：{mime}")
        total += len(data)
        if total > MAX_REPLACE_TOTAL_BYTES:
            raise HTTPException(status_code=413, detail="上传总量过大（上限 512MB）")
        media[index] = (data, mime)

    writes: list[dict] = []
    for item in planned:
        if not isinstance(item, dict):
            continue
        entry = media.get(item.get("index"))
        if entry is None:
            continue
        data, mime = entry
        for track_id in item.get("track_ids") or []:
            writes.append({"track_id": track_id, "data": data, "mime": mime})

    if not writes:
        raise HTTPException(status_code=400, detail="没有可写入的指派")

    service = CoverBatchService()

    def work() -> dict:
        with session_scope() as session:
            return service.apply(session, writes)

    async def runner(ctx) -> None:  # noqa: ANN001
        await ctx.set_total(len(writes))
        stats = await asyncio.to_thread(work)
        await ctx.message(
            f"封面写入完成：成功 {stats['written']} / 共 {stats['total']}，失败 {stats['failed']}"
        )

    task_id = await task_manager.run("cover_write", runner, total=len(writes))
    return TaskAccepted(task_id=task_id)
