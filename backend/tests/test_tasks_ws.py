"""任务系统与 WebSocket 事件推送。"""

from __future__ import annotations

import asyncio


async def test_task_manager_lifecycle() -> None:
    from app.core.tasks import task_manager

    steps: list[str] = []

    async def runner(ctx) -> None:  # noqa: ANN001
        await ctx.set_total(3)
        for index in range(3):
            steps.append(f"step-{index}")
            await ctx.advance(current=f"/music/{index}.flac")

    task_id = await task_manager.run("scan", runner, total=3)
    await asyncio.sleep(0.1)

    task = task_manager.get(task_id)
    assert task is not None
    assert task.status == "succeeded"
    assert task.processed == 3
    assert task.total == 3
    assert len(steps) == 3


async def test_task_manager_failure() -> None:
    from app.core.tasks import task_manager

    async def runner(ctx) -> None:  # noqa: ANN001
        raise RuntimeError("boom")

    task_id = await task_manager.run("scrape", runner)
    await asyncio.sleep(0.1)
    task = task_manager.get(task_id)
    assert task is not None
    assert task.status == "failed"
    assert "boom" in (task.error or "")


def test_ws_events_hello(client) -> None:
    with client.websocket_connect("/ws/events") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "hello"


def test_tasks_api_empty(client) -> None:
    assert client.get("/api/tasks").status_code == 200
    assert client.get("/api/tasks/999999").status_code == 404
