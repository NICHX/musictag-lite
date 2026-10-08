"""封面服务：内嵌封面 + 同名文件兜底、替换、删除、导出（F5）。"""

from __future__ import annotations

from pathlib import Path

from sqlmodel import Session

from app.audio.base import AudioIO, CoverImage
from app.audio.mutagen_io import audio_io
from app.models.db import Track, utcnow
from app.services import oplog
from app.services.organize_service import render_template

# 目录兜底封面候选文件名（按优先级）
SIDECAR_COVER_NAMES: tuple[str, ...] = (
    "cover.jpg",
    "cover.png",
    "folder.jpg",
    "folder.png",
    "front.jpg",
)


def find_sidecar_cover(directory: str | Path) -> Path | None:
    """在同目录下查找兜底封面文件。"""
    base = Path(directory)
    for name in SIDECAR_COVER_NAMES:
        candidate = base / name
        if candidate.is_file():
            return candidate
    return None


def _mime_for(name: str) -> str:
    return "image/png" if name.lower().endswith(".png") else "image/jpeg"


def _ext_for(mime: str) -> str:
    return ".png" if mime == "image/png" else ".jpg"


class CoverService:
    """封面读取/写入/删除/导出。"""

    def __init__(self, audio: AudioIO | None = None) -> None:
        self.audio = audio or audio_io

    def read(self, track: Track) -> tuple[CoverImage | None, str | None]:
        """返回 (封面, 来源)：优先内嵌，其次目录同名文件。"""
        try:
            cover = self.audio.read_cover(Path(track.path))
        except Exception:  # noqa: BLE001 - 损坏文件不应影响列表
            cover = None
        if cover is not None:
            return cover, "embedded"

        sidecar = find_sidecar_cover(Path(track.path).parent)
        if sidecar is not None:
            return CoverImage(data=sidecar.read_bytes(), mime=_mime_for(sidecar.name)), "file"
        return None, None

    def write(
        self,
        session: Session,
        track: Track,
        cover: CoverImage,
        *,
        kind: str = "front",
        source: str = "manual",
    ) -> None:
        """写入内嵌封面并更新索引与日志。"""
        cover.kind = kind
        self.audio.write_cover(Path(track.path), cover)
        track.has_cover = True
        track.updated_at = utcnow()
        session.add(track)
        oplog.record(session, track_id=track.id, action="cover.write", source=source)
        session.commit()
        session.refresh(track)

    def delete(self, session: Session, track: Track, *, source: str = "manual") -> bool:
        """删除内嵌封面（保留目录同名文件）；返回是否确有删除。"""
        removed = self.audio.delete_cover(Path(track.path))
        track.has_cover = find_sidecar_cover(Path(track.path).parent) is not None
        track.updated_at = utcnow()
        session.add(track)
        oplog.record(
            session,
            track_id=track.id,
            action="cover.delete",
            source=source,
            new="removed" if removed else "none",
        )
        session.commit()
        session.refresh(track)
        return removed

    def export(
        self,
        session: Session,
        tracks: list[Track],
        *,
        target_dir: str | None = None,
        filename_template: str = "{artist} - {album}",
    ) -> list[str]:
        """批量导出封面为文件；返回写出的文件路径列表。"""
        written: list[str] = []
        for track in tracks:
            cover, _source = self.read(track)
            if cover is None:
                continue
            directory = Path(target_dir) if target_dir else Path(track.path).parent
            directory.mkdir(parents=True, exist_ok=True)
            stem = (
                render_template(
                    filename_template,
                    {
                        "artist": track.artist or track.album_artist,
                        "album": track.album,
                        "title": track.title,
                        "year": track.year,
                        "track": track.track_no,
                    },
                )
                or Path(track.path).stem
            )
            target = directory / f"{stem}{_ext_for(cover.mime)}"
            target.write_bytes(cover.data)
            written.append(str(target))
            oplog.record(
                session,
                track_id=track.id,
                action="cover.export",
                source="batch",
                new=str(target),
            )
        session.commit()
        return written
