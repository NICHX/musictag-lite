"""操作日志写入（F9）：记录每次写入的字段、前后值与来源。"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session

from app.models.db import OperationLog


def _fmt(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def record(
    session: Session,
    *,
    track_id: int | None,
    action: str,
    field: str | None = None,
    old: Any = None,
    new: Any = None,
    source: str = "manual",
    result: str = "success",
) -> OperationLog:
    """追加一条操作日志（不提交，由调用方统一提交）。"""
    entry = OperationLog(
        track_id=track_id,
        action=action,
        field=field,
        old_value=_fmt(old),
        new_value=_fmt(new),
        source=str(source),
        result=str(result),
    )
    session.add(entry)
    return entry
