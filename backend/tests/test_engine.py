from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import yaml

from beetser.beets_engine import BeetsEngine, origin_mode
from beetser.settings_store import SettingsStore
from helpers import make_flac


def _spec(origin_id: str, path: Path, destination: Path | None = None):
    return SimpleNamespace(
        id=origin_id,
        name="Test",
        path=str(path),
        destination=str(destination) if destination else None,
        effective_destination=str(destination or path),
        import_mode="move",
        path_format=None,
        singleton_path_format=None,
        auto_tag="inherit",
        auto_tag_threshold=None,
    )


def test_generated_config(settings, store: SettingsStore, engine: BeetsEngine, tmp_path: Path):
    store.set("fetch_art", False)
    origin = _spec("origin1", tmp_path / "in", tmp_path / "out")
    config_path = engine.write_origin_config(origin)
    data = yaml.safe_load(config_path.read_text())

    assert data["library"] == str(settings.library_path)
    assert data["directory"] == str(tmp_path / "out")
    assert data["plugins"] == ["musicbrainz", "fetchart"]
    assert data["fetchart"]["sources"] == ["filesystem"]
    assert data["fetchart"]["fetch_for_asis"] is False
    assert data["import"]["quiet"] is True
    assert data["import"]["duplicate_action"] == "keep"
    assert data["match"]["strong_rec_thresh"] == 1.0
    assert data["paths"]["default"] == "$albumartist/$album%aunique{}/$track $title"
    assert (tmp_path / "out").is_dir()


def test_fetch_art_plugin_toggle(settings, store: SettingsStore, engine: BeetsEngine, tmp_path: Path):
    store.set("fetch_art", True)
    store.set("embed_art", True)
    config_path = engine.write_origin_config(_spec("origin2", tmp_path / "in", tmp_path / "out"))
    data = yaml.safe_load(config_path.read_text())
    assert "fetchart" in data["plugins"]
    assert "embedart" in data["plugins"]
    assert data["fetchart"]["auto"] is True
    assert data["embedart"]["auto"] is True


def test_origin_mode_resolution(store: SettingsStore, tmp_path: Path):
    spec = _spec("origin3", tmp_path)
    store.set("import_mode", "copy")
    assert origin_mode(spec, store) == "move"  # explicit per-origin mode wins
    spec.import_mode = "inherit"
    assert origin_mode(spec, store) == "copy"


def test_as_is_import_moves_files_and_stores_absolute_paths(
    settings, store: SettingsStore, engine: BeetsEngine, tmp_path: Path
):
    source = tmp_path / "incoming" / "Album"
    make_flac(source / "01.flac", title="One", track=1)
    make_flac(source / "02.flac", title="Two", track=2)

    destination = tmp_path / "library"
    spec = _spec("origin4", tmp_path / "incoming", destination)
    result = engine.import_files(spec, folder=str(source), kind="album", asis=True)

    assert result.ok, result.output
    assert len(result.new_items) == 2
    moved = sorted(p.relative_to(destination).as_posix() for p in destination.rglob("*.flac"))
    assert moved == ["Test Artist/Test Album/01 One.flac", "Test Artist/Test Album/02 Two.flac"]
    assert list(source.rglob("*.flac")) == []

    con = sqlite3.connect(settings.library_path)
    try:
        paths = [row[0] for row in con.execute("SELECT path FROM items")]
    finally:
        con.close()
    assert all(isinstance(path, bytes) and os.path.isabs(path) for path in paths)
    assert engine.library_paths(refresh=True) == {
        str(destination / "Test Artist" / "Test Album" / "01 One.flac"),
        str(destination / "Test Artist" / "Test Album" / "02 Two.flac"),
    }
    assert engine.stats()["tracks"] == 2


def test_library_search_and_detail(settings, store, engine, tmp_path):
    source = tmp_path / "in" / "Album"
    make_flac(source / "01.flac", title="One", artist="Searchable", album="Findable", track=1)
    engine.import_files(
        _spec("origin5", tmp_path / "in", tmp_path / "music"),
        folder=str(source),
        kind="album",
        asis=True,
    )

    page = engine.albums("findable", 1, 30)
    assert page["total"] == 1
    album = page["albums"][0]
    assert album["album"] == "Findable"

    detail = engine.album_detail(album["id"])
    assert detail is not None
    assert detail["tracks"][0]["title"] == "One"
    assert engine.singles(None, 1, 10)["total"] == 0


def test_local_art_and_album_editing(settings, store, engine, tmp_path):
    from PIL import Image

    source = tmp_path / "incoming" / "Local Album"
    make_flac(source / "01.flac", title="Original", artist="Local Artist", album="Local Album")
    Image.new("RGB", (800, 800), (30, 90, 140)).save(source / "cover.jpg", "JPEG")

    destination = tmp_path / "music"
    spec = _spec("origin6", tmp_path / "incoming", destination)
    result = engine.import_files(spec, folder=str(source), kind="album", asis=True)
    assert result.ok, result.output

    album = engine.albums(None, 1, 10)["albums"][0]
    detail = engine.album_detail(album["id"])
    assert detail is not None
    assert detail["artpath"] and Path(detail["artpath"]).is_file()
    assert engine.cover_path(album["id"]) is not None

    update = engine.update_album(
        spec,
        album["id"],
        fields={"album": "Edited Album", "albumartist": "Edited Artist", "year": "2024"},
        write_tags=True,
        move_files=True,
    )
    assert update.ok, update.output

    edited = engine.album_detail(album["id"])
    assert edited is not None
    assert edited["album"] == "Edited Album"
    assert edited["albumartist"] == "Edited Artist"
    assert edited["year"] == 2024
    assert edited["artpath"] and Path(edited["artpath"]).is_file()
    assert all(
        "/Edited Artist/Edited Album/" in track["path"] for track in edited["tracks"]
    )

    no_year = engine.update_album(
        spec, album["id"], fields={"year": ""}, write_tags=False, move_files=False
    )
    assert no_year.ok, no_year.error
    assert engine.album_detail(album["id"])["year"] == 2024

    invalid = engine.update_album(
        spec, album["id"], fields={"year": "not a year"}, write_tags=False, move_files=False
    )
    assert not invalid.ok
    assert "year must be a number" in (invalid.error or "")

    from io import BytesIO

    buffer = BytesIO()
    Image.new("RGB", (700, 700), (200, 40, 90)).save(buffer, "PNG")
    artpath, warnings = engine.set_album_art(album["id"], buffer.getvalue(), embed=False)
    assert warnings == []
    assert Path(artpath).is_file()
    assert engine.cover_path(album["id"]) == Path(artpath)

    engine.clear_album_art(album["id"])
    assert engine.cover_path(album["id"]) is None
