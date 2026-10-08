"""路由公共依赖与工具。"""

from __future__ import annotations

from fastapi import HTTPException
from sqlmodel import Session, select

from app.core.security import PathSecurityError, ensure_within_roots
from app.models.db import Library, Track


def not_implemented(milestone: str = "M1", detail: str | None = None) -> HTTPException:
    """返回 501，明确标注该能力所属里程碑（接口先行、契约稳定）。"""
    return HTTPException(
        status_code=501,
        detail=detail or f"该接口将在 {milestone} 实现",
        headers={"X-Milestone": milestone},
    )


def library_roots(session: Session) -> list[str]:
    """当前已配置的库根目录白名单（用于路径安全校验）。"""
    return [lib.root_path for lib in session.exec(select(Library)).all()]


def ensure_track_path(session: Session, track: Track) -> None:
    """校验曲目文件确实位于已配置的库根目录内，防止路径穿越。"""
    try:
        ensure_within_roots(track.path, library_roots(session))
    except PathSecurityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def get_track_or_404(session: Session, track_id: int) -> Track:
    track = session.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=404, detail="曲目不存在")
    return track
