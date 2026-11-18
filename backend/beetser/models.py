"""SQLAlchemy models for Beetser's own state.

The beets library database is intentionally separate: it stays the single
source of truth for music metadata, while this database tracks origins,
import jobs, dedupe fingerprints and activity.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .utils import utcnow


def new_id() -> str:
    return uuid.uuid4().hex


JOB_STATES = {
    "discovered",  # waiting for analysis
    "analyzing",  # autotag lookup running
    "needs_review",  # cannot be applied without a human decision
    "ready",  # decision made, waiting to be imported
    "importing",  # beets is moving/copying files
    "imported",  # done
    "duplicate",  # blocked by duplicate protection (needs a decision)
    "skipped",  # dismissed by the user
    "failed",  # import or analysis error
}


class Setting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Origin(Base):
    __tablename__ = "origins"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    path: Mapped[str] = mapped_column(String(4096), nullable=False)
    destination: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    import_mode: Mapped[str] = mapped_column(String(16), default="inherit")
    path_format: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    singleton_path_format: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    auto_tag: Mapped[str] = mapped_column(String(16), default="inherit")
    auto_tag_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    settled_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    watch: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    include_singletons: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_scan_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    jobs: Mapped[list["Job"]] = relationship(back_populates="origin")

    @property
    def effective_destination(self) -> str:
        return self.destination or self.path


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    origin_id: Mapped[str] = mapped_column(ForeignKey("origins.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16), default="album")
    source_dir: Mapped[str] = mapped_column(String(4096), nullable=False)
    state: Mapped[str] = mapped_column(String(24), default="discovered", index=True)

    files_json: Mapped[str] = mapped_column(Text, default="[]")
    artist: Mapped[str | None] = mapped_column(String(512), nullable=True)
    album: Mapped[str | None] = mapped_column(String(512), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    track_count: Mapped[int] = mapped_column(Integer, default=0)
    best_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(String(16), nullable=True)
    candidates_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto: Mapped[bool] = mapped_column(Boolean, default=False)

    duplicate_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    duplicate_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    chosen_release_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chosen_source: Mapped[str | None] = mapped_column(String(24), nullable=True)
    applied_fields_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    library_album_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    library_item_ids: Mapped[str | None] = mapped_column(Text, nullable=True)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    log_tail: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    origin: Mapped[Origin] = relationship(back_populates="jobs")


Index("ix_jobs_origin_state", Job.origin_id, Job.state)


class TrackedFile(Base):
    """Every file Beetser has seen in an origin tree."""

    __tablename__ = "tracked_files"

    path: Mapped[str] = mapped_column(String(4096), primary_key=True)
    origin_id: Mapped[str] = mapped_column(
        ForeignKey("origins.id", ondelete="CASCADE"), index=True
    )
    size: Mapped[int] = mapped_column(Integer, default=0)
    mtime: Mapped[float] = mapped_column(Float, default=0.0)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    first_seen: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(default=utcnow)


class ImportedFingerprint(Base):
    """Content hashes of files that have already been imported."""

    __tablename__ = "imported_fingerprints"

    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    origin_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    path: Mapped[str] = mapped_column(String(4096), nullable=False)
    size: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Activity(Base):
    __tablename__ = "activity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    level: Mapped[str] = mapped_column(String(16), default="info")
    category: Mapped[str] = mapped_column(String(32), default="general", index=True)
    origin_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
