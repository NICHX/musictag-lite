"""进程内后台任务系统（P0）：任务落库 + 进度事件推送 + 取消。

设计说明：SQLite 为本地文件，写操作极快，这里直接同步写库以避免额外复杂度；
M1 若需要可平滑切换到线程池/独立执行器，接口保持不变。
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlmodel import Session, select

from app.core.db import engine
from app.core.events import EventBus, event_bus
from app.core.logging import get_logger
from app.models.db import Task, TaskStatus, TaskType

logger = get_logger(__name__)


class TaskContext:
    """传给任务协程的上下文：上报进度、检查取消。"""

    def __init__(self, manager: TaskManager, task_id: int) -> None:
        self._manager = manager
        self.task_id = task_id
        self._cancel_event = asyncio.Event()
        self._total = 0
        self._processed = 0

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def request_cancel(self) -> None:
        self._cancel_event.set()

    async def set_total(self, total: int) -> None:
        self._total = total
        await self._manager._emit_progress(self, status=TaskStatus.running)

    async def advance(self, step: int = 1, current: str | None = None) -> None:
        """推进进度并推送事件。"""
        self._processed += step
        await self._manager._emit_progress(self, current=current)

    async def report(self, processed: int, total: int, current: str | None = None) -> None:
        """以绝对数值上报进度（供线程内扫描等场景回调）。"""
        self._processed = processed
        self._total = total
        await self._manager._emit_progress(self, current=current)

    async def message(self, text: str) -> None:
        await self._manager._emit_progress(self, message=text)

    @property
    def progress(self) -> tuple[int, int]:
        return self._processed, self._total


TaskRunner = Callable[[TaskContext], Awaitable[None]]


class TaskManager:
    """管理后台任务的生命周期与事件广播。"""

    def __init__(self, bus: EventBus | None = None) -> None:
        self._bus = bus or event_bus
        self._contexts: dict[int, TaskContext] = {}
        self._asyncio_tasks: dict[int, asyncio.Task[None]] = {}

    # ---- 库操作 ----
    @staticmethod
    def _write_task(task_id: int, **fields: object) -> Task | None:
        with Session(engine) as session:
            task = session.get(Task, task_id)
            if task is None:
                return None
            for key, value in fields.items():
                setattr(task, key, value)
            session.add(task)
            session.commit()
            session.refresh(task)
            session.expunge(task)
            return task

    def create(self, type: TaskType | str, total: int = 0, message: str | None = None) -> int:
        """创建任务记录并返回 id。"""
        with Session(engine) as session:
            task = Task(
                type=str(type),
                status=TaskStatus.queued,
                total=total,
                processed=0,
                message=message,
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            assert task.id is not None
            task_id = task.id
        logger.info("task.created", extra={"task_id": task_id, "type": str(type)})
        return task_id

    def get(self, task_id: int) -> Task | None:
        with Session(engine) as session:
            return session.get(Task, task_id)

    def list(self, *, limit: int = 50, status: TaskStatus | None = None) -> list[Task]:
        with Session(engine) as session:
            statement = select(Task).order_by(Task.id.desc()).limit(limit)  # type: ignore[attr-defined]
            if status is not None:
                statement = statement.where(Task.status == str(status))
            return list(session.exec(statement).all())

    # ---- 事件 ----
    async def _emit_progress(
        self,
        ctx: TaskContext,
        *,
        status: TaskStatus | None = None,
        current: str | None = None,
        message: str | None = None,
    ) -> None:
        fields: dict[str, object] = {"processed": ctx._processed, "total": ctx._total}
        if status is not None:
            fields["status"] = str(status)
        if message is not None:
            fields["message"] = message
        task = self._write_task(ctx.task_id, **fields)
        await self._bus.publish(
            {
                "type": "task.progress",
                "task_id": ctx.task_id,
                "kind": task.type if task else None,
                "status": str(status) if status else (task.status if task else None),
                "processed": ctx._processed,
                "total": ctx._total,
                "current": current,
                "message": message,
            }
        )

    # ---- 执行 ----
    async def run(self, type: TaskType | str, runner: TaskRunner, total: int = 0) -> int:
        """创建并启动一个后台任务，返回 task_id（不阻塞调用方）。"""
        task_id = self.create(type, total=total)
        ctx = TaskContext(self, task_id)
        self._contexts[task_id] = ctx
        self._write_task(task_id, status=str(TaskStatus.running), started_at=datetime.now(UTC))
        await self._bus.publish(
            {
                "type": "task.started",
                "task_id": task_id,
                "kind": str(type),
                "status": str(TaskStatus.running),
            }
        )
        runner_task = asyncio.create_task(self._execute(ctx, runner))
        self._asyncio_tasks[task_id] = runner_task
        return task_id

    async def _execute(self, ctx: TaskContext, runner: TaskRunner) -> None:
        try:
            await runner(ctx)
        except asyncio.CancelledError:  # pragma: no cover - 由 cancel 触发
            self._finalize(ctx.task_id, TaskStatus.cancelled)
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("task.failed", extra={"task_id": ctx.task_id})
            self._finalize(ctx.task_id, TaskStatus.failed, error=str(exc))
        else:
            status = TaskStatus.cancelled if ctx.cancelled else TaskStatus.succeeded
            self._finalize(ctx.task_id, status)
        finally:
            self._contexts.pop(ctx.task_id, None)
            self._asyncio_tasks.pop(ctx.task_id, None)

    def _finalize(self, task_id: int, status: TaskStatus, error: str | None = None) -> None:
        self._write_task(task_id, status=str(status), error=error, finished_at=datetime.now(UTC))
        logger.info("task.finished", extra={"task_id": task_id, "status": str(status)})

    async def cancel(self, task_id: int) -> bool:
        ctx = self._contexts.get(task_id)
        if ctx is None:
            return False
        ctx.request_cancel()
        runner_task = self._asyncio_tasks.get(task_id)
        if runner_task is not None:
            runner_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await runner_task
        return True


# 全局单例
task_manager = TaskManager()
