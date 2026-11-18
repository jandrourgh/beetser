"""Origin (watched folder) management."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from ..beets_engine import origin_mode
from ..db import Database
from ..events import EventBus
from ..jobs import ImportService
from ..models import Job, Origin, TrackedFile
from ..schemas import OriginCreate, OriginTestRequest, OriginUpdate
from ..serializers import origin_out
from ..settings_store import SettingsStore
from ..utils import is_audio_file
from .deps import get_bus, get_db, get_service, get_store, require_auth

router = APIRouter(prefix="/origins", tags=["origins"], dependencies=[Depends(require_auth)])
log = logging.getLogger(__name__)


def _is_nested(candidate: str, other: str) -> bool:
    candidate_path = Path(candidate).resolve()
    other_path = Path(other).resolve()
    return candidate_path == other_path or other_path in candidate_path.parents or candidate_path in other_path.parents


def _counts(db: Database) -> dict[str, dict[str, int]]:
    with db.session() as session:
        rows = session.execute(
            select(Job.origin_id, Job.state, func.count(Job.id)).group_by(
                Job.origin_id, Job.state
            )
        ).all()
    result: dict[str, dict[str, int]] = {}
    for origin_id, state, count in rows:
        result.setdefault(origin_id, {})[state] = count
    return result


def _serialize(origin: Origin, store: SettingsStore, counts: dict[str, int]) -> dict:
    return origin_out(
        origin,
        effective_mode=origin_mode(origin, store),
        effective_auto_tag_threshold=(
            origin.auto_tag_threshold
            if origin.auto_tag_threshold is not None
            else store.get_float("auto_tag_threshold", 0.85)
        ),
        job_counts=counts,
    )


@router.get("")
def list_origins(
    db: Database = Depends(get_db), store: SettingsStore = Depends(get_store)
) -> dict:
    with db.session() as session:
        origins = session.scalars(select(Origin).order_by(Origin.name)).all()
    counts = _counts(db)
    return {"origins": [_serialize(o, store, counts.get(o.id, {})) for o in origins]}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_origin(
    payload: OriginCreate,
    db: Database = Depends(get_db),
    store: SettingsStore = Depends(get_store),
    service: ImportService = Depends(get_service),
    bus: EventBus = Depends(get_bus),
) -> dict:
    path = Path(payload.path)
    if not path.is_dir():
        raise HTTPException(400, f"Origin path is not a directory: {payload.path}")
    destination = Path(payload.destination or payload.path)
    try:
        destination.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(400, f"Cannot create destination: {exc}") from exc

    with db.session() as session:
        for other in session.scalars(select(Origin)).all():
            if _is_nested(str(path), other.path):
                raise HTTPException(
                    409,
                    f"Path overlaps with origin '{other.name}' ({other.path}). "
                    "Nested origins would import the same files twice.",
                )
        origin = Origin(
            name=payload.name.strip(),
            path=str(path),
            destination=payload.destination,
            import_mode=payload.import_mode,
            path_format=payload.path_format or None,
            singleton_path_format=payload.singleton_path_format or None,
            auto_tag=payload.auto_tag,
            auto_tag_threshold=payload.auto_tag_threshold,
            settled_seconds=payload.settled_seconds,
            watch=payload.watch,
            enabled=payload.enabled,
            include_singletons=payload.include_singletons,
            notes=payload.notes,
        )
        session.add(origin)
        session.flush()
        serialized = _serialize(origin, store, {})

    service.refresh_watchers()
    service.request_scan(origin.id, delay=0.5)
    bus.publish("origins")
    return serialized


@router.get("/{origin_id}")
def get_origin(
    origin_id: str,
    db: Database = Depends(get_db),
    store: SettingsStore = Depends(get_store),
) -> dict:
    with db.session() as session:
        origin = session.get(Origin, origin_id)
        if origin is None:
            raise HTTPException(404, "Origin not found")
        serialized = _serialize(origin, store, _counts(db).get(origin_id, {}))
    return serialized


@router.patch("/{origin_id}")
def update_origin(
    origin_id: str,
    payload: OriginUpdate,
    db: Database = Depends(get_db),
    store: SettingsStore = Depends(get_store),
    service: ImportService = Depends(get_service),
    bus: EventBus = Depends(get_bus),
) -> dict:
    changes = payload.model_dump(exclude_unset=True)
    with db.session() as session:
        origin = session.get(Origin, origin_id)
        if origin is None:
            raise HTTPException(404, "Origin not found")

        if "path" in changes and changes["path"]:
            path = Path(changes["path"])
            if not path.is_dir():
                raise HTTPException(400, f"Origin path is not a directory: {path}")
            for other in session.scalars(
                select(Origin).where(Origin.id != origin_id)
            ).all():
                if _is_nested(str(path), other.path):
                    raise HTTPException(
                        409,
                        f"Path overlaps with origin '{other.name}' ({other.path})",
                    )

        if "destination" in changes and changes["destination"]:
            try:
                Path(changes["destination"]).mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise HTTPException(400, f"Cannot create destination: {exc}") from exc

        for key, value in changes.items():
            if key in ("path_format", "singleton_path_format", "notes") and value == "":
                value = None
            setattr(origin, key, value)

        session.flush()
        serialized = _serialize(origin, store, _counts(db).get(origin_id, {}))
        rescan = "path" in changes or "enabled" in changes or "watch" in changes

    service.refresh_watchers()
    if rescan:
        service.request_scan(origin_id, delay=0.5)
    bus.publish("origins")
    return serialized


@router.delete("/{origin_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_origin(
    origin_id: str,
    db: Database = Depends(get_db),
    service: ImportService = Depends(get_service),
    bus: EventBus = Depends(get_bus),
) -> None:
    with db.session() as session:
        origin = session.get(Origin, origin_id)
        if origin is None:
            raise HTTPException(404, "Origin not found")
        for job in session.scalars(select(Job).where(Job.origin_id == origin_id)).all():
            session.delete(job)
        for tracked in session.scalars(
            select(TrackedFile).where(TrackedFile.origin_id == origin_id)
        ).all():
            session.delete(tracked)
        session.delete(origin)
    service.refresh_watchers()
    bus.publish("origins")


@router.post("/{origin_id}/scan")
def scan_origin(
    origin_id: str,
    db: Database = Depends(get_db),
    service: ImportService = Depends(get_service),
) -> dict:
    with db.session() as session:
        if session.get(Origin, origin_id) is None:
            raise HTTPException(404, "Origin not found")
    service.request_scan(origin_id, delay=0)
    return {"queued": True}


@router.post("/{origin_id}/test")
def test_origin(
    origin_id: str,
    payload: OriginTestRequest,
    db: Database = Depends(get_db),
) -> dict:
    with db.session() as session:
        origin = session.get(Origin, origin_id)
        if origin is None:
            raise HTTPException(404, "Origin not found")
        path = Path(payload.path or origin.path)
        destination = Path(payload.destination or origin.effective_destination)

    result = {
        "path": str(path),
        "exists": path.is_dir(),
        "readable": os.access(path, os.R_OK) if path.exists() else False,
        "destination": str(destination),
        "destination_writable": _writable(destination),
        "audio_files": 0,
        "error": None,
    }
    if not path.is_dir():
        result["error"] = "Path does not exist or is not a directory"
        return result
    try:
        count = 0
        for _dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            count += sum(1 for name in filenames if is_audio_file(name))
            if count >= 5000:
                break
        result["audio_files"] = count
    except OSError as exc:
        result["error"] = str(exc)
    return result


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".beetser-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False
