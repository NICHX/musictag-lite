"""扩展管理：列出 / 一键安装（内置目录）/ 上传安装（zip）/ 卸载。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, delete

from app.core.db import get_session
from app.extensions import ExtensionError, ExtensionInfo, extension_manager
from app.models.db import ProviderConfig
from app.models.schemas import ExtensionRead, ExtensionsRead
from app.services.scrape_orchestrator import scrape_orchestrator

router = APIRouter(prefix="/extensions", tags=["extensions"])


def _to_read(info: ExtensionInfo) -> ExtensionRead:
    return ExtensionRead(
        key=info.key,
        name=info.name,
        version=info.version,
        description=info.description,
        author=info.author,
        installed=info.installed,
        builtin=info.builtin,
        providers=info.providers,
    )


@router.get("", response_model=ExtensionsRead)
def list_extensions() -> ExtensionsRead:
    """列出已安装扩展与可安装（内置目录）扩展。"""
    return ExtensionsRead(
        installed=[_to_read(info) for info in extension_manager.installed()],
        catalog=[_to_read(info) for info in extension_manager.catalog()],
    )


@router.post("/install", response_model=ExtensionRead)
async def install_uploaded(file: UploadFile = File(...)) -> ExtensionRead:
    """上传扩展 zip 并安装（zip 内应为单一顶层目录，含 extension.json）。"""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传文件为空")
    try:
        info = extension_manager.install_from_zip(data)
    except ExtensionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    scrape_orchestrator.rebind()
    return _to_read(info)


@router.post("/catalog/{key}/install", response_model=ExtensionRead)
def install_from_catalog(key: str) -> ExtensionRead:
    """从内置扩展目录一键安装。"""
    try:
        info = extension_manager.install_from_catalog(key)
    except ExtensionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    scrape_orchestrator.rebind()
    return _to_read(info)


@router.delete("/{key}")
def uninstall(key: str, session: Session = Depends(get_session)) -> dict[str, object]:
    """卸载扩展：注销其 Provider、清理其配置并删除扩展目录。"""
    try:
        removed = extension_manager.uninstall(key)
    except ExtensionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if removed:
        session.exec(delete(ProviderConfig).where(ProviderConfig.provider_key.in_(removed)))
        session.commit()
    scrape_orchestrator.rebind()
    return {"key": key, "removed_providers": removed}
