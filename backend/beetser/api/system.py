"""System information, logs, directory browsing and live events."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from ..beets_engine import BeetsEngine
from ..events import EventBus
from ..jobs import ImportService
from ..logging_setup import log_snapshot
from ..security import AuthService
from ..utils import is_audio_file
from .deps import get_auth, get_bus, get_engine, get_service, require_auth

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
def health(engine: BeetsEngine = Depends(get_engine)) -> dict:
    return {"status": "ok", "library_exists": engine.library_exists()}


@router.get("/info", dependencies=[Depends(require_auth)])
def info(
    engine: BeetsEngine = Depends(get_engine),
    service: ImportService = Depends(get_service),
    auth: AuthService = Depends(get_auth),
) -> dict:
    data = engine.system_info()
    data.update(
        {
            "scan_interval": service.store.get_int("scan_interval_seconds", 300),
            "queues": {
                "jobs": service.job_queue.qsize(),
                "scans": service.scan_queue.qsize(),
            },
            "setup_required": auth.setup_required(),
        }
    )
    return data


@router.get("/logs", dependencies=[Depends(require_auth)])
def logs(after_id: int = 0, limit: int = Query(default=300, ge=1, le=1500)) -> dict:
    rows = log_snapshot(after_id=after_id, limit=limit)
    return {"logs": rows, "last_id": rows[-1]["id"] if rows else after_id}


@router.get("/browse", dependencies=[Depends(require_auth)])
def browse(path: str = "/") -> dict:
    target = Path(path)
    if not target.exists() or not target.is_dir():
        raise HTTPException(400, "Path is not a readable directory")
    try:
        entries = []
        for entry in sorted(target.iterdir(), key=lambda p: p.name.lower()):
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_dir():
                    entries.append({"name": entry.name, "path": str(entry), "type": "dir"})
                elif is_audio_file(entry):
                    entries.append({"name": entry.name, "path": str(entry), "type": "file"})
            except OSError:
                continue
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from None

    parent = str(target.parent) if target.parent != target else None
    return {
        "path": str(target),
        "parent": parent,
        "entries": entries[:500],
        "truncated": len(entries) > 500,
    }


@router.get("/events", dependencies=[Depends(require_auth)])
async def events(request: Request, bus: EventBus = Depends(get_bus)) -> StreamingResponse:
    async def stream():
        yield f"event: ready\ndata: {json.dumps({'version': bus.version})}\n\n"
        async with bus.subscribe() as queue:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"event: change\ndata: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
