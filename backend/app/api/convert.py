"""转换：ffmpeg 转码（F18，P2，可选）。缺 ffmpeg 时明确拒绝且不影响核心。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import not_implemented
from app.models.schemas import ConvertRequest, TaskAccepted
from app.services.convert_service import ffmpeg_available

router = APIRouter(tags=["convert"])


@router.post("/convert", response_model=TaskAccepted)
def convert(payload: ConvertRequest) -> TaskAccepted:
    if not ffmpeg_available():
        raise HTTPException(
            status_code=400,
            detail="未检测到 ffmpeg，转码功能不可用（核心功能不受影响）",
        )
    raise not_implemented("M2", "ffmpeg 转码将在 M2（P2）实现")
