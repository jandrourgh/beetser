from __future__ import annotations

import shutil
from pathlib import Path

from fake_beets import fake_analyze_factory
from helpers import wait_for_job


def _copy_album(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.is_file():
            shutil.copy2(item, target / item.name)


def test_review_import_and_duplicate_flow(client, tmp_path: Path):
    client.app.state.engine.analyze = fake_analyze_factory()

    incoming = tmp_path / "incoming"
    from helpers import make_flac

    make_flac(incoming / "Album" / "01.flac", title="One", artist="Flow Artist", album="Flow Album", track=1)
    make_flac(incoming / "Album" / "02.flac", title="Two", artist="Flow Artist", album="Flow Album", track=2)

    origin = client.post(
        "/api/origins",
        json={"name": "Flow", "path": str(incoming), "auto_tag": "disabled"},
    ).json()

    job = wait_for_job(client, origin["id"], {"needs_review", "duplicate", "failed"})
    assert job["state"] == "needs_review", job
    detail = client.get(f"/api/jobs/{job['id']}").json()
    assert detail["artist"] == "Flow Artist"
    assert detail["album"] == "Flow Album"
    assert detail["track_count"] == 2
    assert detail["files"][0]["title"] in ("One", "Two")

    applied = client.post(f"/api/jobs/{job['id']}/apply", json={"mode": "asis"})
    assert applied.status_code == 200

    job = wait_for_job(client, origin["id"], {"imported", "failed", "skipped"})
    assert job["state"] == "imported", job["error"]
    # Tag-only imports write metadata but never move or rename the files.
    assert sorted(p.name for p in (incoming / "Album").glob("*.flac")) == [
        "01.flac",
        "02.flac",
    ]
    assert client.get("/api/library/stats").json()["tracks"] == 2

    # Dropping the same music into another origin must be flagged as duplicate.
    second = tmp_path / "second"
    _copy_album(incoming / "Album", second / "Copy")
    duplicate_origin = client.post(
        "/api/origins",
        json={"name": "Second", "path": str(second), "auto_tag": "disabled"},
    ).json()

    duplicate = wait_for_job(client, duplicate_origin["id"], {"duplicate", "needs_review", "failed"})
    assert duplicate["state"] == "duplicate", duplicate
    assert duplicate["duplicate_summary"]

    blocked = client.post(f"/api/jobs/{duplicate['id']}/apply", json={"mode": "asis"})
    assert blocked.status_code == 409

    forced = client.post(
        f"/api/jobs/{duplicate['id']}/apply", json={"mode": "asis", "force": True}
    )
    assert forced.status_code == 200
    final = wait_for_job(client, duplicate_origin["id"], {"imported", "failed"})
    assert final["state"] == "imported", final["error"]
    assert client.get("/api/library/stats").json()["tracks"] == 4


def test_skipping_a_job_marks_files_skipped(client, tmp_path: Path):
    client.app.state.engine.analyze = fake_analyze_factory()
    from helpers import make_flac

    incoming = tmp_path / "incoming"
    make_flac(incoming / "Album" / "01.flac", title="Skip me")
    origin = client.post(
        "/api/origins",
        json={"name": "Skip", "path": str(incoming), "auto_tag": "disabled"},
    ).json()

    job = wait_for_job(client, origin["id"], {"needs_review", "duplicate", "failed"})
    assert client.post(f"/api/jobs/{job['id']}/skip").status_code == 200

    detail = client.get(f"/api/jobs/{job['id']}").json()
    assert detail["state"] == "skipped"
    assert (incoming / "Album" / "01.flac").exists()

    # A rescan must not create a new job for skipped files.
    client.post(f"/api/origins/{origin['id']}/scan")
    import time

    time.sleep(1.5)
    jobs = client.get("/api/jobs", params={"origin_id": origin["id"]}).json()["jobs"]
    assert len(jobs) == 1


def test_manual_tagging_imports_with_edited_values(client, tmp_path: Path):
    client.app.state.engine.analyze = fake_analyze_factory()
    from helpers import make_flac

    incoming = tmp_path / "manual"
    make_flac(incoming / "Stuff" / "01.flac", title="Untitled", artist="", album="", track=1)
    origin = client.post(
        "/api/origins",
        json={"name": "Manual", "path": str(incoming), "auto_tag": "disabled"},
    ).json()

    job = wait_for_job(client, origin["id"], {"needs_review", "duplicate", "failed"})
    detail = client.get(f"/api/jobs/{job['id']}").json()
    tracks = {
        entry["path"]: {"title": "Edited Title", "track": 1} for entry in detail["files"]
    }
    response = client.post(
        f"/api/jobs/{job['id']}/apply",
        json={
            "mode": "manual",
            "fields": {
                "albumartist": "Manual Artist",
                "album": "Manual Album",
                "year": "2024",
            },
            "tracks": tracks,
        },
    )
    assert response.status_code == 200

    final = wait_for_job(client, origin["id"], {"imported", "failed"})
    assert final["state"] == "imported", final["error"]

    albums = client.get("/api/library/albums").json()["albums"]
    assert [(a["album"], a["albumartist"]) for a in albums] == [("Manual Album", "Manual Artist")]
    album = client.get(f"/api/library/albums/{albums[0]['id']}").json()
    assert album["tracks"][0]["title"] == "Edited Title"


def test_copy_mode_keeps_originals_and_does_not_requeue_them(client, tmp_path: Path):
    client.app.state.engine.analyze = fake_analyze_factory()
    from helpers import make_flac

    incoming = tmp_path / "copy-in"
    destination = tmp_path / "copy-out"
    destination.mkdir()
    make_flac(incoming / "Album" / "01.flac", title="Copied", artist="Copy Artist", album="Copy Album")

    origin = client.post(
        "/api/origins",
        json={
            "name": "Copy",
            "path": str(incoming),
            "destination": str(destination),
            "import_mode": "copy",
            "auto_tag": "disabled",
        },
    ).json()

    job = wait_for_job(client, origin["id"], {"needs_review", "duplicate", "failed"})
    assert client.post(f"/api/jobs/{job['id']}/apply", json={"mode": "asis"}).status_code == 200
    final = wait_for_job(client, origin["id"], {"imported", "failed"})
    assert final["state"] == "imported", final["error"]

    assert (incoming / "Album" / "01.flac").exists()
    assert list(destination.rglob("*.flac"))

    client.post(f"/api/origins/{origin['id']}/scan")
    import time

    time.sleep(1.5)
    jobs = client.get("/api/jobs", params={"origin_id": origin["id"]}).json()["jobs"]
    assert len(jobs) == 1


def test_album_edit_and_cover_api(client, tmp_path: Path):
    import io

    from PIL import Image

    client.app.state.engine.analyze = fake_analyze_factory()
    from helpers import make_flac

    incoming = tmp_path / "api-library"
    make_flac(incoming / "Album" / "01.flac", title="One", artist="API Artist", album="API Album")
    origin = client.post(
        "/api/origins",
        json={"name": "API", "path": str(incoming), "auto_tag": "disabled"},
    ).json()
    job = wait_for_job(client, origin["id"], {"needs_review", "duplicate", "failed"})
    assert client.post(f"/api/jobs/{job['id']}/apply", json={"mode": "asis"}).status_code == 200
    final = wait_for_job(client, origin["id"], {"imported", "failed"})
    assert final["state"] == "imported", final["error"]

    album = client.get("/api/library/albums").json()["albums"][0]

    updated = client.patch(
        f"/api/library/albums/{album['id']}",
        json={
            "fields": {"album": "Edited API Album", "albumartist": "Edited API Artist"},
            "write_tags": True,
            "move_files": True,
        },
    )
    assert updated.status_code == 200, updated.text
    updated_album = updated.json()["album"]
    assert updated_album["album"] == "Edited API Album"
    assert updated_album["albumartist"] == "Edited API Artist"
    assert all(
        "/Edited API Artist/Edited API Album/" in track["path"]
        for track in updated_album["tracks"]
    ), updated_album["tracks"]

    buffer = io.BytesIO()
    Image.new("RGB", (600, 600), (10, 120, 90)).save(buffer, "PNG")
    cover = client.put(
        f"/api/library/albums/{album['id']}/cover",
        files={"file": ("cover.png", buffer.getvalue(), "image/png")},
    )
    assert cover.status_code == 200, cover.text
    assert cover.json()["artpath"]

    image = client.get(f"/api/library/albums/{album['id']}/cover")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"

    removed = client.delete(f"/api/library/albums/{album['id']}/cover")
    assert removed.status_code == 200
    assert client.get(f"/api/library/albums/{album['id']}/cover").status_code == 404


def test_organize_sorts_files_in_place(client, tmp_path: Path):
    client.app.state.engine.analyze = fake_analyze_factory()
    from helpers import make_flac

    incoming = tmp_path / "organize"
    make_flac(incoming / "Raw Download" / "01.flac", title="One", artist="Sort Artist", album="Sort Album")
    origin = client.post(
        "/api/origins",
        json={"name": "Organize", "path": str(incoming), "auto_tag": "disabled"},
    ).json()

    job = wait_for_job(client, origin["id"], {"needs_review", "duplicate", "failed"})
    assert client.post(f"/api/jobs/{job['id']}/apply", json={"mode": "asis"}).status_code == 200
    assert wait_for_job(client, origin["id"], {"imported", "failed"})["state"] == "imported"

    album = client.get("/api/library/albums").json()["albums"][0]
    assert (incoming / "Raw Download" / "01.flac").is_file()

    organized = client.post(f"/api/library/albums/{album['id']}/organize")
    assert organized.status_code == 200, organized.text
    expected = incoming / "Sort Artist" / "Sort Album" / "01 One.flac"
    assert expected.is_file()
    assert not (incoming / "Raw Download").exists()
    assert expected.as_posix() in {
        track["path"] for track in organized.json()["album"]["tracks"]
    }

    # The scanner must forget the old path, otherwise reusing it would be
    # mistaken for an already-imported file.
    from beetser.models import TrackedFile

    with client.app.state.db.session() as session:
        paths = {row.path for row in session.query(TrackedFile).all()}
    assert expected.as_posix() in paths
    assert not any(path.endswith("Raw Download/01.flac") for path in paths)


def test_organize_origin_bulk(client, tmp_path: Path):
    client.app.state.engine.analyze = fake_analyze_factory()
    from helpers import make_flac

    incoming = tmp_path / "bulk"
    for index, album_name in enumerate(("First", "Second"), start=1):
        make_flac(
            incoming / f"Drop {index}" / "01.flac",
            title=f"{album_name} Song",
            artist="Bulk Artist",
            album=album_name,
            track=index,
        )
    origin = client.post(
        "/api/origins",
        json={"name": "Bulk", "path": str(incoming), "auto_tag": "disabled"},
    ).json()

    wait_for_job(client, origin["id"], {"needs_review", "duplicate", "failed"})
    for album_name in ("First", "Second"):
        jobs = client.get(f"/api/jobs?origin_id={origin['id']}").json()["jobs"]
        job = next(entry for entry in jobs if entry["album"] == album_name)
        applied = client.post(f"/api/jobs/{job['id']}/apply", json={"mode": "asis"})
        assert applied.status_code == 200, applied.text
        done = wait_for_job(
            client, origin["id"], {"imported", "failed"}, job_id=job["id"]
        )
        assert done["state"] == "imported", done["error"]

    result = client.post(f"/api/origins/{origin['id']}/organize")
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["organized"] == 2, body
    assert body["failed"] == 0, body
    assert (incoming / "Bulk Artist" / "First").is_dir()
    assert (incoming / "Bulk Artist" / "Second").is_dir()
