"""API 层：REST 路由与 WebSocket 聚合。

对外文档（``/docs``）默认**只包含对外 API ``/api/open``**，内部 ``/api/*``
（含库管理、数据源配置、批量任务等）不进入 OpenAPI；如需完整文档可设
``DOCS_INCLUDE_INTERNAL=true``。
"""

from fastapi import APIRouter

from app.api import (
    auth,
    convert,
    covers,
    extensions,
    health,
    library,
    logs,
    lyrics,
    open,
    organize,
    providers,
    scrape,
    settings,
    tags,
    tasks,
    tracks,
    ws,
)
from app.core.config import get_settings

# 内部 REST 路由（挂载于 /api 前缀下；默认不进入对外文档）
api_router = APIRouter()
_publish_internal = get_settings().docs_include_internal
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
    extensions,
    settings,
    auth,
    tasks,
):
    api_router.include_router(_module.router, include_in_schema=_publish_internal)

# 对外 API：始终进入文档
api_router.include_router(open.router)

# WebSocket 挂在根路径（/ws/events，不带 /api 前缀）
ws_router = ws.router

__all__ = ["api_router", "ws_router"]
