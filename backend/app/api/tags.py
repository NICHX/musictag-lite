"""标签批量编辑（F4）：预演（dry-run）与执行。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core.db import get_session, session_scope
from app.core.tasks import task_manager
from app.models.schemas import (
    BatchEditRequest,
    BatchPreviewResponse,
    FieldDiff,
    TaskAccepted,
    TrackDiff,
)
from app.services.tag_service import SOURCE_BATCH, TagService

router = APIRouter(prefix="/tracks", tags=["tags"])


@router.post("/batch/preview", response_model=BatchPreviewResponse)
def batch_preview(
    payload: BatchEditRequest, session: Session = Depends(get_session)
) -> BatchPreviewResponse:
    """dry-run：返回每个曲目的字段差异，不写盘。"""
    results = TagService().preview_batch(session, payload.ids, payload.ops, payload.strategy)
    items = [
        TrackDiff(
            track_id=item["track_id"],
            path=item["path"],
            changes=[FieldDiff(**change) for change in item["changes"]],
        )
        for item in results
    ]
    return BatchPreviewResponse(
        total=len(items),
        changed=sum(1 for item in items if item.changes),
        items=items,
    )


@router.post("/batch", response_model=TaskAccepted)
async def batch_edit(payload: BatchEditRequest) -> TaskAccepted:
    """批量写入标签（后台任务）。"""
    if payload.dry_run:
        raise HTTPException(status_code=400, detail="批量预演请使用 POST /tracks/batch/preview")

    service = TagService()

    async def runner(ctx) -> None:  # noqa: ANN001
        await ctx.set_total(len(payload.ids))

        def work() -> dict[str, int]:
            with session_scope() as session:
                return service.apply_batch(
                    session, payload.ids, payload.ops, payload.strategy, source=SOURCE_BATCH
                )

        stats = await asyncio.to_thread(work)
        await ctx.message(
            f"批量完成：修改 {stats['changed']} / 共 {stats['total']}，失败 {stats['failed']}"
        )

    task_id = await task_manager.run("batch_edit", runner, total=len(payload.ids))
    return TaskAccepted(task_id=task_id)
