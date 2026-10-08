"""实时事件：WebSocket /ws/events 推送任务与进度事件（§8.4 示例）。"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.events import event_bus
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/events")
async def ws_events(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = event_bus.subscribe()
    logger.info("ws.connected", extra={"subscribers": event_bus.subscriber_count})
    try:
        await websocket.send_json({"type": "hello", "subscribers": event_bus.subscriber_count})
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        event_bus.unsubscribe(queue)
        logger.info("ws.disconnected", extra={"subscribers": event_bus.subscriber_count})
