"""封面批量替换（F20）。

- ``preview``：仅凭图片**文件名**在「选中曲目」作用域内做优先级链匹配（不写盘）；
- ``apply``：按用户确认的指派把图片写为内嵌封面，复用 :class:`CoverService`。

匹配优先级：同名(stem) → 专辑模板 ``{专辑艺术家|艺术家} - {专辑}`` → 专辑名。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlmodel import Session

from app.audio.base import CoverImage
from app.models.db import LogSource, Track
from app.services.cover_service import CoverService

STATUS_OK = "ok"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_UNMATCHED = "unmatched"

SOURCE_BATCH = str(LogSource.batch)


def _stem(name: str) -> str:
    return Path(name).stem.casefold()


def album_label(track: Track) -> str | None:
    """专辑分组标签：``{专辑艺术家|艺术家} - {专辑}``。"""
    artist = track.album_artist or track.artist
    if artist and track.album:
        return f"{artist} - {track.album}"
    return None


class CoverBatchService:
    """封面批量匹配与写入。"""

    def preview(self, session: Session, ids: list[int], filenames: list[str]) -> dict[str, Any]:
        tracks = self._load(session, ids)

        by_stem: dict[str, list[Track]] = {}
        groups: dict[str, list[Track]] = {}
        for track in tracks:
            by_stem.setdefault(_stem(track.filename), []).append(track)
            label = album_label(track)
            if label:
                groups.setdefault(label, []).append(track)

        album_by_label = {label.casefold(): label for label in groups}
        album_only: dict[str, set[str]] = {}
        for label, group in groups.items():
            album = group[0].album
            if album:
                album_only.setdefault(album.casefold(), set()).add(label)

        matches: list[dict[str, Any]] = []
        for index, filename in enumerate(filenames):
            matches.append(
                self._match(index, filename, by_stem, album_by_label, album_only, groups)
            )

        return {
            "matches": matches,
            "albums": [
                {"label": label, "track_ids": [t.id for t in group]}
                for label, group in groups.items()
            ],
            "all_track_ids": [t.id for t in tracks],
        }

    def apply(self, session: Session, writes: list[dict[str, Any]]) -> dict[str, int]:
        """按指派写入内嵌封面；单首失败不影响整批。"""
        cover_service = CoverService()
        stats = {"total": 0, "written": 0, "failed": 0}
        for write in writes:
            track = session.get(Track, write["track_id"])
            if track is None:
                continue
            stats["total"] += 1
            cover = CoverImage(
                data=write["data"], mime=write["mime"], kind=write.get("kind", "front")
            )
            try:
                cover_service.write(session, track, cover, source=SOURCE_BATCH)
            except Exception:  # noqa: BLE001 - 单首失败不影响整批
                stats["failed"] += 1
                continue
            stats["written"] += 1
        return stats

    # ---- 内部 ----
    @staticmethod
    def _load(session: Session, ids: list[int]) -> list[Track]:
        return [track for track in (session.get(Track, track_id) for track_id in ids) if track]

    @staticmethod
    def _match(
        index: int,
        filename: str,
        by_stem: dict[str, list[Track]],
        album_by_label: dict[str, str],
        album_only: dict[str, set[str]],
        groups: dict[str, list[Track]],
    ) -> dict[str, Any]:
        stem = _stem(filename)
        base = {"index": index, "filename": filename}

        same_stem = by_stem.get(stem)
        if same_stem:
            ids = [t.id for t in same_stem]
            if len(same_stem) == 1:
                return {
                    **base,
                    "status": STATUS_OK,
                    "match": "stem",
                    "track_ids": ids,
                    "album": album_label(same_stem[0]),
                }
            return {**base, "status": STATUS_AMBIGUOUS, "match": "stem", "track_ids": ids}

        if stem in album_by_label:
            label = album_by_label[stem]
            return {
                **base,
                "status": STATUS_OK,
                "match": "album",
                "track_ids": [t.id for t in groups[label]],
                "album": label,
            }

        if stem in album_only:
            labels = album_only[stem]
            if len(labels) == 1:
                label = next(iter(labels))
                return {
                    **base,
                    "status": STATUS_OK,
                    "match": "album_name",
                    "track_ids": [t.id for t in groups[label]],
                    "album": label,
                }
            ids = [t.id for label in labels for t in groups[label]]
            return {**base, "status": STATUS_AMBIGUOUS, "match": "album_name", "track_ids": ids}

        return {**base, "status": STATUS_UNMATCHED, "match": None, "track_ids": []}
