"""Duplicate detection against the central library."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .beets_engine import BeetsEngine
from .models import ImportedFingerprint
from .utils import normalize_text


@dataclass
class DuplicateReport:
    exact: list[dict[str, Any]] = field(default_factory=list)
    tracks: list[dict[str, Any]] = field(default_factory=list)
    albums: list[dict[str, Any]] = field(default_factory=list)

    @property
    def blocking(self) -> bool:
        return bool(self.exact or self.tracks or self.albums)

    def summary(self) -> str | None:
        if self.exact:
            return f"{len(self.exact)} identical file(s) already imported"
        if self.albums:
            album = self.albums[0]
            return f"Album '{album['album']}' by {album['albumartist']} is already in the library"
        if self.tracks:
            return f"{len(self.tracks)} track(s) already exist in the library"
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "exact": self.exact,
            "tracks": self.tracks,
            "albums": self.albums,
            "blocking": self.blocking,
            "summary": self.summary(),
        }


def check_exact_files(
    session: Session, hashes: dict[str, str]
) -> list[dict[str, Any]]:
    """Return fingerprint rows matching any of ``{path: sha256}``."""
    if not hashes:
        return []
    values = [h for h in hashes.values() if h]
    if not values:
        return []
    rows = session.scalars(
        select(ImportedFingerprint).where(ImportedFingerprint.sha256.in_(values))
    ).all()
    out = []
    for row in rows:
        source_path = next((p for p, h in hashes.items() if h == row.sha256), None)
        out.append(
            {
                "kind": "exact",
                "sha256": row.sha256,
                "incoming_path": source_path,
                "library_path": row.path,
                "message": "This exact file has already been imported",
            }
        )
    return out


def check_track_duplicates(
    engine: BeetsEngine, files: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Match incoming files against library items by artist/title/length."""
    con = engine._connect()  # read-only connection
    if con is None:
        return []
    matches: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    try:
        for entry in files:
            title = (entry.get("title") or "").strip()
            artist = (entry.get("artist") or entry.get("albumartist") or "").strip()
            if not title:
                continue
            rows = con.execute(
                "SELECT i.id, i.title, i.artist, i.album, i.length, i.path, i.album_id "
                "FROM items i WHERE lower(i.title) = lower(?) "
                "AND (lower(i.artist) = lower(?) OR lower(i.albumartist) = lower(?)) "
                "LIMIT 5",
                (title, artist, artist),
            ).fetchall()
            for row in rows:
                length = float(row[4] or 0.0)
                incoming_length = float(entry.get("length") or 0.0)
                if length and incoming_length and abs(length - incoming_length) > 3.0:
                    continue
                key = (row[0], entry.get("path"))
                if key in seen:
                    continue
                seen.add(key)
                matches.append(
                    {
                        "kind": "track",
                        "incoming_path": entry.get("path"),
                        "library_path": _decode(row[5]),
                        "title": row[1],
                        "artist": row[2],
                        "album": row[3],
                        "album_id": row[6],
                        "length": row[4],
                        "message": "A track with the same artist, title and length exists",
                    }
                )
    except sqlite3.Error:
        return matches
    finally:
        con.close()
    return matches


def check_album_duplicates(
    engine: BeetsEngine,
    albumartist: str,
    album: str,
    files: list[dict[str, Any]],
    library_mbids: set[str],
    release_id: str | None,
) -> list[dict[str, Any]]:
    titles = [f.get("title") or "" for f in files if f.get("title")]
    matches = engine.duplicate_candidates(albumartist, album, titles)
    if release_id and release_id in library_mbids:
        matches.insert(
            0,
            {
                "kind": "release",
                "album": album,
                "albumartist": albumartist,
                "mb_albumid": release_id,
                "reason": "This exact MusicBrainz release is already in the library",
            },
        )
    return matches


def build_report(
    engine: BeetsEngine,
    session: Session,
    *,
    files: list[dict[str, Any]],
    albumartist: str,
    album: str,
    release_id: str | None,
    library_mbids: set[str] | None = None,
) -> DuplicateReport:
    hashes = {f["path"]: f.get("sha256") for f in files if f.get("sha256")}
    report = DuplicateReport()
    report.exact = check_exact_files(session, hashes)
    report.tracks = check_track_duplicates(engine, files)
    report.albums = check_album_duplicates(
        engine,
        albumartist,
        album,
        files,
        library_mbids or set(),
        release_id,
    )
    return report


def _decode(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return os.fsdecode(value)
    return str(value)


def normalize_for_match(value: str | None) -> str:
    return normalize_text(value)
