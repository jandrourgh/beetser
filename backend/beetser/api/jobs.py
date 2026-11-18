"""Review queue and import job endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select

from ..beets_engine import BeetsEngine
from ..db import Database
from ..jobs import ApplyPayload, ImportService, JobConflict
from ..models import Job, Origin
from ..schemas import ApplyRequest
from ..serializers import job_out
from ..utils import loads
from .deps import get_db, get_engine, get_service, require_auth

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_auth)])

REVIEW_STATES = ("needs_review", "duplicate", "failed")


def _origin_names(db: Database) -> dict[str, str]:
    with db.session() as session:
        rows = session.execute(select(Origin.id, Origin.name)).all()
    return {row[0]: row[1] for row in rows}


@router.get("")
def list_jobs(
    db: Database = Depends(get_db),
    state: str | None = Query(default=None),
    origin_id: str | None = None,
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=200),
) -> dict:
    filters = []
    if state == "review":
        filters.append(Job.state.in_(REVIEW_STATES))
    elif state == "active":
        filters.append(Job.state.in_(("discovered", "analyzing", "ready", "importing")))
    elif state and state != "all":
        filters.append(Job.state == state)
    if origin_id:
        filters.append(Job.origin_id == origin_id)
    if q:
        pattern = f"%{q}%"
        filters.append(
            (Job.album.ilike(pattern))
            | (Job.artist.ilike(pattern))
            | (Job.source_dir.ilike(pattern))
        )

    with db.session() as session:
        total = session.scalar(
            select(func.count(Job.id)).where(*filters)
        ) or 0
        rows = session.scalars(
            select(Job)
            .where(*filters)
            .order_by(Job.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        ).all()
        names = {r[0]: r[1] for r in session.execute(select(Origin.id, Origin.name)).all()}

    return {
        "jobs": [job_out(job, names.get(job.origin_id), compact=True) for job in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/stats")
def job_stats(db: Database = Depends(get_db)) -> dict:
    with db.session() as session:
        rows = session.execute(
            select(Job.state, func.count(Job.id)).group_by(Job.state)
        ).all()
    counts = {state: count for state, count in rows}
    return {
        "counts": counts,
        "review": sum(counts.get(s, 0) for s in REVIEW_STATES),
        "active": sum(
            counts.get(s, 0) for s in ("discovered", "analyzing", "ready", "importing")
        ),
        "total": sum(counts.values()),
    }


@router.get("/{job_id}")
def get_job(job_id: str, db: Database = Depends(get_db)) -> dict:
    with db.session() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        origin = session.get(Origin, job.origin_id)
        return job_out(job, origin.name if origin else None)


@router.get("/{job_id}/candidates/{index}/cover")
def candidate_cover(
    job_id: str,
    index: int,
    db: Database = Depends(get_db),
    engine: BeetsEngine = Depends(get_engine),
) -> Response:
    with db.session() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        candidates = loads(job.candidates_json, [])
    if index < 0 or index >= len(candidates):
        raise HTTPException(404, "Candidate not found")
    path = engine.candidate_cover(candidates[index].get("art_url"))
    if path is None:
        raise HTTPException(404, "No cover art")
    return FileResponse(
        path, headers={"Cache-Control": "public, max-age=604800, immutable"}
    )


@router.post("/{job_id}/apply")
def apply_job(
    job_id: str,
    payload: ApplyRequest,
    service: ImportService = Depends(get_service),
    db: Database = Depends(get_db),
) -> dict:
    apply_payload = ApplyPayload(
        mode=payload.mode,
        release_id=payload.release_id,
        fields=payload.fields,
        tracks=payload.tracks,
        force=payload.force,
    )
    try:
        service.apply(job_id, apply_payload)
    except KeyError:
        raise HTTPException(404, "Job not found") from None
    except JobConflict as exc:
        raise HTTPException(409, str(exc)) from None
    with db.session() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        origin = session.get(Origin, job.origin_id)
        return job_out(job, origin.name if origin else None)


@router.post("/{job_id}/skip")
def skip_job(job_id: str, service: ImportService = Depends(get_service)) -> dict:
    try:
        service.apply(job_id, ApplyPayload(mode="skip"))
    except KeyError:
        raise HTTPException(404, "Job not found") from None
    except JobConflict as exc:
        raise HTTPException(409, str(exc)) from None
    return {"ok": True}


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def forget_job(job_id: str, service: ImportService = Depends(get_service)) -> None:
    try:
        service.forget(job_id)
    except KeyError:
        raise HTTPException(404, "Job not found") from None
    except JobConflict as exc:
        raise HTTPException(409, str(exc)) from None
