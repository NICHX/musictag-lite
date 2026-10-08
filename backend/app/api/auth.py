"""鉴权（P2，可选启用）。默认关闭。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import not_implemented
from app.core.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(payload: dict[str, str]) -> dict[str, str]:
    settings = get_settings()
    if not settings.auth_enabled:
        raise HTTPException(status_code=400, detail="鉴权未启用（可选功能，默认关闭）")
    raise not_implemented("M3", "登录鉴权将在 M3（P2）实现")


@router.post("/logout")
def logout() -> dict[str, bool]:
    return {"ok": True}
