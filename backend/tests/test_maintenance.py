"""删库级联与孤儿曲目清理（只动数据库，不动磁盘文件）。"""

from __future__ import annotations

from pathlib import Path

from sqlmodel import Session

from app.core.db import engine
from app.models.db import CoverCache, Library, LyricsAsset, OperationLog, Track
from app.services.maintenance import purge_library_tracks, purge_orphan_tracks


def _make_library(session: Session, name: str, root: Path) -> Library:
    root.mkdir(parents=True, exist_ok=True)
    library = Library(name=name, root_path=str(root))
    session.add(library)
    session.commit()
    session.refresh(library)
    return library


def test_delete_library_removes_its_tracks(client, tmp_path: Path) -> None:
    root = tmp_path / "del-me"
    with Session(engine) as session:
        library = _make_library(session, "del-me", root)
        track = Track(
            library_id=library.id,
            path=str(root / "a.flac"),
            filename="a.flac",
            title="A",
        )
        session.add(track)
        session.commit()
        session.refresh(track)
        track_id, library_id = track.id, library.id

    assert client.delete(f"/api/libraries/{library_id}").status_code == 204
    assert client.get(f"/api/tracks/{track_id}").status_code == 404


def test_purge_orphan_tracks_removes_records_without_library(client, tmp_path: Path) -> None:
    """模拟历史 bug：直接删库记录而未删曲目 → 需要被自动清理。"""
    root = tmp_path / "orphan"
    with Session(engine) as session:
        library = _make_library(session, "orphan", root)
        track = Track(
            library_id=library.id,
            path=str(root / "b.flac"),
            filename="b.flac",
            title="B",
        )
        session.add(track)
        session.commit()
        session.refresh(track)
        track_id, library_id = track.id, library.id

    # 复现历史遗留状态：绕过外键约束直接删掉库记录，留下孤儿曲目
    raw = engine.raw_connection()
    try:
        cursor = raw.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute("DELETE FROM library WHERE id=?", (library_id,))
        raw.commit()
    finally:
        raw.close()

    assert purge_orphan_tracks() >= 1
    assert client.get(f"/api/tracks/{track_id}").status_code == 404


def test_purge_library_tracks_clears_dependent_rows(tmp_path: Path) -> None:
    """曲目的封面缓存/歌词资源应先被清理，否则外键约束会失败。"""
    root = tmp_path / "deps"
    with Session(engine) as session:
        library = _make_library(session, "deps", root)
        track = Track(library_id=library.id, path=str(root / "c.flac"), filename="c.flac")
        session.add(track)
        session.commit()
        session.refresh(track)
        session.add(CoverCache(track_id=track.id, mime="image/jpeg"))
        session.add(LyricsAsset(track_id=track.id, content_ref="c.lrc"))
        session.add(OperationLog(action="tag.update", track_id=track.id, result="success"))
        session.commit()

        removed = purge_library_tracks(session, library.id)
        assert removed == 1
        assert session.get(Track, track.id) is None
        assert (
            session.exec(
                __import__("sqlmodel").select(CoverCache).where(CoverCache.track_id == track.id)
            ).all()
            == []
        )


def test_purge_orphan_tracks_is_noop_when_clean(tmp_path: Path) -> None:
    root = tmp_path / "clean"
    with Session(engine) as session:
        _make_library(session, "clean", root)
    assert purge_orphan_tracks() == 0
