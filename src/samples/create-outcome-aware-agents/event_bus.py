"""In-process pub/sub used to stream tool-call activity to SSE subscribers."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List


class EventBus:
    """Trivial fan-out async pub/sub.

    Each call to :meth:`subscribe` returns a fresh ``asyncio.Queue`` that
    receives every event published from then on. Callers (the SSE endpoint)
    drop the queue when the client disconnects.
    """

    def __init__(self) -> None:
        self._subscribers: List[asyncio.Queue[Dict[str, Any]]] = []
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue[Dict[str, Any]]:
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=256)
        async with self._lock:
            self._subscribers.append(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[Dict[str, Any]]) -> None:
        async with self._lock:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    async def publish(self, event: Dict[str, Any]) -> None:
        # Snapshot under lock, deliver outside to avoid back-pressure deadlocks.
        async with self._lock:
            targets = list(self._subscribers)
        for q in targets:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest, then re-push. Keeps slow clients from blocking.
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass


# Shared singleton — imported by tools and by the FastAPI app.
bus = EventBus()
