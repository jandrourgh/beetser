"""Logging configuration with an in-memory ring buffer for the UI."""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import datetime, timezone

MAX_LOG_LINES = 1500

_buffer: deque[dict] = deque(maxlen=MAX_LOG_LINES)
_lock = threading.Lock()
_counter = 0


class RingBufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        global _counter
        try:
            message = record.getMessage()
            if record.exc_info:
                message = f"{message}\n{logging.Formatter().formatException(record.exc_info)}"
            if record.name.startswith("uvicorn.access"):
                return
            with _lock:
                _counter += 1
                _buffer.append(
                    {
                        "id": _counter,
                        "ts": datetime.fromtimestamp(
                            record.created, tz=timezone.utc
                        ).isoformat(),
                        "level": record.levelname,
                        "logger": record.name,
                        "message": message,
                    }
                )
        except Exception:  # pragma: no cover - never break logging
            pass


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())

    if not any(isinstance(h, RingBufferHandler) for h in root.handlers):
        root.addHandler(RingBufferHandler())

    if not any(getattr(h, "_beetser_console", False) for h in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        )
        console._beetser_console = True  # type: ignore[attr-defined]
        root.addHandler(console)

    logging.getLogger("watchdog").setLevel("WARNING")
    logging.getLogger("httpx").setLevel("WARNING")


def log_snapshot(after_id: int = 0, limit: int = 500) -> list[dict]:
    with _lock:
        rows = [r for r in _buffer if r["id"] > after_id]
    if limit and len(rows) > limit:
        rows = rows[-limit:]
    return rows
