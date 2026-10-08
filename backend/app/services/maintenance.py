"""数据维护：清理失去归属的曲目索引。

重要：只操作数据库，**永不删除磁盘上的音频文件**。

SQLite 外键为 NO ACTION，删除曲目时必须先清依赖表（封面缓存 / 歌词资源），
并把可空引用（刮削候选 / 操作日志）置空，否则会触发外键约束失败。
"""

from __future__ import annotations

from sqlalchemy import delete, update
from sqlmodel import Session, select

from app.core.logging import get_logger
from app.models.db import (
    CoverCache,
    Library,
    LyricsAsset,
    OperationLog,
    ScrapeCandidate,
    Track,
)

logger = get_logger(__name__)


def _delete_tracks(session: Session, track_ids: list[int]) -> int:
    if not track_ids:
        return 0
    for model in (CoverCache, LyricsAsset):
        session.execute(delete(model).where(model.track_id.in_(track_ids)))  # type: ignore[attr-defined]
    for model in (ScrapeCandidate, OperationLog):
        session.execute(  # type: ignore[attr-defined]
            update(model).where(model.track_id.in_(track_ids)).values(track_id=None)
        )
    session.execute(delete(Track).where(Track.id.in_(track_ids)))  # type: ignore[attr-defined]
    return len(track_ids)


def purge_library_tracks(session: Session, library_id: int) -> int:
    """删除指定库下的全部曲目索引（不触碰磁盘文件）。"""
    ids = [
        track.id
        for track in session.exec(select(Track).where(Track.library_id == library_id)).all()
        if track.id is not None
    ]
    removed = _delete_tracks(session, ids)
    session.commit()
    return removed


def purge_orphan_tracks(session: Session | None = None) -> int:
    """删除 library_id 已不存在的孤儿曲目记录（修复历史残留）。"""
    if session is not None:
        return _purge(session)

    from app.core.db import session_scope

    with session_scope() as own:
        return _purge(own)


def _purge(session: Session) -> int:
    known = {row for row in session.exec(select(Library.id)).all() if row is not None}
    ids = [
        track.id
        for track in session.exec(select(Track)).all()
        if track.id is not None and track.library_id not in known
    ]
    removed = _delete_tracks(session, ids)
    session.commit()
    if removed:
        logger.warning("db.orphan_tracks_purged", extra={"count": removed})
    return removed
