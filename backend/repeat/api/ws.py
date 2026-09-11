"""WebSocket fan-out of the event bus to the side panel and content scripts."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..deps import get_deps

log = logging.getLogger(__name__)
ws_router = APIRouter()


@ws_router.websocket("/ws")
async def events(ws: WebSocket):
    await ws.accept()
    bus = get_deps().bus
    q = bus.subscribe()
    await ws.send_json({"type": "hello", "payload": {"ok": True}})
    try:
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=20)
            except TimeoutError:
                await ws.send_json({"type": "ping", "payload": {}})
                continue
            await ws.send_json(event)
    except WebSocketDisconnect:
        pass
    except Exception as e:  # client vanished mid-send
        log.debug("ws closed: %s", e)
    finally:
        bus.unsubscribe(q)
