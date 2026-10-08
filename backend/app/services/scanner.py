"""扫描服务：遍历库根目录、增量识别、读取标签并更新索引（F1）。

文件系统与 mutagen 读取在**工作线程**中执行，进度经回调转交事件循环推送，
避免阻塞 FastAPI 的 event loop。
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import select

from app.audio.base import AudioIO
from app.audio.formats import ALLOWED_EXTENSIONS, format_name
from app.audio.mutagen_io import audio_io
from app.core.db import session_scope
from app.core.logging import get_logger
from app.core.tasks import TaskContext
from app.models.db import Library, Track, utcnow
from app.services.cover_service import find_sidecar_cover
from app.services.tag_service import compute_tag_status

logger = get_logger(__name__)

ProgressCallback = Callable[[int, int, str], None]


@dataclass
class ScanStats:
    """一次扫描的统计结果。"""

    total: int = 0
    scanned: int = 0
    unchanged: int = 0
    failed: int = 0
    skipped: int = 0
    removed: int = 0


def iter_audio_files(
    root: str | Path,
    *,
    extensions: frozenset[str] = ALLOWED_EXTENSIONS,
    ignore_names: set[str] | None = None,
) -> Iterator[Path]:
    """递归遍历目录，产出受支持的音频文件（忽略隐藏文件与临时文件）。"""
    ignore_names = ignore_names or set()
    base = Path(root)
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if name.startswith(".") or name in ignore_names:
                continue
            if Path(name).suffix.lower() in extensions:
                yield Path(dirpath) / name


def needs_rescan(existing: Track | None, size: int, mtime: float) -> bool:
    """增量判定：以「路径 + 修改时间 + 文件大小」决定是否重新读取标签。"""
    if existing is None:
        return True
    if existing.size != size:
        return True
    try:
        existing_mtime = existing.mtime.timestamp()
    except (AttributeError, ValueError):
        return True
    return abs(existing_mtime - mtime) > 1.0


def _sync_scan(
    library_id: int,
    *,
    full: bool,
    extensions: frozenset[str],
    ignore_names: set[str],
    audio: AudioIO,
    progress: ProgressCallback,
    commit_every: int = 200,
) -> ScanStats:
    """在工作线程内执行的实际扫描逻辑。"""
    stats = ScanStats()
    with session_scope() as session:
        library = session.get(Library, library_id)
        if library is None:
            raise ValueError(f"库不存在：{library_id}")
        root = library.root_path

        existing: dict[str, Track] = {
            track.path: track
            for track in session.exec(select(Track).where(Track.library_id == library_id)).all()
        }
        paths = sorted(iter_audio_files(root, extensions=extensions, ignore_names=ignore_names))
        total = len(paths)
        stats.total = total
        step = max(1, total // 100)  # 进度事件节流：最多约 100 次推送

        seen: set[str] = set()
        for index, path in enumerate(paths, start=1):
            source = str(path)
            seen.add(source)
            try:
                stat = path.stat()
            except OSError:
                stats.skipped += 1
            else:
                track = existing.get(source)
                if not full and not needs_rescan(track, stat.st_size, stat.st_mtime):
                    stats.unchanged += 1
                else:
                    try:
                        doc = audio.read(path)
                    except Exception:  # noqa: BLE001 - 损坏/不支持的文件不应中断扫描
                        stats.failed += 1
                        logger.warning("scan.read_failed", extra={"path": source})
                    else:
                        if track is None:
                            track = Track(library_id=library_id, path=source)
                        _apply_document(track, path, stat, doc)
                        session.add(track)
                        stats.scanned += 1

            if index % step == 0 or index == total:
                progress(index, total, source)
            if index % commit_every == 0:
                session.commit()

        for source, track in existing.items():
            if source not in seen:
                session.delete(track)
                stats.removed += 1

    logger.info(
        "scan.finished",
        extra={
            "library_id": library_id,
            "total": stats.total,
            "scanned": stats.scanned,
            "unchanged": stats.unchanged,
            "failed": stats.failed,
            "removed": stats.removed,
        },
    )
    return stats


def _apply_document(track: Track, path: Path, stat: os.stat_result, doc: object) -> None:
    """把一次读取结果写入 Track 记录。"""
    tags = doc.tags  # type: ignore[attr-defined]
    props = doc.properties  # type: ignore[attr-defined]
    sidecar = find_sidecar_cover(path.parent)
    lrc = path.with_suffix(".lrc")

    track.dirname = str(path.parent)
    track.filename = path.name
    track.ext = path.suffix.lower()
    track.format = format_name(path.suffix)
    track.size = stat.st_size
    track.mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)

    track.duration = props.duration
    track.bitrate = props.bitrate
    track.sample_rate = props.sample_rate
    track.channels = props.channels
    track.bit_depth = props.bit_depth

    track.title = tags.title
    track.artist = tags.artist
    track.album = tags.album
    track.album_artist = tags.album_artist
    track.composer = tags.composer
    track.genre = tags.genre
    track.track_no = tags.track_no
    track.disc_no = tags.disc_no
    track.year = tags.year
    track.date = tags.date
    track.comment = tags.comment

    track.has_cover = doc.cover is not None or sidecar is not None  # type: ignore[attr-defined]
    track.cover_mtime = (
        datetime.fromtimestamp(sidecar.stat().st_mtime, tz=UTC) if sidecar is not None else None
    )
    track.has_lyrics = bool(tags.lyrics) or lrc.is_file()
    track.tag_status = str(compute_tag_status(tags))
    track.updated_at = utcnow()


class Scanner:
    """库扫描器。"""

    def __init__(
        self,
        *,
        audio: AudioIO | None = None,
        extensions: frozenset[str] | None = None,
        ignore_names: set[str] | None = None,
    ) -> None:
        self.audio = audio or audio_io
        self.extensions = extensions if extensions is not None else ALLOWED_EXTENSIONS
        self.ignore_names = ignore_names or set()

    async def scan_library(
        self,
        library_id: int,
        *,
        full: bool = False,
        ctx: TaskContext | None = None,
    ) -> ScanStats:
        """扫描指定库；通过 ctx 上报进度。返回统计结果。"""
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[int, int, str]] = asyncio.Queue()

        def progress(processed: int, total: int, current: str) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, (processed, total, current))

        async def drain() -> None:
            while True:
                processed, total, current = await queue.get()
                if ctx is not None:
                    await ctx.report(processed, total, current)

        drain_task = asyncio.create_task(drain())
        try:
            stats = await asyncio.to_thread(
                _sync_scan,
                library_id,
                full=full,
                extensions=self.extensions,
                ignore_names=self.ignore_names,
                audio=self.audio,
                progress=progress,
            )
        finally:
            await queue.put((0, 0, ""))  # 让 drain 退出
            drain_task.cancel()
            try:
                await drain_task
            except asyncio.CancelledError:
                pass
        return stats
