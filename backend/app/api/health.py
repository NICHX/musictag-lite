"""健康检查与版本信息。"""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.core.config import get_settings
from app.models.schemas import HealthResponse
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


@router.get("/capabilities")
def capabilities() -> dict[str, bool]:
    """外部可选依赖检测结果（核心功能零 ffmpeg 依赖）。"""
    return {"ffmpeg": ffmpeg_available(), "fpcalc": fpcalc_available()}
