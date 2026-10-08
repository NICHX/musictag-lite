"""健康检查与版本信息。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app import __version__
from app.core.config import get_settings
from app.core.db import get_session
from app.models.schemas import Capabilities, HealthResponse
from app.services.ai_config import is_ai_available
from app.services.convert_service import ffmpeg_available, fpcalc_available

router = APIRouter(tags=["meta"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        name=settings.app_name,
        version=settings.app_version or __version__,
        environment=settings.environment,
        ffmpeg=ffmpeg_available(),
    )


@router.get("/version")
def version() -> dict[str, str]:
    settings = get_settings()
    return {"name": settings.app_name, "version": settings.app_version or __version__}


@router.get("/capabilities", response_model=Capabilities)
def capabilities(session: Session = Depends(get_session)) -> Capabilities:
    """可选能力检测（核心功能零 ffmpeg 依赖；AI 辅助默认关闭）。"""
    return Capabilities(
        ffmpeg=ffmpeg_available(),
        fpcalc=fpcalc_available(),
        ai=is_ai_available(session),
    )
