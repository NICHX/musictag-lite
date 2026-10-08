"""路由公共依赖与工具。"""

from __future__ import annotations

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models.db import Library


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
