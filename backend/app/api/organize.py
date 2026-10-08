"""整理：按模板重命名/移动（F15，P1）。落盘在 M2。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import not_implemented
from app.models.schemas import OrganizePreviewRequest, OrganizePreviewResponse, TaskAccepted

router = APIRouter(prefix="/organize", tags=["organize"])


@router.post("/preview", response_model=OrganizePreviewResponse)
def preview(payload: OrganizePreviewRequest) -> OrganizePreviewResponse:
    raise not_implemented("M2", "模板化整理预演将在 M2（P1）实现")


@router.post("/apply", response_model=TaskAccepted)
def apply(payload: OrganizePreviewRequest) -> TaskAccepted:
    raise not_implemented("M2", "模板化整理执行将在 M2（P1）实现")
