from __future__ import annotations

from beetser.dedupe import DuplicateReport, check_exact_files
from beetser.models import ImportedFingerprint


def test_summary_prefers_exact_files():
    report = DuplicateReport(
        exact=[{"kind": "exact"}],
        tracks=[{"kind": "track"}],
        albums=[{"kind": "album", "album": "X", "albumartist": "Y"}],
    )
    assert report.summary() == "1 identical file(s) already imported"
    assert report.blocking is True


def test_summary_for_album_and_tracks():
    assert (
        DuplicateReport(albums=[{"album": "A", "albumartist": "B"}]).summary()
        == "Album 'A' by B is already in the library"
    )
    assert DuplicateReport(tracks=[{}]).summary() == "1 track(s) already exist in the library"
    assert DuplicateReport().summary() is None
    assert DuplicateReport().blocking is False


def test_exact_file_lookup(db):
    sha = "a" * 64
    with db.session() as session:
        session.add(
            ImportedFingerprint(
                sha256=sha, origin_id="o1", job_id="j1", path="/library/x.flac", size=10
            )
        )

    with db.session() as session:
        matches = check_exact_files(session, {"/incoming/x.flac": sha})
    assert len(matches) == 1
    assert matches[0]["library_path"] == "/library/x.flac"
    assert matches[0]["incoming_path"] == "/incoming/x.flac"

    with db.session() as session:
        assert check_exact_files(session, {}) == []
        assert check_exact_files(session, {"/incoming/y.flac": "b" * 64}) == []
