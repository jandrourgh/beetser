"""Reorganizing library albums into their optimal folder layout.

Imports keep files where they are (``beet import -CMw``), so organizing is a
separate, explicit action. Because moving files invalidates the paths recorded
by the scanner, every organized album also gets its tracked paths refreshed.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy import select

from .beets_engine import BeetsEngine, OrganizeResult, file_sha256
from .db import Database
from .models import TrackedFile

log = logging.getLogger(__name__)


def organize_albums(
    db: Database, engine: BeetsEngine, origin: Any, album_ids: list[int]
) -> dict[str, Any]:
    """Organize albums and keep scanner state in sync with the new paths."""
    organized: list[int] = []
    failures: list[dict[str, Any]] = []
    for album_id in album_ids:
        result = engine.organize_album(origin, album_id)
        if not result.ok:
            failures.append(
                {"album_id": album_id, "error": result.error or "Organize failed"}
            )
            continue
        _sync_tracked_paths(db, origin.id, result)
        organized.append(album_id)

    return {
        "total": len(album_ids),
        "organized": len(organized),
        "failed": len(failures),
        "album_ids": organized,
        "failures": failures,
    }


def _sync_tracked_paths(
    db: Database, origin_id: str, result: OrganizeResult
) -> None:
    """Drop tracked rows for the old paths and track the new ones.

    Leaving the old rows behind would make a later download that reuses the
    same folder/file names look like an already-imported file.
    """
    before = set(result.before)
    after = set(result.after)
    if before == after:
        return

    with db.session() as session:
        stale = before - after
        if stale:
            rows = session.scalars(
                select(TrackedFile).where(
                    TrackedFile.origin_id == origin_id,
                    TrackedFile.path.in_(stale),
                )
            ).all()
            for row in rows:
                session.delete(row)

        for path in after:
            try:
                stat = os.stat(path)
            except OSError:
                continue
            row = session.get(TrackedFile, path)
            if row is None:
                session.add(
                    TrackedFile(
                        path=path,
                        origin_id=origin_id,
                        size=stat.st_size,
                        mtime=stat.st_mtime,
                        sha256=_sha256(path),
                        status="imported",
                    )
                )
            else:
                row.origin_id = origin_id
                row.status = "imported"
                row.size = stat.st_size
                row.mtime = stat.st_mtime


def _sha256(path: str) -> str | None:
    try:
        return file_sha256(path)
    except OSError:  # pragma: no cover - unreadable file
        return None
