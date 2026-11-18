"""Library browsing and editing endpoints.

Reads come straight from the central beets database. Writes go through the
beets CLI with a per-origin config so path formats and file moves stay
consistent with imports.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select

from ..beets_engine import BeetsEngine
from ..db import Database
from ..models import Origin
from ..schemas import AlbumUpdate
from .deps import get_db, get_engine, require_auth

router = APIRouter(
    prefix="/library", tags=["library"], dependencies=[Depends(require_auth)]
)


@router.get("/stats")
def library_stats(engine: BeetsEngine = Depends(get_engine)) -> dict:
    return engine.stats()


@router.get("/albums")
def list_albums(
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=30, ge=1, le=120),
    engine: BeetsEngine = Depends(get_engine),
) -> dict:
    try:
        return engine.albums(q, page, per_page)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.get("/singles")
def list_singles(
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    engine: BeetsEngine = Depends(get_engine),
) -> dict:
    return engine.singles(q, page, per_page)


@router.get("/albums/{album_id}")
def album_detail(
    album_id: int, engine: BeetsEngine = Depends(get_engine)
) -> dict:
    album = engine.album_detail(album_id)
    if album is None:
        raise HTTPException(404, "Album not found")
    return album


@router.patch("/albums/{album_id}")
def edit_album(
    album_id: int,
    payload: AlbumUpdate,
    db: Database = Depends(get_db),
    engine: BeetsEngine = Depends(get_engine),
) -> dict:
    if not payload.fields and not payload.tracks:
        raise HTTPException(400, "Nothing to update")
    if engine.album_detail(album_id) is None:
        raise HTTPException(404, "Album not found")

    origin = _origin_for_album(db, engine, album_id)
    result = engine.update_album(
        origin,
        album_id,
        fields=payload.fields,
        tracks=payload.tracks,
        write_tags=payload.write_tags,
        move_files=payload.move_files,
    )
    if not result.ok:
        raise HTTPException(
            400,
            {
                "message": result.error or "Update failed",
                "output": result.output,
                "warnings": result.warnings,
            },
        )
    return {
        "ok": True,
        "output": result.output,
        "warnings": result.warnings,
        "album": engine.album_detail(album_id),
    }


@router.get("/albums/{album_id}/cover")
def album_cover(
    album_id: int, engine: BeetsEngine = Depends(get_engine)
) -> Response:
    path = engine.cover_path(album_id)
    if path is None:
        raise HTTPException(404, "No cover art")
    return FileResponse(path, headers={"Cache-Control": "no-cache"})


@router.put("/albums/{album_id}/cover")
async def upload_album_cover(
    album_id: int,
    file: UploadFile = File(...),
    embed: bool | None = Form(default=None),
    engine: BeetsEngine = Depends(get_engine),
) -> dict:
    data = await file.read()
    try:
        artpath, warnings = engine.set_album_art(album_id, data, embed=embed)
    except KeyError:
        raise HTTPException(404, "Album not found") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return {
        "ok": True,
        "artpath": artpath,
        "warnings": warnings,
        "album": engine.album_detail(album_id),
    }


@router.delete("/albums/{album_id}/cover")
def delete_album_cover(
    album_id: int, engine: BeetsEngine = Depends(get_engine)
) -> dict:
    try:
        warnings = engine.clear_album_art(album_id)
    except KeyError:
        raise HTTPException(404, "Album not found") from None
    return {"ok": True, "warnings": warnings, "album": engine.album_detail(album_id)}


@router.post("/albums/{album_id}/cover/fetch")
def fetch_album_cover(
    album_id: int, engine: BeetsEngine = Depends(get_engine)
) -> dict:
    try:
        artpath, warnings = engine.fetch_album_art(album_id)
    except KeyError:
        raise HTTPException(404, "Album not found") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return {
        "ok": True,
        "artpath": artpath,
        "warnings": warnings,
        "album": engine.album_detail(album_id),
    }


def _origin_for_album(
    db: Database, engine: BeetsEngine, album_id: int
) -> SimpleNamespace | None:
    detail = engine.album_detail(album_id)
    if detail is None:
        return None
    paths = [track["path"] for track in detail["tracks"] if track.get("path")]

    with db.session() as session:
        origins = session.scalars(select(Origin)).all()
        flex_id = engine.album_origin_id(album_id)
        chosen = next((origin for origin in origins if origin.id == flex_id), None)

        if chosen is None:
            best_length = -1
            for origin in origins:
                destination = os.path.normpath(origin.effective_destination)
                for path in paths:
                    normalized = os.path.normpath(path)
                    if normalized != destination and not normalized.startswith(
                        destination + os.sep
                    ):
                        continue
                    if len(destination) > best_length:
                        best_length = len(destination)
                        chosen = origin

        if chosen is None:
            return None
        return SimpleNamespace(
            id=chosen.id,
            name=chosen.name,
            path=chosen.path,
            destination=chosen.destination,
            effective_destination=chosen.effective_destination,
            import_mode=chosen.import_mode,
            path_format=chosen.path_format,
            singleton_path_format=chosen.singleton_path_format,
            auto_tag=chosen.auto_tag,
            auto_tag_threshold=chosen.auto_tag_threshold,
        )
