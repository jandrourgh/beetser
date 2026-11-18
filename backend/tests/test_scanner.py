from __future__ import annotations

from pathlib import Path

from beetser.models import Origin, TrackedFile
from beetser.scanner import Scanner, prune_empty_dirs
from sqlalchemy import select


def _scanner(db, engine, store) -> Scanner:
    return Scanner(db, engine, store)


def _origin(db, path: Path, name: str = "Tester") -> str:
    with db.session() as session:
        origin = Origin(name=name, path=str(path), destination=None, import_mode="move")
        session.add(origin)
        session.flush()
        return origin.id


def test_groups_album_folders_and_root_singles(tmp_path, db, store, engine):
    root = tmp_path / "incoming"
    (root / "Album").mkdir(parents=True)
    (root / "Album" / "01.flac").write_bytes(b"a" * 100)
    (root / "Album" / "02.flac").write_bytes(b"b" * 100)
    (root / "loose.mp3").write_bytes(b"c" * 100)
    (root / ".hidden").mkdir()
    (root / ".hidden" / "ignored.flac").write_bytes(b"d" * 100)
    ignored_dir = root / "extras"
    ignored_dir.mkdir()
    (ignored_dir / ".beetser-ignore").write_text("")
    (ignored_dir / "skip.flac").write_bytes(b"e" * 100)

    origin_id = _origin(db, root)
    stats = _scanner(db, engine, store).scan_origin(origin_id)

    assert stats.new_files == 3
    assert stats.new_jobs == 2
    assert len(stats.job_ids) == 2

    with db.session() as session:
        jobs = session.scalars(select(TrackedFile)).all()
        assert len(jobs) == 3
        assert all(row.sha256 and len(row.sha256) == 64 for row in jobs)
        assert all(row.status == "pending" for row in jobs)


def test_rescan_is_idempotent(tmp_path, db, store, engine):
    root = tmp_path / "incoming"
    (root / "Album").mkdir(parents=True)
    (root / "Album" / "01.flac").write_bytes(b"a" * 10)
    origin_id = _origin(db, root)
    scanner = _scanner(db, engine, store)

    first = scanner.scan_origin(origin_id)
    second = scanner.scan_origin(origin_id)

    assert first.new_jobs == 1
    assert second.new_jobs == 0
    assert second.new_files == 0


def test_library_paths_are_skipped(tmp_path, db, store, engine, monkeypatch):
    root = tmp_path / "incoming"
    root.mkdir()
    known = root / "known.flac"
    known.write_bytes(b"x" * 10)
    monkeypatch.setattr(engine, "library_paths", lambda refresh=False: {str(known)})

    origin_id = _origin(db, root)
    stats = _scanner(db, engine, store).scan_origin(origin_id)
    assert stats.new_jobs == 0


def test_disappearing_files_are_cleaned(tmp_path, db, store, engine):
    root = tmp_path / "incoming"
    (root / "Album").mkdir(parents=True)
    track = root / "Album" / "01.flac"
    track.write_bytes(b"a" * 10)
    origin_id = _origin(db, root)
    scanner = _scanner(db, engine, store)
    scanner.scan_origin(origin_id)

    track.unlink()
    scanner.scan_origin(origin_id)

    with db.session() as session:
        assert session.scalars(select(TrackedFile)).all() == []
        from beetser.models import Job

        job = session.scalars(select(Job)).first()
        assert job is not None
        assert job.state == "skipped"


def test_ignore_glob(tmp_path, db, store, engine):
    store.set("ignore_globs", ["*.tmp.flac"])
    root = tmp_path / "incoming"
    root.mkdir()
    (root / "keep.flac").write_bytes(b"a")
    (root / "skip.tmp.flac").write_bytes(b"b")
    origin_id = _origin(db, root)

    stats = _scanner(db, engine, store).scan_origin(origin_id)
    assert stats.new_files == 1


def test_prune_empty_dirs_stops_at_root(tmp_path):
    root = tmp_path / "root"
    nested = root / "a" / "b" / "c"
    nested.mkdir(parents=True)
    prune_empty_dirs(nested, root)
    assert root.exists()
    assert not (root / "a").exists()

    root.mkdir(exist_ok=True)
    prune_empty_dirs(root / "elsewhere", root)  # outside: no-op
