"""整理：按模板重命名/移动（F15，P1；F11 的「标签→文件名」分支）。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core.db import get_session, session_scope
from app.core.tasks import task_manager
from app.models.schemas import (
    OrganizeApplyRequest,
    OrganizePreviewRequest,
    OrganizePreviewResponse,
    TaskAccepted,
)
from app.services.organize_service import OrganizeService

router = APIRouter(prefix="/organize", tags=["organize"])


@router.post("/preview", response_model=OrganizePreviewResponse)
def preview(
    payload: OrganizePreviewRequest, session: Session = Depends(get_session)
) -> OrganizePreviewResponse:
    """dry-run：按模板列出 old → new 路径与冲突，不写盘。"""
    if not payload.ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    result = OrganizeService().preview(session, payload.ids, payload.template, move=payload.move)
    return OrganizePreviewResponse(**result)


@router.post("/apply", response_model=TaskAccepted)
async def apply(payload: OrganizeApplyRequest) -> TaskAccepted:
    """执行整理（后台任务）；``plan`` 非空时以用户确认的目标为准。"""
    if not payload.ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")

    service = OrganizeService()
    plan = [item.model_dump() for item in payload.plan] if payload.plan else None

    def work() -> dict:
        with session_scope() as session:
            return service.apply(
                session, payload.ids, payload.template, move=payload.move, plan=plan
            )

    async def runner(ctx) -> None:  # noqa: ANN001
        await ctx.set_total(len(payload.ids))
        stats = await asyncio.to_thread(work)
        await ctx.message(
            f"整理完成：成功 {stats['moved']} / 共 {stats['total']}，"
            f"跳过 {stats['skipped']}，失败 {stats['failed']}"
        )

    task_id = await task_manager.run("organize", runner, total=len(payload.ids))
    return TaskAccepted(task_id=task_id)
