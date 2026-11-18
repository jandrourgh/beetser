"""Activity log endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import delete, select

from ..db import Database
from ..models import Activity, Origin
from ..serializers import activity_out
from .deps import get_db, require_auth

router = APIRouter(
    prefix="/activity", tags=["activity"], dependencies=[Depends(require_auth)]
)


@router.get("")
def list_activity(
    db: Database = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=500),
    before_id: int | None = None,
    level: str | None = None,
    category: str | None = None,
    origin_id: str | None = None,
) -> dict:
    filters = []
    if before_id:
        filters.append(Activity.id < before_id)
    if level:
        filters.append(Activity.level == level)
    if category:
        filters.append(Activity.category == category)
    if origin_id:
        filters.append(Activity.origin_id == origin_id)

    with db.session() as session:
        rows = session.scalars(
            select(Activity)
            .where(*filters)
            .order_by(Activity.id.desc())
            .limit(limit)
        ).all()
        names = {r[0]: r[1] for r in session.execute(select(Origin.id, Origin.name)).all()}

    return {
        "activity": [activity_out(row, names.get(row.origin_id)) for row in rows],
        "next_before_id": rows[-1].id if rows else None,
    }


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def clear_activity(db: Database = Depends(get_db)) -> None:
    with db.session() as session:
        session.execute(delete(Activity))
