"""任务中心：查询任务状态、取消任务（配合 WS 进度推送）。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.tasks import task_manager
from app.models.db import TaskStatus
from app.models.schemas import TaskRead

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskRead])
def list_tasks(limit: int = 50, status: str | None = None) -> list[TaskRead]:
    status_enum = TaskStatus(status) if status else None
    return [
        TaskRead.model_validate(task) for task in task_manager.list(limit=limit, status=status_enum)
    ]


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: int) -> TaskRead:
    task = task_manager.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return TaskRead.model_validate(task)


@router.post("/{task_id}/cancel", response_model=TaskRead)
async def cancel_task(task_id: int) -> TaskRead:
    task = task_manager.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    await task_manager.cancel(task_id)
    updated = task_manager.get(task_id)
    assert updated is not None
    return TaskRead.model_validate(updated)
