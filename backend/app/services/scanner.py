"""扫描服务：遍历库根目录、增量识别、更新索引。

M0 提供可复用的纯函数（目录遍历、增量判定）；实际读取标签与写库在 M1 完成。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from app.audio.formats import ALLOWED_EXTENSIONS
from app.models.db import Track

_MILESTONE = "扫描落库将在 M1 实现"


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
        # 就地过滤隐藏目录，避免无谓下探
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if name.startswith(".") or name in ignore_names:
                continue
            suffix = Path(name).suffix.lower()
            if suffix in extensions:
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


class Scanner:
    """库扫描器（M1 落库实现）。"""

    def __init__(self, *, max_concurrency: int = 4) -> None:
        self.max_concurrency = max_concurrency

    async def scan_library(self, library_id: int, *, full: bool = False) -> int:
        """扫描指定库并返回受影响曲目数；返回 task_id 由 API 层包装。"""
        raise NotImplementedError(_MILESTONE)
