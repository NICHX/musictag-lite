"""库管理（F1 配置部分）：CRUD + 触发扫描（扫描落库在 M1）。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, func, select

from app.core.config import get_settings
from app.core.db import get_session
from app.core.tasks import task_manager
from app.models.db import Library, Track
from app.models.schemas import LibraryCreate, LibraryRead, LibraryUpdate, TaskAccepted
from app.services.maintenance import purge_library_tracks
from app.services.scanner import Scanner

router = APIRouter(prefix="/libraries", tags=["libraries"])


def _to_read(session: Session, lib: Library) -> LibraryRead:
    count = session.exec(
        select(func.count()).select_from(Track).where(Track.library_id == lib.id)
    ).one()
    data = LibraryRead.model_validate(lib)
    data.track_count = int(count)
    return data


def _get_or_404(session: Session, library_id: int) -> Library:
    lib = session.get(Library, library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="库不存在")
    return lib


@router.get("", response_model=list[LibraryRead])
def list_libraries(session: Session = Depends(get_session)) -> list[LibraryRead]:
    libs = session.exec(select(Library).order_by(Library.id)).all()
    return [_to_read(session, lib) for lib in libs]


@router.post("", response_model=LibraryRead, status_code=201)
def create_library(payload: LibraryCreate, session: Session = Depends(get_session)) -> LibraryRead:
    root = Path(payload.root_path).expanduser()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail=f"目录不存在或不是目录：{payload.root_path}")
    resolved = str(root.resolve())
    duplicate = session.exec(select(Library).where(Library.root_path == resolved)).first()
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="该库根目录已存在")

    lib = Library(
        name=payload.name,
        root_path=resolved,
        enabled=payload.enabled,
        scan_mode=payload.scan_mode,
    )
    session.add(lib)
    session.commit()
    session.refresh(lib)
    return _to_read(session, lib)


@router.get("/{library_id}", response_model=LibraryRead)
def get_library(library_id: int, session: Session = Depends(get_session)) -> LibraryRead:
    return _to_read(session, _get_or_404(session, library_id))


@router.patch("/{library_id}", response_model=LibraryRead)
def update_library(
    library_id: int, payload: LibraryUpdate, session: Session = Depends(get_session)
) -> LibraryRead:
    lib = _get_or_404(session, library_id)
    data = payload.model_dump(exclude_unset=True)
    if "root_path" in data and data["root_path"]:
        root = Path(data["root_path"]).expanduser()
        if not root.exists() or not root.is_dir():
            raise HTTPException(
                status_code=400, detail=f"目录不存在或不是目录：{data['root_path']}"
            )
        data["root_path"] = str(root.resolve())
    for key, value in data.items():
        setattr(lib, key, value)
    session.add(lib)
    session.commit()
    session.refresh(lib)
    return _to_read(session, lib)


@router.delete("/{library_id}", status_code=204)
def delete_library(library_id: int, session: Session = Depends(get_session)) -> None:
    """删除音乐库及其曲目索引（仅数据库记录，磁盘上的音频文件不受影响）。"""
    lib = _get_or_404(session, library_id)
    purge_library_tracks(session, library_id)
    session.delete(lib)
    session.commit()


@router.post("/{library_id}/scan", response_model=TaskAccepted)
async def scan_library(library_id: int, session: Session = Depends(get_session)) -> TaskAccepted:
    """触发一次扫描（增量或全量，依库的 scan_mode），返回 task_id。"""
    library = _get_or_404(session, library_id)
    settings = get_settings()
    scanner = Scanner(
        extensions=settings.scan_extensions,
        ignore_names=settings.scan_ignore_names,
    )
    full = library.scan_mode == "full"
    library_name = library.name

    async def runner(ctx) -> None:  # noqa: ANN001
        stats = await scanner.scan_library(library_id, full=full, ctx=ctx)
        await ctx.message(
            f"「{library_name}」扫描完成：更新 {stats.scanned}，未变 {stats.unchanged}，"
            f"失败 {stats.failed}，移除 {stats.removed}"
        )

    task_id = await task_manager.run("scan", runner)
    return TaskAccepted(task_id=task_id)
