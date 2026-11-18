"""The beets integration layer.

This module owns everything that touches beets:

* generating per-origin beets configuration files,
* running MusicBrainz lookups in-process for the review UI,
* executing imports through the patched beets CLI,
* reading the central library for browsing and duplicate detection.

All beets writes happen in a subprocess, which keeps the global beets
configuration in the API process read-only and avoids concurrent state.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .beets_compat import install_absolute_path_patch
from .settings import Settings
from .settings_store import SettingsStore
from .utils import is_audio_file, tail

log = logging.getLogger(__name__)

ART_URL_TEMPLATE = "https://coverartarchive.org/release/{release_id}/front-500"


@dataclass
class FileInfo:
    path: str
    name: str
    size: int
    mtime: float
    artist: str = ""
    album: str = ""
    albumartist: str = ""
    title: str = ""
    track: int = 0
    disc: int = 0
    length: float = 0.0
    year: int = 0
    format: str = ""


@dataclass
class CandidateTrack:
    index: int
    title: str
    artist: str = ""
    length: float = 0.0
    medium: int = 1
    medium_index: int = 0
    track_id: str | None = None


@dataclass
class Candidate:
    source: str
    album_id: str | None
    album: str
    albumartist: str
    year: int | None = None
    month: int | None = None
    day: int | None = None
    country: str | None = None
    label: str | None = None
    catalognum: str | None = None
    barcode: str | None = None
    media: str | None = None
    albumtype: str | None = None
    albumstatus: str | None = None
    albumdisambig: str | None = None
    similarity: float = 0.0
    missing_tracks: int = 0
    extra_items: int = 0
    art_url: str | None = None
    tracks: list[CandidateTrack] = field(default_factory=list)
    mapping: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class AnalysisResult:
    files: list[FileInfo] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    recommendation: str | None = None
    best_similarity: float | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "files": [asdict(f) for f in self.files],
            "candidates": [asdict(c) for c in self.candidates],
            "recommendation": self.recommendation,
            "best_similarity": self.best_similarity,
            "error": self.error,
            "warnings": self.warnings,
        }


@dataclass
class ImportResult:
    ok: bool
    returncode: int
    output: str
    new_items: list[dict[str, Any]] = field(default_factory=list)
    reason: str | None = None


@dataclass
class UpdateResult:
    ok: bool
    output: str = ""
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class AlbumRow:
    id: int
    album: str
    albumartist: str
    year: int | None
    path: str | None
    artpath: str | None
    track_count: int
    added: str | None
    mb_albumid: str | None
    art_mtime: float | None = None


class BeetsEngine:
    def __init__(self, settings: Settings, store: SettingsStore):
        self.settings = settings
        self.store = store
        self._prepare_lock = threading.Lock()
        self._prepared = False
        self._music_dir = settings.data_dir / "music"
        self._music_dir.mkdir(parents=True, exist_ok=True)
        self.base_config_path = settings.beets_dir / "config.yaml"

        self._cache_lock = threading.Lock()
        self._path_cache: set[str] | None = None
        self._path_cache_ts = 0.0
        self._mbid_cache: set[str] | None = None
        self._mbid_cache_ts = 0.0
        self.cache_ttl = 120.0

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def prepare(self) -> None:
        """Write the base config and initialise beets' global state once."""
        with self._prepare_lock:
            if self._prepared:
                return
            install_absolute_path_patch()
            self._write_base_config()

            from beets import config, plugins

            config.read(user=False)
            config.set_file(str(self.base_config_path))
            config["library"] = str(self.settings.library_path)
            config["directory"] = str(self._music_dir)
            try:
                plugins.load_plugins()
            except Exception as exc:  # pragma: no cover - plugin issues
                log.warning("Could not load beets plugins: %s", exc)
            self._prepared = True

    def _write_base_config(self) -> None:
        data: dict[str, Any] = {
            "library": str(self.settings.library_path),
            "directory": str(self._music_dir),
            "statefile": str(self.settings.beets_dir / "state.pickle"),
            "create_backup_before_migrations": False,
            "plugins": ["musicbrainz"],
            "import": {"resume": False, "incremental": False},
            "ui": {"color": False},
        }
        if self.settings.musicbrainz_user_agent:
            data["musicbrainz"] = {"useragent": self.settings.musicbrainz_user_agent}
        self._write_yaml(self.base_config_path, data)

    def _write_yaml(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        tmp.replace(path)

    def _effective_path_format(self, origin: Any, key: str, default_key: str) -> str:
        if key == "default" and origin.path_format:
            return origin.path_format
        if key == "singleton" and origin.singleton_path_format:
            return origin.singleton_path_format
        return str(self.store.get(default_key) or "").strip()

    def write_origin_config(self, origin: Any) -> Path:
        """Generate the beets config used by one origin's imports."""
        self.prepare()
        destination = Path(origin.effective_destination)
        destination.mkdir(parents=True, exist_ok=True)

        fetch_art = self.store.get_bool("fetch_art", True)
        embed_art = self.store.get_bool("embed_art", False)
        # `fetchart` is always enabled: with only the `filesystem` source it
        # adopts local cover.jpg/folder.jpg files without any network access.
        plugins = ["musicbrainz", "fetchart"]
        if embed_art:
            plugins.append("embedart")

        default_format = self._effective_path_format(origin, "default", "path_format")
        singleton_format = self._effective_path_format(
            origin, "singleton", "singleton_path_format"
        )
        comp_format = str(self.store.get("comp_path_format") or default_format)

        data: dict[str, Any] = {
            "library": str(self.settings.library_path),
            "directory": str(destination),
            "statefile": str(self.settings.beets_dir / f"state-{origin.id}.pickle"),
            "create_backup_before_migrations": False,
            "plugins": plugins,
            "import": {
                "write": self.store.get_bool("write_tags", True),
                "autotag": True,
                "quiet": True,
                "quiet_fallback": "skip",
                "none_rec_action": "skip",
                "timid": False,
                "incremental": False,
                "resume": False,
                "duplicate_action": "keep",
                "from_scratch": False,
                "singletons": False,
            },
            # We always apply an explicitly chosen release, so beets must not
            # second-guess the decision based on its own recommendation caps.
            "match": {
                "strong_rec_thresh": 1.0,
                "medium_rec_thresh": 1.0,
                "max_rec": {
                    "missing_tracks": "strong",
                    "unmatched_tracks": "strong",
                },
            },
            "paths": {
                "default": default_format,
                "singleton": singleton_format,
                "comp": comp_format,
            },
            "ui": {"color": False},
        }
        data["fetchart"] = {
            "auto": True,
            # As-is imports search local files only; matched imports may use
            # the web sources below when `fetch_art` is enabled.
            "fetch_for_asis": False,
            "cover_names": [
                "cover",
                "folder",
                "front",
                "album",
                "albumart",
                "artwork",
                "art",
            ],
            "maxwidth": 1200,
            "sources": ["filesystem"] + (["coverart", "itunes"] if fetch_art else []),
        }
        if embed_art:
            data["embedart"] = {
                "auto": True,
                "maxwidth": 1200,
                "remove_art_file": False,
            }

        path = self.settings.origin_config_dir / f"{origin.id}.yaml"
        self._write_yaml(path, data)
        return path

    # ------------------------------------------------------------------
    # Library access
    # ------------------------------------------------------------------

    def library_exists(self) -> bool:
        return self.settings.library_path.exists()

    def _connect(self) -> sqlite3.Connection | None:
        if not self.library_exists():
            return None
        uri = f"file:{self.settings.library_path}?mode=ro"
        return sqlite3.connect(uri, uri=True, timeout=15)

    def ensure_library(self) -> None:
        """Create/upgrade the beets database without importing anything."""
        self.prepare()
        from beets.library import Library

        existed = self.library_exists()
        if existed:
            self._rolling_backup()
        Library(str(self.settings.library_path), str(self._music_dir))

    def _rolling_backup(self) -> None:
        """Keep a single daily backup of the library, without beets' per-run copies."""
        source = self.settings.library_path
        if not source.is_file():
            return
        target = source.with_suffix(source.suffix + ".backup")
        try:
            if target.exists() and (time.time() - target.stat().st_mtime) < 24 * 3600:
                return
            shutil.copy2(source, target)
            log.info("Library backup written to %s", target)
        except OSError as exc:  # pragma: no cover - disk issues
            log.warning("Could not back up the library: %s", exc)

    def stats(self) -> dict[str, Any]:
        con = self._connect()
        if con is None:
            return {
                "albums": 0,
                "tracks": 0,
                "artists": 0,
                "genres": 0,
                "last_added": None,
                "library_path": str(self.settings.library_path),
            }
        try:
            tracks = con.execute("SELECT COUNT(*) FROM items").fetchone()[0]
            albums = con.execute("SELECT COUNT(*) FROM albums").fetchone()[0]
            artists = con.execute(
                "SELECT COUNT(DISTINCT albumartist) FROM albums "
                "WHERE albumartist IS NOT NULL AND albumartist != ''"
            ).fetchone()[0]
            last_added = con.execute("SELECT MAX(added) FROM items").fetchone()[0]
        finally:
            con.close()
        return {
            "albums": albums,
            "tracks": tracks,
            "artists": artists,
            "last_added": _beets_time(last_added),
            "library_path": str(self.settings.library_path),
        }

    def library_paths(self, refresh: bool = False) -> set[str]:
        with self._cache_lock:
            fresh = (
                self._path_cache is not None
                and not refresh
                and (time.monotonic() - self._path_cache_ts) < self.cache_ttl
            )
            if fresh:
                return set(self._path_cache or set())

        con = self._connect()
        result: set[str] = set()
        if con is not None:
            try:
                rows = con.execute("SELECT path FROM items").fetchall()
            finally:
                con.close()
            for (raw,) in rows:
                result.add(os.fsdecode(raw) if isinstance(raw, bytes) else str(raw))

        with self._cache_lock:
            self._path_cache = result
            self._path_cache_ts = time.monotonic()
        return set(result)

    def invalidate_library_cache(self) -> None:
        with self._cache_lock:
            self._path_cache = None
            self._mbid_cache = None

    def max_item_id(self) -> int:
        con = self._connect()
        if con is None:
            return 0
        try:
            row = con.execute("SELECT COALESCE(MAX(id), 0) FROM items").fetchone()
            return int(row[0] or 0)
        finally:
            con.close()

    def items_after(self, item_id: int) -> list[dict[str, Any]]:
        con = self._connect()
        if con is None:
            return []
        try:
            rows = con.execute(
                "SELECT i.id, i.path, i.album_id, i.title, i.artist, i.album, "
                "i.track, i.disc, i.length, a.artpath "
                "FROM items i LEFT JOIN albums a ON a.id = i.album_id "
                "WHERE i.id > ? ORDER BY i.id",
                (item_id,),
            ).fetchall()
        finally:
            con.close()
        items = []
        for row in rows:
            path = row[1]
            artpath = row[9]
            items.append(
                {
                    "id": row[0],
                    "path": os.fsdecode(path) if isinstance(path, bytes) else str(path),
                    "album_id": row[2],
                    "title": row[3],
                    "artist": row[4],
                    "album": row[5],
                    "track": row[6],
                    "disc": row[7],
                    "length": row[8],
                    "artpath": (
                        os.fsdecode(artpath) if isinstance(artpath, bytes) else artpath
                    ),
                }
            )
        return items

    def _album_rows(self, con: sqlite3.Connection, album_ids: list[int]) -> dict[int, AlbumRow]:
        if not album_ids:
            return {}
        placeholders = ",".join("?" for _ in album_ids)
        rows = con.execute(
            "SELECT a.id, a.album, a.albumartist, a.year, a.artpath, a.added, a.mb_albumid, "
            "COUNT(i.id), MIN(i.path) "
            f"FROM albums a LEFT JOIN items i ON i.album_id = a.id "
            f"WHERE a.id IN ({placeholders}) "
            "GROUP BY a.id",
            album_ids,
        ).fetchall()
        result: dict[int, AlbumRow] = {}
        for row in rows:
            artpath = row[4]
            first_path = row[8]
            art_path = _decode_path(artpath)
            result[row[0]] = AlbumRow(
                id=row[0],
                album=row[1] or "",
                albumartist=row[2] or "",
                year=row[3],
                path=_decode_path(first_path),
                artpath=art_path,
                track_count=row[7],
                added=_beets_time(row[5]),
                mb_albumid=row[6],
                art_mtime=_file_mtime(art_path),
            )
        return result

    def albums(self, query: str | None, page: int, per_page: int) -> dict[str, Any]:
        self.prepare()
        from beets.library import Library

        if not self.library_exists():
            return {"albums": [], "total": 0, "page": page, "per_page": per_page}

        lib = Library(
            str(self.settings.library_path),
            str(self._music_dir),
            set_music_dir=False,
        )
        try:
            albums = list(lib.albums(query or None))
        except Exception as exc:
            raise ValueError(f"Invalid search query: {exc}") from exc

        total = len(albums)
        start = max(0, (page - 1) * per_page)
        selected = albums[start : start + per_page]
        ids = [a.id for a in selected if a.id is not None]

        con = self._connect()
        rows: dict[int, AlbumRow] = {}
        try:
            if con is not None:
                rows = self._album_rows(con, ids)
        finally:
            if con is not None:
                con.close()

        out = []
        for album in selected:
            row = rows.get(album.id)
            out.append(
                {
                    "id": album.id,
                    "album": album.album,
                    "albumartist": album.albumartist,
                    "year": album.year,
                    "artpath": _decode_path(album.artpath),
                    "art_mtime": row.art_mtime if row else None,
                    "track_count": row.track_count if row else album.albumtotal,
                    "path": row.path if row else None,
                    "mb_albumid": album.mb_albumid,
                    "added": row.added if row else None,
                }
            )
        return {"albums": out, "total": total, "page": page, "per_page": per_page}

    def singles(self, query: str | None, page: int, per_page: int) -> dict[str, Any]:
        con = self._connect()
        if con is None:
            return {"tracks": [], "total": 0, "page": page, "per_page": per_page}
        where = "WHERE i.album_id IS NULL"
        params: list[Any] = []
        if query:
            where += " AND (lower(i.title) LIKE ? OR lower(i.artist) LIKE ? OR lower(i.album) LIKE ?)"
            pattern = f"%{query.lower()}%"
            params += [pattern, pattern, pattern]
        try:
            total = con.execute(
                f"SELECT COUNT(*) FROM items i {where}", params
            ).fetchone()[0]
            rows = con.execute(
                "SELECT i.id, i.path, i.title, i.artist, i.album, i.albumartist, "
                "i.length, i.year, i.genres, i.format, i.mtime "
                f"FROM items i {where} ORDER BY i.added DESC, i.id DESC "
                "LIMIT ? OFFSET ?",
                params + [per_page, max(0, (page - 1) * per_page)],
            ).fetchall()
        finally:
            con.close()
        tracks = [
            {
                "id": row[0],
                "path": _decode_path(row[1]),
                "title": row[2],
                "artist": row[3],
                "album": row[4],
                "albumartist": row[5],
                "length": row[6],
                "year": row[7],
                "genres": row[8],
                "format": row[9],
                "mtime": row[10],
            }
            for row in rows
        ]
        return {"tracks": tracks, "total": total, "page": page, "per_page": per_page}

    def album_detail(self, album_id: int) -> dict[str, Any] | None:
        con = self._connect()
        if con is None:
            return None
        try:
            album_row = con.execute(
                "SELECT id, album, albumartist, year, artpath, added, mb_albumid, "
                "label, catalognum, country, albumtype, albumdisambig, genres, "
                "barcode, asin, "
                "(SELECT media FROM items WHERE album_id = albums.id "
                " ORDER BY disc, track LIMIT 1) AS media "
                "FROM albums WHERE id = ?",
                (album_id,),
            ).fetchone()
            if album_row is None:
                return None
            items = con.execute(
                "SELECT id, path, title, artist, track, disc, length, genre_or_genres, "
                "mb_trackid, bitrate, format, mtime "
                "FROM (SELECT id, path, title, artist, track, disc, length, "
                "  COALESCE(genres, '') AS genre_or_genres, mb_trackid, bitrate, format, mtime "
                "  FROM items WHERE album_id = ?) "
                "ORDER BY disc, track, title",
                (album_id,),
            ).fetchall()
        finally:
            con.close()

        artpath = _decode_path(album_row[4])
        return {
            "id": album_row[0],
            "album": album_row[1],
            "albumartist": album_row[2],
            "year": album_row[3],
            "artpath": artpath,
            "art_mtime": _file_mtime(artpath),
            "added": _beets_time(album_row[5]),
            "mb_albumid": album_row[6],
            "label": album_row[7],
            "catalognum": album_row[8],
            "country": album_row[9],
            "albumtype": album_row[10],
            "albumdisambig": album_row[11],
            "genres": album_row[12],
            "barcode": album_row[13],
            "asin": album_row[14],
            "media": album_row[15],
            "tracks": [
                {
                    "id": row[0],
                    "path": _decode_path(row[1]),
                    "title": row[2],
                    "artist": row[3],
                    "track": row[4],
                    "disc": row[5],
                    "length": row[6],
                    "genres": row[7],
                    "mb_trackid": row[8],
                    "bitrate": row[9],
                    "format": row[10],
                    "mtime": row[11],
                }
                for row in items
            ],
        }

    def cover_path(self, album_id: int) -> Path | None:
        con = self._connect()
        if con is None:
            return None
        try:
            row = con.execute(
                "SELECT artpath FROM albums WHERE id = ?", (album_id,)
            ).fetchone()
        finally:
            con.close()
        if not row or not row[0]:
            return None
        path = Path(_decode_path(row[0]) or "")
        return path if path.is_file() else None

    def album_mbids(self, refresh: bool = False) -> set[str]:
        with self._cache_lock:
            fresh = (
                self._mbid_cache is not None
                and not refresh
                and (time.monotonic() - self._mbid_cache_ts) < self.cache_ttl
            )
            if fresh:
                return set(self._mbid_cache or set())

        con = self._connect()
        result: set[str] = set()
        if con is not None:
            try:
                rows = con.execute(
                    "SELECT mb_albumid FROM albums "
                    "WHERE mb_albumid IS NOT NULL AND mb_albumid != ''"
                ).fetchall()
            finally:
                con.close()
            result = {row[0] for row in rows}

        with self._cache_lock:
            self._mbid_cache = result
            self._mbid_cache_ts = time.monotonic()
        return set(result)

    def duplicate_candidates(
        self, albumartist: str, album: str, track_titles: list[str]
    ) -> list[dict[str, Any]]:
        """Find library albums that look like the same release."""
        con = self._connect()
        if con is None:
            return []
        try:
            rows = con.execute(
                "SELECT a.id, a.album, a.albumartist, a.year, COUNT(i.id), "
                "GROUP_CONCAT(i.title, '||') "
                "FROM albums a LEFT JOIN items i ON i.album_id = a.id "
                "WHERE lower(a.album) = lower(?) "
                "GROUP BY a.id LIMIT 25",
                (album or "",),
            ).fetchall()
        finally:
            con.close()

        matches = []
        wanted = {_norm(t) for t in track_titles if t}
        for row in rows:
            titles = {_norm(t) for t in (row[5] or "").split("||") if t}
            overlap = len(wanted & titles)
            same_artist = _norm(row[2]) == _norm(albumartist)
            if same_artist or (wanted and overlap / max(1, len(wanted)) >= 0.5):
                matches.append(
                    {
                        "kind": "album",
                        "album_id": row[0],
                        "album": row[1],
                        "albumartist": row[2],
                        "year": row[3],
                        "track_count": row[4],
                        "title_overlap": overlap,
                        "reason": (
                            "Same album name and artist"
                            if same_artist
                            else "Most track titles already exist in the library"
                        ),
                    }
                )
        return matches

    # ------------------------------------------------------------------
    # Autotagging
    # ------------------------------------------------------------------

    def analyze(self, paths: list[str]) -> AnalysisResult:
        self.prepare()
        from beets.autotag import tag_album, tag_item
        from beets.autotag.source import Source
        from beets.library import Item

        result = AnalysisResult()
        items = []
        for path in paths:
            try:
                item = Item.from_path(path)
                items.append(item)
                result.files.append(_file_info(item, path))
            except Exception as exc:
                result.warnings.append(f"Could not read {path}: {exc}")

        if not items:
            result.error = "No readable audio files found"
            return result

        try:
            if len(items) == 1:
                proposal = tag_item(Source.from_item(items[0]))
            else:
                proposal = tag_album(Source.from_items(items))
        except Exception as exc:
            log.warning("Autotag lookup failed for %s: %s", paths, exc)
            result.error = f"MusicBrainz lookup failed: {exc}"
            return result

        result.recommendation = proposal.recommendation.name
        result.candidates = [
            _serialize_match(match) for match in list(proposal.candidates)[:10]
        ]
        if result.candidates:
            result.best_similarity = result.candidates[0].similarity
        return result

    # ------------------------------------------------------------------
    # Importing
    # ------------------------------------------------------------------

    def import_files(
        self,
        origin: Any,
        *,
        folder: str,
        kind: str = "album",
        release_id: str | None = None,
        asis: bool = False,
        set_fields: dict[str, str] | None = None,
        track_tags: dict[str, dict[str, Any]] | None = None,
    ) -> ImportResult:
        config_path = self.write_origin_config(origin)

        if track_tags:
            for path, fields in track_tags.items():
                try:
                    _write_tags(path, fields)
                except Exception as exc:
                    return ImportResult(
                        ok=False,
                        returncode=-1,
                        output="",
                        reason=f"Could not write tags to {path}: {exc}",
                    )

        argv = [
            sys.executable,
            "-m",
            "beetser.beets_cli",
            "-c",
            str(config_path),
            "import",
            "-q",
            "-I",
        ]

        mode = origin_mode(origin, self.store)
        argv.append("-m" if mode == "move" else "-c")

        if kind == "singleton":
            argv.append("-s")
        if release_id:
            argv += ["-S", release_id]
        if asis or not release_id:
            argv.append("-A")

        merged_fields = {"beetser_origin": origin.id}
        for key, value in (set_fields or {}).items():
            if value is None or str(value) == "":
                continue
            merged_fields[key] = str(value)
        for key, value in merged_fields.items():
            argv += ["--set", f"{key}={value}"]

        argv.append("--")
        argv.append(folder)

        before = self.max_item_id()
        log.info("Importing %s (%s)", folder, "move" if mode == "move" else "copy")
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=self.settings.import_timeout,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
        except subprocess.TimeoutExpired:
            return ImportResult(
                ok=False,
                returncode=-1,
                output="",
                reason=f"Import timed out after {self.settings.import_timeout}s",
            )
        except Exception as exc:
            return ImportResult(ok=False, returncode=-1, output="", reason=str(exc))

        output = (proc.stdout or "") + (proc.stderr or "")
        new_items = self.items_after(before)
        ok = proc.returncode == 0 and bool(new_items)

        reason = None
        lowered = output.lower()
        if not ok:
            if "duplicate" in lowered:
                reason = "beets reported a duplicate album"
            elif "skipping" in lowered or "no files imported" in lowered:
                reason = "beets skipped the folder (no confident match)"
            elif proc.returncode != 0:
                reason = f"beets exited with code {proc.returncode}"
            else:
                reason = "No items were added to the library"

        return ImportResult(
            ok=ok,
            returncode=proc.returncode,
            output=tail(output, 12000),
            new_items=new_items,
            reason=reason,
        )

    def candidate_cover(self, url: str | None) -> Path | None:
        """Download and cache candidate artwork from the Cover Art Archive.

        Serving the image from Beetser avoids browser CORS/ORB problems and
        keeps the admin's browsing away from third-party hosts.
        """
        if not url:
            return None
        from urllib.parse import urlparse

        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in {
            "coverartarchive.org",
            "archive.org",
        }:
            return None

        cache_dir = self.settings.data_dir / "cache" / "covers"
        cache_dir.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        for suffix in (".jpg", ".png", ".webp"):
            existing = cache_dir / f"{key}{suffix}"
            if existing.is_file():
                return existing

        try:
            import httpx

            with httpx.Client(timeout=15, follow_redirects=True) as client:
                response = client.get(url)
        except Exception as exc:  # pragma: no cover - network
            log.debug("Could not fetch cover art: %s", exc)
            return None

        if response.status_code != 200 or not response.content:
            return None
        final = urlparse(str(response.url))
        if final.scheme != "https" or not (final.hostname or "").endswith("archive.org"):
            return None
        content_type = response.headers.get("content-type", "")
        suffix = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
        }.get(content_type.split(";")[0].strip())
        if suffix is None or len(response.content) > 15_000_000:
            return None

        path = cache_dir / f"{key}{suffix}"
        try:
            path.write_bytes(response.content)
        except OSError:
            return None
        return path

    # ------------------------------------------------------------------
    # Editing the library
    # ------------------------------------------------------------------

    ALBUM_EDIT_FIELDS = {
        "album",
        "albumartist",
        "year",
        "month",
        "day",
        "label",
        "catalognum",
        "country",
        "albumtype",
        "albumdisambig",
        "barcode",
        "asin",
        "genres",
        "original_year",
    }
    TRACK_EDIT_FIELDS = {"title", "artist", "track", "disc", "year", "genres"}
    NUMERIC_EDIT_FIELDS = {"year", "month", "day", "original_year"}
    NUMERIC_TRACK_FIELDS = {"track", "disc", "year"}

    def _library(self):
        self.prepare()
        from beets.library import Library

        return Library(str(self.settings.library_path), str(self._music_dir))

    def update_album(
        self,
        origin: Any | None,
        album_id: int,
        *,
        fields: dict[str, str] | None = None,
        tracks: dict[int, dict[str, str]] | None = None,
        write_tags: bool = True,
        move_files: bool = True,
    ) -> UpdateResult:
        fields = dict(fields or {})
        tracks = {key: dict(value) for key, value in (tracks or {}).items()}
        warnings: list[str] = []

        for key in ("album", "albumartist"):
            if key in fields and not fields[key].strip():
                return UpdateResult(False, error=f"{key} cannot be empty")
        for key in self.NUMERIC_EDIT_FIELDS:
            if key not in fields:
                continue
            if not fields[key].strip():
                fields.pop(key)
                continue
            try:
                int(fields[key])
            except ValueError:
                return UpdateResult(False, error=f"{key} must be a number")
        for item_fields in tracks.values():
            for key in self.NUMERIC_TRACK_FIELDS:
                if key not in item_fields:
                    continue
                if not item_fields[key].strip():
                    item_fields.pop(key)
                    continue
                try:
                    int(item_fields[key])
                except ValueError:
                    return UpdateResult(False, error=f"{key} must be a number")

        unknown = set(fields) - self.ALBUM_EDIT_FIELDS
        if unknown:
            return UpdateResult(False, error=f"Unsupported album fields: {', '.join(sorted(unknown))}")
        for item_fields in tracks.values():
            unknown_track = set(item_fields) - self.TRACK_EDIT_FIELDS
            if unknown_track:
                return UpdateResult(
                    False,
                    error=f"Unsupported track fields: {', '.join(sorted(unknown_track))}",
                )

        if move_files and origin is None:
            move_files = False
            warnings.append(
                "No origin was found for this album; files were updated in place."
            )

        if origin is not None:
            config_path = self.write_origin_config(origin)
        else:
            self.prepare()
            config_path = self.base_config_path

        outputs: list[str] = []
        write_flag = "-w" if write_tags else "-W"
        move_flag = "-m" if move_files else "-M"

        if fields:
            argv = [
                sys.executable,
                "-m",
                "beetser.beets_cli",
                "-c",
                str(config_path),
                "modify",
                "-a",
                "-y",
                move_flag,
                write_flag,
                f"id:{album_id}",
            ]
            argv += [f"{key}={value}" for key, value in fields.items()]
            proc = self._run_beets(argv)
            outputs.append(proc.stdout + proc.stderr)
            if proc.returncode != 0:
                return UpdateResult(
                    False,
                    output=tail("".join(outputs), 12000),
                    error=f"beets modify failed with code {proc.returncode}",
                    warnings=warnings,
                )

        for item_id, item_fields in tracks.items():
            if not item_fields:
                continue
            argv = [
                sys.executable,
                "-m",
                "beetser.beets_cli",
                "-c",
                str(config_path),
                "modify",
                "-y",
                move_flag,
                write_flag,
                f"id:{item_id}",
            ]
            argv += [f"{key}={value}" for key, value in item_fields.items()]
            proc = self._run_beets(argv)
            outputs.append(proc.stdout + proc.stderr)
            if proc.returncode != 0:
                return UpdateResult(
                    False,
                    output=tail("".join(outputs), 12000),
                    error=f"beets modify failed with code {proc.returncode}",
                    warnings=warnings,
                )

        self.invalidate_library_cache()
        return UpdateResult(True, output=tail("".join(outputs), 12000), warnings=warnings)

    def _run_beets(self, argv: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=self.settings.import_timeout,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )

    def set_album_art(
        self,
        album_id: int,
        data: bytes,
        *,
        embed: bool | None = None,
    ) -> tuple[str, list[str]]:
        import io
        import uuid

        from PIL import Image

        if not data:
            raise ValueError("Empty image")
        if len(data) > 15_000_000:
            raise ValueError("Image is larger than 15 MB")
        try:
            image = Image.open(io.BytesIO(data))
            image.verify()
            image_format = (image.format or "").upper()
        except Exception as exc:
            raise ValueError("Not a valid image") from exc

        suffix = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}.get(image_format)
        if suffix is None:
            raise ValueError("Unsupported image format (use JPEG, PNG or WebP)")

        cache_dir = self.settings.data_dir / "cache" / "art"
        cache_dir.mkdir(parents=True, exist_ok=True)
        temp_path = cache_dir / f"upload-{uuid.uuid4().hex}{suffix}"
        temp_path.write_bytes(data)

        warnings: list[str] = []
        try:
            lib = self._library()
            album = lib.get_album(album_id)
            if album is None:
                raise KeyError(album_id)
            album.set_art(str(temp_path), copy=True)
            album.store()
            artpath = _decode_path(album.artpath) or ""

            if embed is None:
                embed = self.store.get_bool("embed_art", False)
            if embed:
                import mediafile

                for item in album.items():
                    try:
                        media = mediafile.MediaFile(os.fsdecode(item.path))
                        media.art = data
                        media.save()
                    except Exception as exc:  # pragma: no cover - codec issues
                        warnings.append(f"Could not embed art in {item.path}: {exc}")
        finally:
            try:
                temp_path.unlink()
            except OSError:
                pass

        return artpath, warnings

    def clear_album_art(
        self, album_id: int, *, clear_embedded: bool = True
    ) -> list[str]:
        warnings: list[str] = []
        lib = self._library()
        album = lib.get_album(album_id)
        if album is None:
            raise KeyError(album_id)

        old_art = album.artpath
        album.artpath = None
        album.store()
        if old_art:
            try:
                Path(os.fsdecode(old_art)).unlink(missing_ok=True)
            except OSError as exc:
                warnings.append(f"Could not remove {os.fsdecode(old_art)}: {exc}")

        if clear_embedded:
            import mediafile

            for item in album.items():
                try:
                    media = mediafile.MediaFile(os.fsdecode(item.path))
                    media.art = None
                    media.save()
                except Exception as exc:  # pragma: no cover - codec issues
                    warnings.append(f"Could not clear art in {item.path}: {exc}")
        return warnings

    def fetch_album_art(self, album_id: int) -> tuple[str, list[str]]:
        lib = self._library()
        album = lib.get_album(album_id)
        if album is None:
            raise KeyError(album_id)
        mbid = album.mb_albumid
        if not mbid:
            raise ValueError("This album has no MusicBrainz release id")
        path = self.candidate_cover(ART_URL_TEMPLATE.format(release_id=mbid))
        if path is None:
            raise ValueError("Cover Art Archive returned no image for this release")
        return self.set_album_art(album_id, path.read_bytes())

    def album_origin_id(self, album_id: int) -> str | None:
        con = self._connect()
        if con is None:
            return None
        try:
            row = con.execute(
                "SELECT value FROM item_attributes WHERE item_id IN "
                "(SELECT id FROM items WHERE album_id = ?) AND key = 'beetser_origin' "
                "LIMIT 1",
                (album_id,),
            ).fetchone()
        except sqlite3.Error:
            return None
        finally:
            con.close()
        return str(row[0]) if row and row[0] else None

    def system_info(self) -> dict[str, Any]:
        import beets

        usage = shutil.disk_usage(self.settings.data_dir)
        return {
            "beetser_version": _beetser_version(),
            "beets_version": getattr(beets, "__version__", "unknown"),
            "python_version": sys.version.split()[0],
            "library_path": str(self.settings.library_path),
            "data_dir": str(self.settings.data_dir),
            "library_exists": self.library_exists(),
            "disk": {
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
            },
        }


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def origin_mode(origin: Any, store: SettingsStore) -> str:
    if origin.import_mode in {"move", "copy"}:
        return origin.import_mode
    mode = str(store.get("import_mode") or "move")
    return mode if mode in {"move", "copy"} else "move"


