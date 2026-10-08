"""标签服务：读取/写入元数据，批量策略与变更预览（F2/F3/F4）。

M0 实现纯函数（标签状态判定、批量策略计算），文件读写与落库在 M1 完成。
"""

from __future__ import annotations

import re
from typing import Any

from app.audio.base import TagSet
from app.models.db import TagStatus
from app.models.schemas import BatchEditOp

_MILESTONE = "标签读写将在 M1 实现"


def compute_tag_status(tags: TagSet) -> TagStatus:
    """根据核心字段缺失情况判定标签状态（用于列表徽标与筛选）。

    规则：三者齐全 → OK；全部缺失 → MISSING_TAGS；
    否则按 title → artist → album 的优先级返回第一个缺失项。
    """
    missing = [bool(tags.title), bool(tags.artist), bool(tags.album)]
    if all(missing):
        return TagStatus.ok
    if not any(missing):
        return TagStatus.missing_tags
    if not tags.title:
        return TagStatus.missing_title
    if not tags.artist:
        return TagStatus.missing_artist
    if not tags.album:
        return TagStatus.missing_album
    return TagStatus.unknown


def _as_text(value: Any) -> str:
    return "" if value is None else str(value)


def apply_batch_ops(
    current: dict[str, Any],
    ops: list[BatchEditOp],
    strategy: str = "overwrite",
) -> dict[str, Any]:
    """在内存中计算批量编辑结果（供 diff 预演与落盘复用）。

    - current：当前字段值字典；
    - strategy：overwrite（覆盖）/ fill_empty（仅填空）/ append（追加）/ replace（查找替换）。
    返回新的字段字典（不修改入参）。
    """
    result = dict(current)

    for op in ops:
        field = op.field
        old = result.get(field)

        if op.op == "set":
            if strategy == "fill_empty":
                if old not in (None, ""):
                    continue
                result[field] = op.value
            elif strategy == "append":
                if old in (None, ""):
                    result[field] = op.value
                else:
                    result[field] = f"{old}{op.value}"
            else:  # overwrite
                result[field] = op.value

        elif op.op == "replace":
            find = op.find or ""
            repl = op.replace or ""
            if old in (None, "") or not find:
                continue
            text = _as_text(old)
            if op.use_regex:
                result[field] = re.sub(find, repl, text)
            else:
                result[field] = text.replace(find, repl)

        elif op.op == "fill_empty":
            if old in (None, ""):
                result[field] = op.value

    return result


def diff_fields(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    """对比前后值，产出生效的字段变更列表。"""
    changes: list[dict[str, Any]] = []
    for field, new_value in after.items():
        old_value = before.get(field)
        if old_value != new_value:
            changes.append({"field": field, "old_value": old_value, "new_value": new_value})
    return changes


class TagService:
    """标签读写与批量编辑（M1 落盘实现）。"""

    async def update_track(
        self, track_id: int, values: dict[str, Any], *, source: str = "manual"
    ) -> None:
        raise NotImplementedError(_MILESTONE)

    def preview_batch(
        self, ids: list[int], ops: list[BatchEditOp], strategy: str
    ) -> list[dict[str, Any]]:
        raise NotImplementedError(_MILESTONE)
