"""Filesystem scanning and album discovery."""

from __future__ import annotations

import fnmatch
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select

from .beets_engine import BeetsEngine, file_sha256
from .db import Database
from .models import ImportedFingerprint, Job, Origin, TrackedFile
from .settings_store import SettingsStore
from .utils import dumps, is_audio_file, loads, utcnow

log = logging.getLogger(__name__)

PENDING_STATES = ("discovered", "analyzing", "needs_review", "duplicate", "failed", "ready")


@dataclass
class ScanStats:
    origin_id: str
    files_seen: int = 0
    new_files: int = 0
    new_jobs: int = 0
    updated_jobs: int = 0
    duplicates: int = 0
    waiting: int = 0
    errors: list[str] | None = None
    job_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "origin_id": self.origin_id,
            "files_seen": self.files_seen,
            "new_files": self.new_files,
            "new_jobs": self.new_jobs,
            "updated_jobs": self.updated_jobs,
            "duplicates": self.duplicates,
            "waiting": self.waiting,
            "errors": self.errors or [],
        }


class Scanner:
    def __init__(self, db: Database, engine: BeetsEngine, store: SettingsStore):
        self.db = db
        self.engine = engine
        self.store = store

    def scan_origin(self, origin_id: str) -> ScanStats:
        stats = ScanStats(origin_id=origin_id, errors=[])
        with self.db.session() as session:
            origin = session.get(Origin, origin_id)
            if origin is None or not origin.enabled:
                return stats

            root = Path(origin.path)
            if not root.is_dir():
                origin.last_scan_at = utcnow()
                origin.last_scan_status = "missing"
                origin.last_error = f"Origin path does not exist: {origin.path}"
                stats.errors.append(origin.last_error)
                return stats

            try:
                self._scan(session, origin, root, stats)
                origin.last_scan_status = "ok"
                origin.last_error = None
            except Exception as exc:
                log.exception("Scan failed for origin %s", origin.name)
                origin.last_scan_status = "error"
                origin.last_error = str(exc)
                stats.errors.append(str(exc))
            finally:
                origin.last_scan_at = utcnow()
        return stats

    # ------------------------------------------------------------------

    def _scan(
        self, session, origin: Origin, root: Path, stats: ScanStats
    ) -> None:
        store = self.store
        settle_seconds = origin.settled_seconds
        if settle_seconds is None:
            settle_seconds = store.get_int("settle_seconds", 30)
        ignore_globs = store.get("ignore_globs") or []
        ignore_dirs = set(store.get("ignore_dirs") or [])
        include_singletons = bool(origin.include_singletons) and store.get_bool(
            "include_singletons", True
        )

        destination = Path(origin.effective_destination)
        prune_destination = destination != root and root in destination.parents

        library_paths = self.engine.library_paths()
        tracked = {
            row.path
            for row in session.scalars(
                select(TrackedFile).where(TrackedFile.origin_id == origin.id)
            ).all()
        }

        new_files: dict[Path, os.stat_result] = {}
        existing_paths: set[str] = set()

        for dirpath, dirnames, filenames in os.walk(root):
            current = Path(dirpath)
            kept = []
            for name in dirnames:
                if name.startswith(".") or name in ignore_dirs:
                    continue
                child = current / name
                if (child / ".beetser-ignore").exists():
                    continue
                if prune_destination and child == destination:
                    continue
                kept.append(name)
            dirnames[:] = kept

            for name in filenames:
                if not is_audio_file(name) or any(
                    fnmatch.fnmatch(name, pattern) for pattern in ignore_globs
                ):
                    continue
                path = current / name
                try:
                    stat = path.stat()
                except OSError:
                    continue
                if stat.st_size == 0 or not path.is_file():
                    continue
                if time.time() - max(stat.st_mtime, stat.st_ctime) < settle_seconds:
                    stats.waiting += 1
                    continue
                stats.files_seen += 1
                key = str(path)
                existing_paths.add(key)
                if key in library_paths or key in tracked:
                    continue
                new_files[path] = stat

        self._collect_garbage(session, origin, root, existing_paths)

        if not new_files:
            return

        groups: dict[Path, list[dict]] = defaultdict(list)
        for path, stat in new_files.items():
            entry = {
                "path": str(path),
                "name": path.name,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "sha256": self._hash(path, stats),
            }
            groups[path.parent].append(entry)

        for directory, entries in groups.items():
            entries.sort(key=lambda e: e["name"])
            stats.new_files += len(entries)

            if directory == root:
                if not include_singletons:
                    continue
                for entry in entries:
                    self._create_or_update(
                        session, origin, entry["path"], [entry], "singleton", stats
                    )
            else:
                self._create_or_update(
                    session, origin, str(directory), entries, "album", stats
                )

        self.engine.invalidate_library_cache()

    # ------------------------------------------------------------------

    def _create_or_update(
        self,
        session,
        origin: Origin,
        source_dir: str,
        entries: list[dict],
        kind: str,
        stats: ScanStats,
    ) -> None:
        state_filter = ("discovered", "needs_review", "duplicate", "failed")
        job = session.scalars(
            select(Job)
            .where(
                Job.origin_id == origin.id,
                Job.source_dir == source_dir,
                Job.state.in_(state_filter),
            )
            .order_by(Job.created_at.desc())
        ).first()

        if job is None:
            existing = session.scalars(
                select(Job).where(
                    Job.origin_id == origin.id,
                    Job.source_dir == source_dir,
                    Job.state.in_(("ready", "importing", "analyzing")),
                )
            ).first()
            if existing is not None:
                # Let the in-flight job finish; the next scan picks up the
                # remaining files.
                return

            job = Job(
                origin_id=origin.id,
                kind=kind,
                source_dir=source_dir,
                state="discovered",
                files_json=dumps(entries),
                track_count=len(entries),
            )
            session.add(job)
            session.flush()
            stats.new_jobs += 1
        else:
            if job.state == "analyzing":
                return
            current = loads(job.files_json, [])
            known = {entry.get("path") for entry in current}
            current.extend(e for e in entries if e["path"] not in known)
            current.sort(key=lambda e: e.get("name") or "")
            job.files_json = dumps(current)
            job.track_count = len(current)
            job.state = "discovered"
            job.error = None
            job.auto = False
            stats.updated_jobs += 1

        for entry in entries:
            tracked = session.get(TrackedFile, entry["path"])
            if tracked is None:
                session.add(
                    TrackedFile(
                        path=entry["path"],
                        origin_id=origin.id,
                        size=entry["size"],
                        mtime=entry["mtime"],
                        sha256=entry.get("sha256"),
                        status="pending",
                        job_id=job.id,
                    )
                )
            else:
                tracked.status = "pending"
                tracked.job_id = job.id
                tracked.sha256 = entry.get("sha256") or tracked.sha256

        # Exact-content duplicates never need a MusicBrainz lookup; surface
        # them immediately so the user can decide.
        hashes = [e["sha256"] for e in entries if e.get("sha256")]
        if hashes:
            duplicates = session.scalars(
                select(ImportedFingerprint).where(
                    ImportedFingerprint.sha256.in_(hashes)
                )
            ).all()
            if len(duplicates) >= len(entries):
                job.state = "duplicate"
                job.duplicate_json = dumps(
                    {
                        "exact": [
                            {
                                "kind": "exact",
                                "sha256": row.sha256,
                                "library_path": row.path,
                                "message": "This exact file has already been imported",
                            }
                            for row in duplicates
                        ],
                        "tracks": [],
                        "albums": [],
                        "blocking": True,
                        "summary": "All files were already imported previously",
                    }
                )
                job.duplicate_summary = "All files were already imported previously"
                stats.duplicates += 1
                session.flush()
                stats.job_ids.append(job.id)
                return

        session.flush()
        stats.job_ids.append(job.id)

    # ------------------------------------------------------------------

    def _collect_garbage(
        self, session, origin: Origin, root: Path, existing_paths: set[str]
    ) -> None:
        rows = session.scalars(
            select(TrackedFile).where(
                TrackedFile.origin_id == origin.id,
                TrackedFile.status == "pending",
            )
        ).all()
        removed_jobs: set[str] = set()
        for row in rows:
            if row.path not in existing_paths:
                if row.job_id:
                    removed_jobs.add(row.job_id)
                session.delete(row)

        for job_id in removed_jobs:
            job = session.get(Job, job_id)
            if job is None or job.state in ("importing", "imported", "skipped"):
                continue
            files = [
                f for f in loads(job.files_json, []) if Path(f.get("path", "")).exists()
            ]
            if not files:
                job.state = "skipped"
                job.error = "Files disappeared before they could be imported"
                job.finished_at = utcnow()
                job.track_count = 0

    @staticmethod
    def _hash(path: Path, stats: ScanStats) -> str | None:
        try:
            return file_sha256(str(path))
        except OSError as exc:
            stats.errors.append(f"Could not hash {path}: {exc}")
            return None


def prune_empty_dirs(folder: Path, stop: Path) -> None:
    """Remove empty directories from ``folder`` up to (but not including) ``stop``."""
    try:
        folder = folder.resolve()
        stop = stop.resolve()
    except OSError:
        return
    if stop not in folder.parents and folder != stop:
        return
    current = folder
    while current != stop and stop in current.parents:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent
