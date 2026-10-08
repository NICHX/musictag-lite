"""封面：查看/替换/删除/导出（F5）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlmodel import Session

from app.api.deps import ensure_track_path, get_track_or_404, library_roots
from app.audio.base import CoverImage
from app.core.db import get_session
from app.core.security import PathSecurityError, ensure_within_roots
from app.models.db import Track
from app.models.schemas import CoverBatchExportRequest, CoverBatchExportResponse, CoverMeta
from app.services.cover_service import CoverService

router = APIRouter(tags=["covers"])

MAX_COVER_BYTES = 20 * 1024 * 1024
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
