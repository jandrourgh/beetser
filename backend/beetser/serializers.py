"""Plain-dict serialisers shared by the API routers."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

from .models import Activity, Job, Origin
from .utils import iso, loads


def origin_spec(origin: Origin) -> SimpleNamespace:
    """Detached snapshot of an origin, safe to use after the session closes."""
    return SimpleNamespace(
        id=origin.id,
        name=origin.name,
        path=origin.path,
        destination=origin.destination,
        effective_destination=origin.effective_destination,
        import_mode=origin.import_mode,
        path_format=origin.path_format,
        singleton_path_format=origin.singleton_path_format,
        auto_tag=origin.auto_tag,
        auto_tag_threshold=origin.auto_tag_threshold,
    )


def origin_out(
    origin: Origin,
    *,
    effective_mode: str,
    effective_auto_tag_threshold: float,
    job_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "id": origin.id,
        "name": origin.name,
        "path": origin.path,
        "destination": origin.effective_destination,
        "destination_is_default": origin.destination is None,
        "import_mode": origin.import_mode,
        "effective_import_mode": effective_mode,
        "path_format": origin.path_format,
        "singleton_path_format": origin.singleton_path_format,
        "auto_tag": origin.auto_tag,
        "auto_tag_threshold": origin.auto_tag_threshold,
        "effective_auto_tag_threshold": effective_auto_tag_threshold,
        "settled_seconds": origin.settled_seconds,
        "watch": origin.watch,
        "enabled": origin.enabled,
        "include_singletons": origin.include_singletons,
        "notes": origin.notes,
        "path_exists": os.path.isdir(origin.path),
        "created_at": iso(origin.created_at),
        "updated_at": iso(origin.updated_at),
        "last_scan_at": iso(origin.last_scan_at),
        "last_scan_status": origin.last_scan_status,
        "last_error": origin.last_error,
        "job_counts": job_counts or {},
    }


def job_out(
    job: Job, origin_name: str | None = None, *, compact: bool = False
) -> dict[str, Any]:
    files = loads(job.files_json, [])
    candidates = loads(job.candidates_json, [])
    duplicates = loads(job.duplicate_json, None)
    applied = loads(job.applied_fields_json, None) or {}
    cover = f"/api/jobs/{job.id}/candidates/0/cover" if candidates else None

    if compact:
        return {
            "id": job.id,
            "origin_id": job.origin_id,
            "origin_name": origin_name,
            "kind": job.kind,
            "source_dir": job.source_dir,
            "source_name": os.path.basename(job.source_dir.rstrip("/")) or job.source_dir,
            "state": job.state,
            "artist": job.artist,
            "album": job.album,
            "year": job.year,
            "track_count": job.track_count,
            "best_similarity": job.best_similarity,
            "recommendation": job.recommendation,
            "auto": job.auto,
            "files": [],
            "candidates": [],
            "candidate_count": len(candidates),
            "cover_url": cover,
            "duplicates": None,
            "duplicate_summary": job.duplicate_summary,
            "chosen_release_id": job.chosen_release_id,
            "chosen_source": job.chosen_source,
            "applied_fields": {},
            "applied_tracks": {},
            "library_album_id": job.library_album_id,
            "library_item_ids": [],
            "error": job.error,
            "log_tail": None,
            "created_at": iso(job.created_at),
            "updated_at": iso(job.updated_at),
            "started_at": iso(job.started_at),
            "finished_at": iso(job.finished_at),
        }

    return {
        "id": job.id,
        "origin_id": job.origin_id,
        "origin_name": origin_name,
        "kind": job.kind,
        "source_dir": job.source_dir,
        "source_name": os.path.basename(job.source_dir.rstrip("/")) or job.source_dir,
        "state": job.state,
        "artist": job.artist,
        "album": job.album,
        "year": job.year,
        "track_count": job.track_count,
        "best_similarity": job.best_similarity,
        "recommendation": job.recommendation,
        "auto": job.auto,
        "files": files,
        "candidates": candidates,
        "candidate_count": len(candidates),
        "cover_url": cover,
        "duplicates": duplicates,
        "duplicate_summary": job.duplicate_summary,
        "chosen_release_id": job.chosen_release_id,
        "chosen_source": job.chosen_source,
        "applied_fields": applied.get("fields") or {},
        "applied_tracks": applied.get("tracks") or {},
        "library_album_id": job.library_album_id,
        "library_item_ids": loads(job.library_item_ids, []),
        "error": job.error,
        "log_tail": job.log_tail,
        "created_at": iso(job.created_at),
        "updated_at": iso(job.updated_at),
        "started_at": iso(job.started_at),
        "finished_at": iso(job.finished_at),
    }


def activity_out(row: Activity, origin_name: str | None = None) -> dict[str, Any]:
    return {
        "id": row.id,
        "ts": iso(row.ts),
        "level": row.level,
        "category": row.category,
        "origin_id": row.origin_id,
        "origin_name": origin_name,
        "job_id": row.job_id,
        "message": row.message,
        "detail": loads(row.detail_json, None),
    }
