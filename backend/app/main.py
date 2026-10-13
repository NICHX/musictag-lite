"""FastAPI 应用入口。

- 提供 `/api/*` 与 `/ws/events`；
- 生产模式下同时托管前端静态资源（SPA 回退到 index.html）；
- 启动时初始化日志与数据库（迁移由 Alembic 负责）。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import api_router, ws_router
from app.core.config import get_settings
from app.core.db import init_db, run_migrations
from app.core.logging import get_logger, setup_logging
from app.extensions import extension_manager
from app.services.maintenance import purge_orphan_tracks
from app.services.scrape_orchestrator import scrape_orchestrator

settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging(logging.DEBUG if settings.debug else logging.INFO)
    settings.ensure_data_dir()
    if settings.debug:
        # 开发模式：启动时自动迁移，`uvicorn app.main:app` 即可跑起来
        run_migrations()
    init_db()
    # 加载已安装的扩展（社区刮削源以可安装扩展形式提供，不再随核心内置）
    extension_manager.load_all()
    # 清理历史上「删库未删曲目」遗留的孤儿记录（仅数据库，不动磁盘文件）
    purge_orphan_tracks()
    logger.info(
        "app.startup",
        extra={"env": settings.environment, "version": settings.app_version or __version__},
    )
    try:
        yield
    finally:
        await scrape_orchestrator.aclose()
        logger.info("app.shutdown")


def _frontend_available() -> bool:
    return settings.serve_frontend and (settings.frontend_dist / "index.html").exists()


def _mount_frontend(app: FastAPI) -> None:
    """生产模式：托管构建后的前端静态资源，并做 SPA 回退。"""
    dist = settings.frontend_dist
    index = dist / "index.html"
    assets = dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith(f"{settings.api_prefix.strip('/')}/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version or __version__,
        description="MusicTag Lite — 轻量自托管音乐标签管理 API",
        lifespan=lifespan,
        openapi_url=f"{settings.api_prefix}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=settings.api_prefix)
    app.include_router(ws_router)

    if _frontend_available():
        _mount_frontend(app)
    else:

        @app.get("/", include_in_schema=False)
        async def root() -> dict[str, str]:
            return {
                "name": settings.app_name,
                "version": settings.app_version or __version__,
                "docs": "/docs",
                "api": settings.api_prefix,
            }

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=settings.debug)
