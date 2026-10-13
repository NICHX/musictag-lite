"""操作日志（F9）：查询每次写入的前后值与来源。"""

from __future__ import annotations

import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.core.db import get_session
from app.models.db import OperationLog
from app.models.schemas import OperationLogRead, Page

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("", response_model=Page[OperationLogRead])
def list_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    track_id: int | None = None,
    source: str | None = None,
    result: str | None = None,
    q: str | None = None,
    session: Session = Depends(get_session),
) -> Page[OperationLogRead]:
    filters = []
    if track_id is not None:
        filters.append(OperationLog.track_id == track_id)
    if source:
        filters.append(OperationLog.source == source)
    if result:
        filters.append(OperationLog.result == result)
    if q:
        like = f"%{q}%"
        filters.append(
            or_(
                OperationLog.action.like(like),
                OperationLog.field.like(like),
                OperationLog.old_value.like(like),
                OperationLog.new_value.like(like),
            )
        )

    statement = select(OperationLog)
    count_statement = select(func.count()).select_from(OperationLog)
    for condition in filters:
        statement = statement.where(condition)
        count_statement = count_statement.where(condition)

    statement = statement.order_by(OperationLog.created_at.desc(), OperationLog.id.desc())
    statement = statement.offset((page - 1) * page_size).limit(page_size)

    items = session.exec(statement).all()
    total = int(session.exec(count_statement).one())
    pages = max(1, math.ceil(total / page_size)) if total else 1
    return Page[OperationLogRead](
        items=[OperationLogRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )
