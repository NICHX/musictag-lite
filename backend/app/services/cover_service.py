"""封面服务：内嵌封面 + 同名文件兜底、替换、导出（F5）。M1 实现。"""

from __future__ import annotations

from pathlib import Path

from app.audio.base import CoverImage

_MILESTONE = "封面读写将在 M1 实现"

# 目录兜底封面候选文件名（按优先级）
SIDECAR_COVER_NAMES: tuple[str, ...] = (
    "cover.jpg",
    "cover.png",
    "folder.jpg",
    "folder.png",
    "front.jpg",
)


def find_sidecar_cover(directory: str | Path) -> Path | None:
    """在同目录下查找兜底封面文件（纯路径逻辑，M0 可用）。"""
    base = Path(directory)
    for name in SIDECAR_COVER_NAMES:
        candidate = base / name
        if candidate.is_file():
            return candidate
    return None


class CoverService:
    """封面读写与导出（M1 实现）。"""

    def read_cover(self, track_id: int) -> CoverImage | None:
        raise NotImplementedError(_MILESTONE)

    def write_cover(self, track_id: int, cover: CoverImage, *, kind: str = "front") -> None:
        raise NotImplementedError(_MILESTONE)

    def delete_cover(self, track_id: int) -> bool:
        raise NotImplementedError(_MILESTONE)

    def export(self, ids: list[int], target_dir: str | Path) -> list[Path]:
        raise NotImplementedError(_MILESTONE)
