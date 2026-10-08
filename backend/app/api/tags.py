"""标签批量编辑（F4）：预演（dry-run）与执行。落盘在 M1。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.deps import not_implemented
from app.core.db import get_session
from app.models.schemas import BatchEditRequest, BatchPreviewResponse, TaskAccepted

router = APIRouter(prefix="/tracks", tags=["tags"])


@router.post("/batch/preview", response_model=BatchPreviewResponse)
def batch_preview(
    payload: BatchEditRequest, session: Session = Depends(get_session)
) -> BatchPreviewResponse:
    raise not_implemented("M1", "批量变更预演将在 M1 实现")


@router.post("/batch", response_model=TaskAccepted)
def batch_edit(payload: BatchEditRequest, session: Session = Depends(get_session)) -> TaskAccepted:
    raise not_implemented("M1", "批量标签写入将在 M1 实现")
