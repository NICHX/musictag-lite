"""对外 API（``/api/open``）：供外部系统（Navidrome / 脚本 / 自建前端 / 智能音箱等）集成。

与内部 SPA 使用的 ``/api/*`` 相互独立，只开放**核心功能白名单**：

- 浏览：库 / 曲目列表·详情·聚合 / 封面 / 歌词 / 试听 / 数据源列表
- 匹配：发起检索（返回候选）、指纹识别、写入匹配结果
- 写入：单条标签编辑、歌词写入

**不开放**管理类与重型接口：库增删改与扫描、数据源配置、批量编辑/批量解析、
封面替换、整理/转码、任务与日志、扩展管理、应用设置等（这些仅内部 SPA 使用）。

所有接口统一要求 API Token，可在「设置 → 对外 API」中查看/重置：

- ``Authorization: Bearer <token>``
- ``X-API-Token: <token>``
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api import covers, health, library, lyrics, providers, scrape, tracks
from app.api.deps import require_api_token
from app.core.config import get_settings

router = APIRouter(prefix="/open", tags=["open"], dependencies=[Depends(require_api_token)])


@router.get("", summary="对外 API 索引")
def open_index() -> dict[str, object]:
    """返回对外 API 的基本信息与开放端点。"""
    return {
        "name": "MusicTag Lite 对外 API",
        "version": get_settings().app_version,
        "auth": "请求头携带 Authorization: Bearer <token> 或 X-API-Token: <token>",
        "docs": "/docs",
        "endpoints": {
            # 浏览
            "health": "GET /api/open/health",
            "version": "GET /api/open/version",
            "libraries": "GET /api/open/libraries",
            "providers": "GET /api/open/providers",
            "tracks": "GET /api/open/tracks",
            "track_ids": "GET /api/open/tracks/ids",
            "track_facets": "GET /api/open/tracks/facets",
            "track": "GET /api/open/tracks/{track_id}",
            "cover": "GET /api/open/tracks/{track_id}/cover",
            "lyrics": "GET /api/open/tracks/{track_id}/lyrics",
            "stream": "GET /api/open/tracks/{track_id}/stream",
            # 匹配
            "scrape_search": "POST /api/open/scrape/search",
            "scrape_fingerprint": "POST /api/open/scrape/fingerprint",
            "scrape_apply": "POST /api/open/scrape/apply",
            # 写入
            "track_update": "PATCH /api/open/tracks/{track_id}",
            "lyrics_write": "PUT /api/open/tracks/{track_id}/lyrics",
        },
    }


# ---- 浏览（只读）----
router.add_api_route("/health", health.health, methods=["GET"])
router.add_api_route("/version", health.version, methods=["GET"])
router.add_api_route("/libraries", library.list_libraries, methods=["GET"])
router.add_api_route("/providers", providers.list_providers, methods=["GET"])
router.add_api_route("/tracks/facets", tracks.track_facets, methods=["GET"])
router.add_api_route("/tracks/ids", tracks.list_track_ids, methods=["GET"])
router.add_api_route("/tracks", tracks.list_tracks, methods=["GET"])
router.add_api_route("/tracks/{track_id}/cover", covers.get_cover, methods=["GET"])
router.add_api_route("/tracks/{track_id}/lyrics", lyrics.get_lyrics, methods=["GET"])
router.add_api_route("/tracks/{track_id}/stream", tracks.stream_track, methods=["GET"])
router.add_api_route("/tracks/{track_id}", tracks.get_track, methods=["GET"])

# ---- 匹配（检索候选 → 写入结果）----
router.add_api_route("/scrape/search", scrape.search, methods=["POST"])
router.add_api_route("/scrape/fingerprint", scrape.fingerprint, methods=["POST"])
router.add_api_route("/scrape/apply", scrape.apply, methods=["POST"])

# ---- 写入（单条编辑）----
router.add_api_route("/tracks/{track_id}", tracks.update_track, methods=["PATCH"])
router.add_api_route("/tracks/{track_id}/lyrics", lyrics.put_lyrics, methods=["PUT"])
