"""Background worker: scans origins, analyses albums and runs imports."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select

from .beets_engine import BeetsEngine, ImportResult, origin_mode
from .db import Database
from .dedupe import build_report
from .events import EventBus
from .models import Activity, ImportedFingerprint, Job, Origin, TrackedFile
from .notify import Notifier
from .scanner import Scanner, prune_empty_dirs
from .settings import Settings
from .settings_store import SettingsStore
from .utils import dumps, loads, normalize_text, tail, utcnow

log = logging.getLogger(__name__)

AUDIO_SUFFIXES = {
    ".flac",
    ".mp3",
    ".m4a",
    ".ogg",
    ".opus",
    ".wav",
    ".aiff",
    ".wma",
    ".ape",
    ".wv",
    ".mp4",
    ".aac",
    ".alac",
    ".oga",
    ".mpc",
    ".m4b",
    ".m4p",
    ".aif",
}


class JobConflict(Exception):
    pass


class ApplyPayload:
    def __init__(
        self,
        mode: str,
        release_id: str | None = None,
        fields: dict[str, str] | None = None,
        tracks: dict[str, dict[str, Any]] | None = None,
        force: bool = False,
    ):
        self.mode = mode
        self.release_id = release_id
        self.fields = fields or {}
        self.tracks = tracks or {}
        self.force = force


class ImportService:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        store: SettingsStore,
        engine: BeetsEngine,
        bus: EventBus,
        notifier: Notifier,
    ):
        self.settings = settings
        self.db = db
        self.store = store
        self.engine = engine
        self.bus = bus
        self.notifier = notifier

        self.job_queue: asyncio.Queue[str] = asyncio.Queue()
        self.scan_queue: asyncio.Queue[str | None] = asyncio.Queue()
        self.scanner = Scanner(db, engine, store)

        self._loop: asyncio.AbstractEventLoop | None = None
        self._tasks: list[asyncio.Task] = []
        self._observer = None
        self._watches: dict[str, Any] = {}
        self._last_event: dict[str, float] = {}
        self._queued_jobs: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self.bus.bind_loop(self._loop)
        self.notifier.bind_loop(self._loop)
        await asyncio.to_thread(self._prepare_engine)
        self._recover_jobs()
        self._tasks = [
            asyncio.create_task(self._job_worker(), name="beetser-jobs"),
            asyncio.create_task(self._scan_worker(), name="beetser-scans"),
            asyncio.create_task(self._periodic_scanner(), name="beetser-periodic"),
        ]
        self.refresh_watchers()
        # Catch files that arrived while the container was stopped.
        self.request_scan(None, delay=1.0)
        log.info("Background workers started")

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=3)
            except Exception:  # pragma: no cover
                pass
        self._tasks.clear()

    def _prepare_engine(self) -> None:
        try:
            self.engine.prepare()
            self.engine.ensure_library()
        except Exception:  # pragma: no cover - startup diagnostics
            log.exception("Could not initialise the beets library")

    def _recover_jobs(self) -> None:
        with self.db.session() as session:
            jobs = session.scalars(select(Job)).all()
            requeue: list[str] = []
            for job in jobs:
                if job.state in ("discovered", "analyzing", "ready"):
                    if job.state == "analyzing":
                        job.state = "discovered"
                    requeue.append(job.id)
                elif job.state == "importing":
                    job.state = "failed"
                    job.error = "Import was interrupted by a restart"
                    job.finished_at = utcnow()
        for job_id in requeue:
            self.enqueue_job(job_id)

    # ------------------------------------------------------------------
    # Queue helpers
    # ------------------------------------------------------------------

    def enqueue_job(self, job_id: str) -> None:
        if not self._loop or self._loop.is_closed():
            return
        if job_id in self._queued_jobs:
            return
        self._queued_jobs.add(job_id)
        self._loop.call_soon_threadsafe(self.job_queue.put_nowait, job_id)

    def request_scan(self, origin_id: str | None = None, delay: float = 2.0) -> None:
        if not self._loop or self._loop.is_closed():
            return
        self._loop.call_soon_threadsafe(
            self._loop.call_later, delay, self.scan_queue.put_nowait, origin_id
        )

    # ------------------------------------------------------------------
    # Workers
    # ------------------------------------------------------------------

    async def _job_worker(self) -> None:
        while True:
            job_id = await self.job_queue.get()
            self._queued_jobs.discard(job_id)
            try:
                await asyncio.to_thread(self._process_job, job_id)
            except Exception:
                log.exception("Unhandled error while processing job %s", job_id)
            finally:
                self.job_queue.task_done()
                self.bus.publish("jobs")

    async def _scan_worker(self) -> None:
        while True:
            origin_id = await self.scan_queue.get()
            try:
                await asyncio.to_thread(self._run_scan, origin_id)
            except Exception:
                log.exception("Unhandled error while scanning %s", origin_id)
            finally:
                self.scan_queue.task_done()
                self.bus.publish("scan")

    async def _periodic_scanner(self) -> None:
        while True:
            interval = max(10, self.store.get_int("scan_interval_seconds", 300))
            await asyncio.sleep(interval)
            self.request_scan(None, delay=0)

    def _run_scan(self, origin_id: str | None) -> None:
        if origin_id is None:
            with self.db.session() as session:
                ids = [
                    o.id
                    for o in session.scalars(
                        select(Origin).where(Origin.enabled.is_(True))
                    ).all()
                ]
        else:
            ids = [origin_id]

        for oid in ids:
            stats = self.scanner.scan_origin(oid)
            for job_id in stats.job_ids:
                self.enqueue_job(job_id)
            if stats.waiting:
                settle = self._settle_seconds(oid)
                self.request_scan(oid, delay=max(5, settle + 2))
            if stats.new_files:
                self._activity(
                    "info",
                    "scan",
                    f"Found {stats.new_files} new file(s) in {self._origin_name(oid)}"
                    + (f" ({stats.new_jobs} new job(s))" if stats.new_jobs else ""),
                    origin_id=oid,
                    detail=stats.as_dict(),
                )

    def _settle_seconds(self, origin_id: str) -> int:
        with self.db.session() as session:
            origin = session.get(Origin, origin_id)
            if origin and origin.settled_seconds is not None:
                return int(origin.settled_seconds)
        return self.store.get_int("settle_seconds", 30)

    def _origin_name(self, origin_id: str) -> str:
        with self.db.session() as session:
            origin = session.get(Origin, origin_id)
            return origin.name if origin else origin_id

    # ------------------------------------------------------------------
    # Job processing
    # ------------------------------------------------------------------

    def _process_job(self, job_id: str) -> None:
        with self.db.session() as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            state = job.state
        if state == "discovered":
            self._analyze(job_id)
        elif state == "ready":
            self._import(job_id)

    # -- analysis ------------------------------------------------------

    def _analyze(self, job_id: str) -> None:
        with self.db.session() as session:
            job = session.get(Job, job_id)
            if job is None or job.state != "discovered":
                return
            files = loads(job.files_json, [])
            paths = [f["path"] for f in files if f.get("path")]
            job.state = "analyzing"
            job.started_at = utcnow()
            job.error = None
            session.commit()

        if not paths:
            self._set_needs_review(job_id, "No files left to analyse")
            return

        try:
            result = self.engine.analyze(paths)
        except Exception as exc:
            log.exception("Analysis crashed for job %s", job_id)
            self._set_failed(job_id, f"Analysis failed: {exc}")
            return

        with self.db.session() as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            origin = session.get(Origin, job.origin_id)
            if origin is None:
                job.state = "failed"
                job.error = "Origin was deleted"
                return

            files = loads(job.files_json, [])
            by_path = {f.path: f for f in result.files}
            for entry in files:
                info = by_path.get(entry.get("path"))
                if info is None:
                    continue
                entry.update(
                    {
                        "artist": info.artist,
                        "album": info.album,
                        "albumartist": info.albumartist,
                        "title": info.title,
                        "track": info.track,
                        "disc": info.disc,
                        "length": info.length,
                        "year": info.year,
                        "format": info.format,
                    }
                )
            job.files_json = dumps(files)

            candidates = list(result.candidates)
            job.candidates_json = dumps([asdict(c) for c in candidates])
            job.recommendation = result.recommendation
            job.best_similarity = result.best_similarity
            job.track_count = len(files)
            job.error = result.error

            albumartist, album, year = _majority_tags(files, candidates)
            job.artist = albumartist
            job.album = album
            job.year = year

            best = candidates[0] if candidates else None
            library_mbids = self.engine.album_mbids()
            report = build_report(
                self.engine,
                session,
                files=files,
                albumartist=(best.albumartist if best and best.albumartist else albumartist),
                album=(best.album if best and best.album else album),
                release_id=best.album_id if best else None,
                library_mbids=library_mbids,
            )
            job.duplicate_json = dumps(report.as_dict())
            job.duplicate_summary = report.summary()

            if report.blocking:
                job.state = "duplicate"
                job.auto = False
                session.commit()
                self._activity(
                    "warning",
                    "duplicate",
                    f"Possible duplicate: {job.artist or 'Unknown'} - "
                    f"{job.album or 'Unknown'}",
                    origin_id=origin.id,
                    job_id=job.id,
                    detail=report.as_dict(),
                )
                self._notify_review(origin, job, duplicate=True)
                return

            if not candidates:
                job.state = "needs_review"
                self._finish_analysis(session, job, origin)
                return

            if self._should_auto_import(origin, candidates):
                job.state = "ready"
                job.auto = True
                job.chosen_release_id = best.album_id
                job.chosen_source = "musicbrainz"
                session.commit()
                self._activity(
                    "info",
                    "import",
                    f"Auto-importing {best.albumartist} - {best.album} "
                    f"({best.similarity * 100:.0f}% match)",
                    origin_id=origin.id,
                    job_id=job.id,
                )
                self.enqueue_job(job.id)
                return

            job.state = "needs_review"
            job.auto = False
            self._finish_analysis(session, job, origin)

    def _set_failed(self, job_id: str, message: str) -> None:
        with self.db.session() as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            job.state = "failed"
            job.error = message
            job.finished_at = utcnow()

    def _set_needs_review(self, job_id: str, message: str) -> None:
        with self.db.session() as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            job.state = "needs_review"
            job.error = message
            job.finished_at = None

    def _finish_analysis(self, session, job: Job, origin: Origin) -> None:
        job.finished_at = None
        job_id, origin_id = job.id, origin.id
        artist, album = job.artist, job.album
        source_dir = job.source_dir
        score = job.best_similarity
        origin_name = origin.name
        session.commit()

        reason = f" ({score * 100:.0f}% best match)" if score is not None else ""
        self._activity(
            "info",
            "review",
            f"Needs review: {artist or 'Unknown artist'} - "
            f"{album or os.path.basename(source_dir)}{reason}",
            origin_id=origin_id,
            job_id=job_id,
        )
        self._notify_review_text(origin_name, artist, album)

    def _should_auto_import(self, origin: Origin, candidates: list[Any]) -> bool:
        if origin.auto_tag == "disabled":
            return False
        if not self.store.get_bool("auto_tag_enabled", True):
            return False

        best = candidates[0]
        threshold = (
            origin.auto_tag_threshold
            if origin.auto_tag_threshold is not None
            else self.store.get_float("auto_tag_threshold", 0.85)
        )
        if best.similarity < threshold:
            return False
        if best.missing_tracks or best.extra_items:
            return False
        if not best.album_id:
            return False
        if best.album_id in self.engine.album_mbids():
            return False

        gap = self.store.get_float("auto_tag_min_gap", 0.03)
        for other in candidates[1:]:
            if best.similarity - other.similarity >= gap:
                break
            same_release = (
                normalize_text(other.album) == normalize_text(best.album)
                and normalize_text(other.albumartist)
                == normalize_text(best.albumartist)
            )
            if not same_release:
                return False
        return True

    # -- import --------------------------------------------------------

    def _import(self, job_id: str) -> None:
        with self.db.session() as session:
            job = session.get(Job, job_id)
            if job is None or job.state != "ready":
                return
            origin = session.get(Origin, job.origin_id)
            if origin is None:
                job.state = "failed"
                job.error = "Origin was deleted"
                return
            spec = _origin_spec(origin)
            files = loads(job.files_json, [])
            applied = loads(job.applied_fields_json, {}) or {}
            kind = job.kind
            chosen_source = job.chosen_source
            release_id = job.chosen_release_id
            folder = job.source_dir
            job.state = "importing"
            job.started_at = utcnow()
            session.commit()

        set_fields = {str(k): str(v) for k, v in (applied.get("fields") or {}).items()}
        track_tags: dict[str, dict[str, Any]] = {}
        if chosen_source == "manual":
            raw_tracks = applied.get("tracks") or {}
            for entry in files:
                path = entry.get("path")
                if not path:
                    continue
                merged = dict(set_fields)
                merged.update(raw_tracks.get(path) or {})
                track_tags[path] = merged

        try:
            result = self.engine.import_files(
                spec,
                folder=folder,
                kind=kind,
                release_id=release_id,
                asis=chosen_source in ("asis", "manual") or not release_id,
                set_fields=set_fields,
                track_tags=track_tags,
            )
        except Exception as exc:
            log.exception("Import crashed for job %s", job_id)
            result = ImportResult(
                ok=False, returncode=-1, output="", reason=f"Import failed: {exc}"
            )

        if result.ok:
            self._finalize_success(job_id, origin.id, result, files, spec, kind)
        else:
            self._finalize_failure(job_id, result)

    def _finalize_success(
        self,
        job_id: str,
        origin_id: str,
        result: ImportResult,
        files: list[dict],
        origin: SimpleNamespace,
        kind: str,
    ) -> None:
        with self.db.session() as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            artist, album, auto = job.artist, job.album, job.auto
            source_dir = job.source_dir
            job.state = "imported"
            job.finished_at = utcnow()
            job.error = None
            job.log_tail = result.output
            job.library_album_id = next(
                (item["album_id"] for item in result.new_items if item.get("album_id")),
                None,
            )
            job.library_item_ids = dumps([item["id"] for item in result.new_items])
            job.track_count = len(result.new_items) or job.track_count

            mode = origin_mode(origin, self.store)
            old_paths = [entry.get("path") for entry in files if entry.get("path")]
            for path in old_paths:
                tracked = session.get(TrackedFile, path)
                if tracked is None:
                    continue
                if mode == "copy":
                    # The originals stay in the origin; keep them tracked so a
                    # rescan does not queue them as new files again.
                    tracked.status = "imported"
                    tracked.job_id = job_id
                else:
                    session.delete(tracked)

            from .beets_engine import file_sha256

            for item in result.new_items:
                path = item["path"]
                try:
                    sha = file_sha256(path)
                except OSError:
                    sha = None
                session.add(
                    TrackedFile(
                        path=path,
                        origin_id=origin_id,
                        size=os.path.getsize(path) if os.path.exists(path) else 0,
                        mtime=os.path.getmtime(path) if os.path.exists(path) else 0,
                        sha256=sha,
                        status="imported",
                        job_id=job_id,
                    )
                )
                if sha:
                    session.merge(
                        ImportedFingerprint(
                            sha256=sha,
                            origin_id=origin_id,
                            job_id=job_id,
                            path=path,
                            size=0,
                        )
                    )

            self.engine.invalidate_library_cache()

        if (
            kind == "album"
            and mode == "move"
            and self.store.get_bool("delete_empty_dirs", True)
        ):
            prune_empty_dirs(Path(source_dir), Path(origin.path))

        self._activity(
            "success",
            "import",
            f"Imported {artist or 'Unknown'} - {album or 'Unknown'} "
            f"({len(result.new_items)} track(s))",
            origin_id=origin_id,
            job_id=job_id,
        )
        if auto and self.store.get_bool("notify_on_import", False):
            self.notifier.notify(
                title="Album imported",
                message=f"{artist} - {album}",
                kind="success",
            )

    def _finalize_failure(self, job_id: str, result: ImportResult) -> None:
        with self.db.session() as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            job.state = "failed"
            job.finished_at = utcnow()
            job.error = result.reason or "Import failed"
            job.log_tail = tail(result.output or "", 8000)
            origin_id = job.origin_id
            artist, album = job.artist, job.album

        self._activity(
            "error",
            "import",
            f"Import failed for {artist or 'Unknown'} - {album or 'Unknown'}: "
            f"{result.reason or 'unknown error'}",
            origin_id=origin_id,
            job_id=job_id,
        )
        if self.store.get_bool("notify_on_error", True):
            self.notifier.notify(
                title="Import failed",
                message=f"{artist or 'Unknown'} - {album or 'Unknown'}: "
                f"{result.reason or 'unknown error'}",
                kind="error",
            )

    # ------------------------------------------------------------------
    # User actions
    # ------------------------------------------------------------------

    def apply(self, job_id: str, payload: ApplyPayload) -> None:
        if payload.mode == "skip":
            self._skip(job_id)
            self.bus.publish("jobs")
            return

        with self.db.session() as session:
            job = session.get(Job, job_id)
            if job is None:
                raise KeyError(job_id)
            if job.state in ("importing", "imported"):
                raise JobConflict(f"Job is {job.state} and cannot be changed")
            if (
                job.state == "duplicate"
                and payload.mode in ("candidate", "asis", "manual")
                and not payload.force
            ):
                raise JobConflict("Duplicate must be confirmed before importing")
            if payload.mode not in {"candidate", "asis", "manual", "reanalyze", "retry"}:
                raise JobConflict(f"Unsupported mode: {payload.mode}")

            if payload.mode in ("reanalyze", "retry"):
                job.state = "discovered"
                job.error = None
                job.started_at = None
                job.finished_at = None
                job.candidates_json = None
                job.duplicate_json = None
                job.duplicate_summary = None
                for entry in loads(job.files_json, []):
                    tracked = session.get(TrackedFile, entry.get("path"))
                    if tracked is not None:
                        tracked.status = "pending"
            elif payload.mode == "candidate":
                if not payload.release_id:
                    raise JobConflict("A release id is required")
                candidates = loads(job.candidates_json, [])
                known_ids = {c.get("album_id") for c in candidates}
                if known_ids and payload.release_id not in known_ids:
                    raise JobConflict("Unknown release id for this job")
                job.chosen_release_id = payload.release_id
                job.chosen_source = "musicbrainz"
                job.applied_fields_json = dumps({"fields": payload.fields})
                job.state = "ready"
                job.auto = False
                job.finished_at = None
            elif payload.mode == "asis":
                job.chosen_release_id = None
                job.chosen_source = "asis"
                job.applied_fields_json = dumps({"fields": payload.fields})
                job.state = "ready"
                job.auto = False
                job.finished_at = None
            elif payload.mode == "manual":
                job.chosen_release_id = None
                job.chosen_source = "manual"
                job.applied_fields_json = dumps(
                    {"fields": payload.fields, "tracks": payload.tracks}
                )
                job.state = "ready"
                job.auto = False
                job.finished_at = None
            job_id = job.id

        self.enqueue_job(job_id)
        self.bus.publish("jobs")

    def _skip(self, job_id: str) -> None:
        with self.db.session() as session:
            job = session.get(Job, job_id)
            if job is None:
                raise KeyError(job_id)
            job.state = "skipped"
            job.finished_at = utcnow()
            for entry in loads(job.files_json, []):
                tracked = session.get(TrackedFile, entry.get("path"))
                if tracked is not None:
                    tracked.status = "skipped"

    def forget(self, job_id: str) -> None:
        with self.db.session() as session:
            job = session.get(Job, job_id)
            if job is None:
                raise KeyError(job_id)
            if job.state == "importing":
                raise JobConflict("Cannot forget a job while it is importing")
            for entry in loads(job.files_json, []):
                tracked = session.get(TrackedFile, entry.get("path"))
                if tracked is not None:
                    session.delete(tracked)
            session.delete(job)

    def get(self, job_id: str) -> Job:
        with self.db.session() as session:
            job = session.get(Job, job_id)
            if job is None:
                raise KeyError(job_id)
            return job

    # ------------------------------------------------------------------
    # Watchers
    # ------------------------------------------------------------------

    def refresh_watchers(self) -> None:
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except Exception:  # pragma: no cover
            log.warning("watchdog is unavailable; falling back to periodic scans")
            return

        with self.db.session() as session:
            origins = session.scalars(
                select(Origin).where(Origin.enabled.is_(True), Origin.watch.is_(True))
            ).all()
            desired = {o.id: o.path for o in origins}
            destinations = {o.id: o.effective_destination for o in origins}

        if self._observer is None:
            self._observer = Observer()
            self._observer.daemon = True
            self._observer.start()

        for origin_id in list(self._watches):
            if origin_id not in desired:
                watch, _path = self._watches.pop(origin_id)
                try:
                    self._observer.unschedule(watch)
                except Exception:
                    pass

        service = self

        class _Handler(FileSystemEventHandler):
            def __init__(self, oid: str, ignored_prefix: str | None):
                self.oid = oid
                self.ignored_prefix = ignored_prefix

            def on_any_event(self, event):  # type: ignore[no-untyped-def]
                if event.event_type in ("opened", "closed_no_write", "closed"):
                    return
                path = getattr(event, "dest_path", "") or getattr(event, "src_path", "") or ""
                if self.ignored_prefix and (
                    path == self.ignored_prefix
                    or path.startswith(self.ignored_prefix + os.sep)
                ):
                    return
                if event.is_directory:
                    service._debounced_scan(self.oid)
                    return
                if path and Path(path).suffix.lower() in AUDIO_SUFFIXES:
                    service._debounced_scan(self.oid)

        for origin_id, path in desired.items():
            current = self._watches.get(origin_id)
            if current is not None:
                watch, watched_path = current
                if watched_path == path:
                    continue
                try:
                    self._observer.unschedule(watch)
                except Exception:
                    pass
                self._watches.pop(origin_id, None)
            if not os.path.isdir(path):
                continue
            destination = destinations.get(origin_id)
            ignored = destination if destination and destination != path else None
            try:
                watch = self._observer.schedule(
                    _Handler(origin_id, ignored), path, recursive=True
                )
                self._watches[origin_id] = (watch, path)
            except Exception as exc:
                log.warning("Cannot watch %s: %s", path, exc)

    def _debounced_scan(self, origin_id: str) -> None:
        now = time.monotonic()
        if now - self._last_event.get(origin_id, 0.0) < 3.0:
            return
        self._last_event[origin_id] = now
        self.request_scan(origin_id, delay=3.0)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _activity(
        self,
        level: str,
        category: str,
        message: str,
        *,
        origin_id: str | None = None,
        job_id: str | None = None,
        detail: Any = None,
    ) -> None:
        try:
            with self.db.session() as session:
                session.add(
                    Activity(
                        level=level,
                        category=category,
                        origin_id=origin_id,
                        job_id=job_id,
                        message=message,
                        detail_json=dumps(detail) if detail is not None else None,
                    )
                )
        except Exception:  # pragma: no cover
            log.exception("Could not record activity")
        self.bus.publish("activity")

    def _notify_review(
        self, origin: Origin, job: Job, duplicate: bool = False
    ) -> None:
        self._notify_review_text(origin.name, job.artist, job.album, duplicate)

    def _notify_review_text(
        self,
        origin_name: str,
        artist: str | None,
        album: str | None,
        duplicate: bool = False,
    ) -> None:
        if not self.store.get_bool("notify_on_review", True):
            return
        title = "Duplicate detected" if duplicate else "Album needs review"
        message = (
            f"{artist or 'Unknown artist'} - {album or 'Unknown album'} "
            f"from {origin_name}"
        )
        self.notifier.notify(title=title, message=message, kind="review")


def _origin_spec(origin: Origin) -> SimpleNamespace:
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


def _majority_tags(
    files: list[dict], candidates: list[Any]
) -> tuple[str, str, int | None]:
    if candidates and candidates[0].similarity >= 0.6:
        best = candidates[0]
        return best.albumartist, best.album, best.year

    albumartists: Counter[str] = Counter()
    artist_originals: dict[str, str] = {}
    for entry in files:
        value = (entry.get("albumartist") or entry.get("artist") or "").strip()
        if not value or value.lower() in ("[unknown]", "unknown"):
            continue
        key = normalize_text(value)
        albumartists[key] += 1
        artist_originals.setdefault(key, value)

    albums: Counter[str] = Counter()
    album_originals: dict[str, str] = {}
    for entry in files:
        value = (entry.get("album") or "").strip()
        if not value:
            continue
        key = normalize_text(value)
        albums[key] += 1
        album_originals.setdefault(key, value)

    albumartist = (
        artist_originals.get(albumartists.most_common(1)[0][0], "")
        if albumartists
        else ""
    )
    album = (
        album_originals.get(albums.most_common(1)[0][0], "") if albums else ""
    )
    year = None
    for entry in files:
        if entry.get("year"):
            year = int(entry["year"])
            break
    return albumartist, album, year
