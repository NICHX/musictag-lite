"""API 层：REST 路由与 WebSocket 聚合。"""

from fastapi import APIRouter

from app.api import (
    auth,
    convert,
    covers,
    health,
    library,
    logs,
    lyrics,
    organize,
    providers,
    scrape,
    settings,
    tags,
    tasks,
    tracks,
    ws,
)

# 所有 REST 路由（挂载于 /api 前缀下）
api_router = APIRouter()
for _module in (
    health,
    library,
    tracks,
    tags,
    covers,
    lyrics,
    scrape,
    organize,
    convert,
    logs,
    providers,
    settings,
    auth,
    tasks,
):
    api_router.include_router(_module.router)

# WebSocket 挂在根路径（/ws/events，不带 /api 前缀）
ws_router = ws.router

__all__ = ["api_router", "ws_router"]
