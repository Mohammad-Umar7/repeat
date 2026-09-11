"""In-process event bus. Agent nodes publish; the WebSocket route fans out to the panel
and the extension. Nothing leaves the machine."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger(__name__)


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self.history: list[dict[str, Any]] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    async def publish(self, type_: str, payload: dict[str, Any] | None = None) -> None:
        event = {"type": type_, "payload": payload or {}}
        self.history.append(event)
        if len(self.history) > 200:
            self.history = self.history[-200:]
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                log.warning("dropping slow subscriber")
                self._subscribers.discard(q)
