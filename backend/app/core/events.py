"""事件总线：进程内发布/订阅，供 WebSocket 推送任务与进度事件。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

Event = dict[str, Any]


class EventBus:
    """极简进程内事件总线：多订阅者、非阻塞发布、慢消费者丢弃旧消息。"""

    def __init__(self, max_queue: int = 1000) -> None:
        self._queues: set[asyncio.Queue[Event]] = set()
        self._max_queue = max_queue

    def subscribe(self) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._max_queue)
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Event]) -> None:
        self._queues.discard(queue)

    async def publish(self, event: Event) -> None:
        """向所有订阅者投递事件；队列满则丢弃（进度类事件可容忍丢失）。"""
        for queue in list(self._queues):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()  # 丢弃最旧一条
                    queue.put_nowait(event)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass

    @property
    def subscriber_count(self) -> int:
        return len(self._queues)

    async def stream(self) -> AsyncIterator[Event]:
        """把订阅队列包装为异步迭代器，便于 WebSocket 消费。"""
        queue = self.subscribe()
        try:
            while True:
                yield await queue.get()
        finally:
            self.unsubscribe(queue)


# 全局单例
event_bus = EventBus()
