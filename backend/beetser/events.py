"""A tiny in-process event bus used for server-sent events."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._version = 0
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def publish(self, topic: str = "change") -> None:
        """Thread-safe publish; may be called from worker threads."""
        if self._loop and not self._loop.is_closed():
            try:
                self._loop.call_soon_threadsafe(self._publish_now, topic)
                return
            except RuntimeError:  # pragma: no cover - loop shutting down
                pass
        self._publish_now(topic)

    def _publish_now(self, topic: str) -> None:
        self._version += 1
        payload = {"version": self._version, "topic": topic}
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:  # pragma: no cover - defensive
                pass

    @property
    def version(self) -> int:
        return self._version

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)
