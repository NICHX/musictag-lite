"""封面：查看/替换/删除/导出（F5）。读写落盘在 M1。"""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile

from app.api.deps import not_implemented
from app.models.schemas import CoverBatchExportRequest, CoverBatchExportResponse, CoverMeta

router = APIRouter(tags=["covers"])


@router.get("/tracks/{track_id}/cover")
def get_cover(track_id: int):
    raise not_implemented("M1", "封面读取（内嵌 + cover.jpg 兜底）将在 M1 实现")


@router.put("/tracks/{track_id}/cover", response_model=CoverMeta)
def put_cover(track_id: int, file: UploadFile = File(...)) -> CoverMeta:
    raise not_implemented("M1", "封面替换将在 M1 实现")


@router.delete("/tracks/{track_id}/cover")
def delete_cover(track_id: int):
    raise not_implemented("M1", "封面删除将在 M1 实现")


@router.post("/covers/batch-export", response_model=CoverBatchExportResponse)
def batch_export(payload: CoverBatchExportRequest) -> CoverBatchExportResponse:
    raise not_implemented("M1", "封面批量导出将在 M1 实现")
