"""Outbound notifications (generic webhook / Discord / ntfy compatible)."""

from __future__ import annotations

import asyncio
import logging

import httpx

from .settings_store import SettingsStore

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, store: SettingsStore):
        self.store = store
        self._loop: asyncio.AbstractEventLoop | None = None
        self._tasks: set[asyncio.Task] = set()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def notify(
        self, *, title: str, message: str, url: str | None = None, kind: str = "info"
    ) -> None:
        webhook = str(self.store.get("notify_webhook_url") or "").strip()
        if not webhook:
            return
        if self._loop and not self._loop.is_closed():
            try:
                self._loop.call_soon_threadsafe(
                    self._schedule, webhook, title, message, url, kind
                )
                return
            except RuntimeError:  # pragma: no cover
                pass
        self._schedule(webhook, title, message, url, kind)

    def _schedule(
        self,
        webhook: str,
        title: str,
        message: str,
        url: str | None,
        kind: str,
    ) -> None:
        try:
            task = asyncio.create_task(self._post(webhook, title, message, url, kind))
        except RuntimeError:  # pragma: no cover - no running loop
            return
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _post(
        self, webhook: str, title: str, message: str, url: str | None, kind: str
    ) -> None:
        payload = {
            "title": title,
            "message": message,
            "text": f"{title}\n{message}" if title else message,
            "content": f"**{title}**\n{message}" if title else message,
            "kind": kind,
            "url": url,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(webhook, json=payload)
        except Exception as exc:  # pragma: no cover - network errors
            log.warning("Webhook notification failed: %s", exc)
