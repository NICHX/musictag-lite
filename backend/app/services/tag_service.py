"""标签服务：读取/写入元数据，批量策略与变更预览（F2/F3/F4）。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sqlmodel import Session

from app.audio.base import AudioIO, TagSet
from app.audio.mutagen_io import audio_io
from app.models.db import LogResult, LogSource, TagStatus, Track, utcnow
from app.models.schemas import BatchEditOp
from app.services import oplog

# 可编辑字段（与 schemas.EDITABLE_FIELDS 对应）
EDITABLE_FIELDS: tuple[str, ...] = (
    "title",
    "artist",
    "album",
    "album_artist",
    "composer",
    "genre",
    "track_no",
    "disc_no",
    "year",
    "date",
    "comment",
)

_INT_FIELDS = {"track_no", "disc_no"}


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

    - ``set``  + strategy：overwrite 覆盖 / fill_empty 仅填空 / append 追加
    - ``replace``：按 find→replace 做普通或正则替换
    - ``fill_empty``：仅当当前为空时写入
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
                result[field] = op.value if old in (None, "") else f"{old}{op.value}"
            else:  # overwrite
                result[field] = op.value

        elif op.op == "replace":
            find = op.find or ""
            repl = op.replace or ""
            if old in (None, "") or not find:
                continue
            text = _as_text(old)
            result[field] = re.sub(find, repl, text) if op.use_regex else text.replace(find, repl)

        elif op.op == "fill_empty" and old in (None, ""):
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


def _normalize(field: str, value: Any) -> Any:
    """把请求值规整为入库值；``None`` / 空串表示清除。"""
    if value is None or value == "":
        return None
    if field in _INT_FIELDS:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return str(value)


def _tag_value(value: Any) -> str | None:
    """把入库值转换为 mutagen 写入语义：``""`` 表示清除，``None`` 表示不修改。"""
    return "" if value is None else str(value)


class TagService:
    """单条与批量标签写入。"""

    def __init__(self, audio: AudioIO | None = None) -> None:
        self.audio = audio or audio_io

    # ---- 单条 ----
    def apply_single(
        self,
        session: Session,
        track: Track,
        values: dict[str, Any],
        *,
        source: str = "manual",
    ) -> list[dict[str, Any]]:
        """写入单条曲目标签并记录日志；返回生效的字段差异。"""
        changes = self._compute_changes(track, values)
        if not changes:
            return []

        self.audio.write_tags(Path(track.path), self._build_tagset(changes))
        self._apply_to_track(track, changes)
        for field, old_value, new_value in changes:
            oplog.record(
                session,
                track_id=track.id,
                action="tag.edit",
                field=field,
                old=old_value,
                new=new_value,
                source=source,
            )
        session.add(track)
        session.commit()
        session.refresh(track)
        return [{"field": f, "old_value": o, "new_value": n} for f, o, n in changes]

    # ---- 批量 ----
    def preview_batch(
        self, session: Session, ids: list[int], ops: list[BatchEditOp], strategy: str
    ) -> list[dict[str, Any]]:
        """dry-run：返回每个曲目的字段差异。"""
        results: list[dict[str, Any]] = []
        for track in self._load_tracks(session, ids):
            before = {field: getattr(track, field) for field in EDITABLE_FIELDS}
            after = apply_batch_ops(before, ops, strategy)
            results.append(
                {
                    "track_id": track.id,
                    "path": track.path,
                    "changes": diff_fields(before, after),
                }
            )
        return results

    def apply_batch(
        self,
        session: Session,
        ids: list[int],
        ops: list[BatchEditOp],
        strategy: str,
        *,
        source: str = "batch",
    ) -> dict[str, int]:
        """批量写入；返回统计。"""
        stats = {"total": 0, "changed": 0, "failed": 0}
        for track in self._load_tracks(session, ids):
            stats["total"] += 1
            before = {field: getattr(track, field) for field in EDITABLE_FIELDS}
            after = apply_batch_ops(before, ops, strategy)
            changes = [
                (change["field"], change["old_value"], change["new_value"])
                for change in diff_fields(before, after)
            ]
            if not changes:
                continue
            try:
                self.audio.write_tags(Path(track.path), self._build_tagset(changes))
            except Exception:  # noqa: BLE001 - 单条失败不影响整批
                stats["failed"] += 1
                oplog.record(
                    session,
                    track_id=track.id,
                    action="tag.edit",
                    source=source,
                    result=str(LogResult.failure),
                )
                continue
            self._apply_to_track(track, changes)
            for field, old_value, new_value in changes:
                oplog.record(
                    session,
                    track_id=track.id,
                    action="tag.edit",
                    field=field,
                    old=old_value,
                    new=new_value,
                    source=source,
                )
            session.add(track)
            stats["changed"] += 1
        session.commit()
        return stats

    # ---- 内部 ----
    @staticmethod
    def _load_tracks(session: Session, ids: list[int]) -> list[Track]:
        return [track for track in (session.get(Track, track_id) for track_id in ids) if track]

    @staticmethod
    def _compute_changes(track: Track, values: dict[str, Any]) -> list[tuple[str, Any, Any]]:
        changes: list[tuple[str, Any, Any]] = []
        for field, raw in values.items():
            if field not in EDITABLE_FIELDS:
                continue
            new_value = _normalize(field, raw)
            if getattr(track, field) != new_value:
                changes.append((field, getattr(track, field), new_value))
        return changes

    @staticmethod
    def _build_tagset(changes: list[tuple[str, Any, Any]]) -> TagSet:
        tags = TagSet()
        for field, _old, new_value in changes:
            setattr(tags, field, _tag_value(new_value))
        return tags

    @staticmethod
    def _apply_to_track(track: Track, changes: list[tuple[str, Any, Any]]) -> None:
        for field, _old, new_value in changes:
            setattr(track, field, new_value)
            if field == "year":
                track.date = new_value
        track.tag_status = str(
            compute_tag_status(TagSet(title=track.title, artist=track.artist, album=track.album))
        )
        track.updated_at = utcnow()


# 供 API 层复用的来源常量
SOURCE_MANUAL = str(LogSource.manual)
SOURCE_BATCH = str(LogSource.batch)
SOURCE_SCRAPE = str(LogSource.scrape)