def _beetser_version() -> str:
    from . import __version__

    return __version__


def _norm(value: str | None) -> str:
    from .utils import normalize_text

    return normalize_text(value)


def _file_mtime(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return os.path.getmtime(value)
    except OSError:
        return None


def _beets_time(value: Any) -> str | None:
    """beets stores timestamps as Unix seconds; the UI expects ISO-8601."""
    if value is None or value == "":
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return str(value)


def _decode_path(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return os.fsdecode(value)
    return str(value)


def _file_info(item: Any, path: str) -> FileInfo:
    try:
        stat = os.stat(path)
        size, mtime = stat.st_size, stat.st_mtime
    except OSError:
        size, mtime = 0, 0.0
    return FileInfo(
        path=path,
        name=Path(path).name,
        size=size,
        mtime=mtime,
        artist=item.get("artist") or "",
        album=item.get("album") or "",
        albumartist=item.get("albumartist") or "",
        title=item.get("title") or "",
        track=int(item.get("track") or 0),
        disc=int(item.get("disc") or 0),
        length=float(item.get("length") or 0.0),
        year=int(item.get("year") or 0),
        format=item.get("format") or "",
    )


def _serialize_match(match: Any) -> Candidate:
    info = match.info
    similarity = round(max(0.0, min(1.0, 1.0 - float(match.distance))), 4)
    is_singleton = not hasattr(info, "tracks")

    album_id = info.get("album_id")
    if is_singleton:
        album_id = info.get("track_id") or album_id

    tracks = []
    mapping: dict[str, dict[str, Any]] = {}
    if is_singleton:
        tracks.append(
            CandidateTrack(
                index=1,
                title=info.get("title") or "",
                artist=info.get("artist") or "",
                length=float(info.get("length") or 0.0),
                medium=1,
                medium_index=0,
                track_id=info.get("track_id"),
            )
        )
        item = getattr(match, "item", None)
        path = _decode_path(item.path) if item is not None else None
        if path:
            mapping[path] = {
                "index": 1,
                "medium_index": 0,
                "medium": 1,
                "title": info.get("title") or "",
            }
    else:
        for track in info.tracks:
            tracks.append(
                CandidateTrack(
                    index=int(track.get("index") or 0),
                    title=track.get("title") or "",
                    artist=track.get("artist") or "",
                    length=float(track.get("length") or 0.0),
                    medium=int(track.get("medium") or 1),
                    medium_index=int(track.get("medium_index") or 0),
                    track_id=track.get("track_id"),
                )
            )
        for item, track in getattr(match, "mapping", {}).items():
            path = _decode_path(item.path)
            if not path:
                continue
            mapping[path] = {
                "index": int(track.get("index") or 0),
                "medium_index": int(track.get("medium_index") or 0),
                "medium": int(track.get("medium") or 1),
                "title": track.get("title") or "",
            }

    return Candidate(
        source=info.get("data_source") or "MusicBrainz",
        album_id=album_id,
        album=info.get("album") or (info.get("title") if is_singleton else "") or "",
        albumartist=info.get("artist") or "",
        year=info.get("year"),
        month=info.get("month"),
        day=info.get("day"),
        country=info.get("country"),
        label=info.get("label"),
        catalognum=info.get("catalognum"),
        barcode=info.get("barcode"),
        media=info.get("media"),
        albumtype=info.get("albumtype"),
        albumstatus=info.get("albumstatus"),
        albumdisambig=info.get("albumdisambig"),
        similarity=similarity,
        missing_tracks=len(getattr(match, "extra_tracks", []) or []),
        extra_items=len(getattr(match, "extra_items", []) or []),
        art_url=(
            ART_URL_TEMPLATE.format(release_id=album_id)
            if album_id and not is_singleton
            else None
        ),
        tracks=tracks,
        mapping=mapping,
    )


def _write_tags(path: str, fields: dict[str, Any]) -> None:
    import mediafile as mediafile_module

    media = mediafile_module.MediaFile(path)
    simple = {
        "title": "title",
        "artist": "artist",
        "album": "album",
        "albumartist": "albumartist",
        "genre": "genre",
        "label": "label",
        "catalognum": "catalognum",
        "country": "country",
    }
    for key, attr in simple.items():
        if key in fields and fields[key] not in (None, ""):
            try:
                setattr(media, attr, str(fields[key]))
            except Exception:
                pass
    for key, attr in (("track", "track"), ("disc", "disc"), ("year", "year")):
        if key in fields and fields[key] not in (None, ""):
            try:
                setattr(media, attr, int(fields[key]))
            except (TypeError, ValueError):
                pass
    media.save()


def file_sha256(path: str, chunk_size: int = 1024 * 1024) -> str:
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def collect_audio_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file() and is_audio_file(p)]
