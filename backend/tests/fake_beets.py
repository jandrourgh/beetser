from __future__ import annotations

import os
from pathlib import Path

import mediafile
from beetser.beets_engine import AnalysisResult, FileInfo


def fake_analyze_factory():
    """Offline stand-in for MusicBrainz lookups.

    It still reads the real tags from disk so duplicate detection, review
    grouping and manual edits behave exactly as in production.
    """

    def fake_analyze(paths: list[str]) -> AnalysisResult:
        files = []
        for path in paths:
            media = mediafile.MediaFile(path)
            stat = os.stat(path)
            files.append(
                FileInfo(
                    path=path,
                    name=Path(path).name,
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                    artist=media.artist or "",
                    album=media.album or "",
                    albumartist=media.albumartist or "",
                    title=media.title or "",
                    track=int(media.track or 0),
                    disc=int(media.disc or 0),
                    length=float(media.length or 0),
                    year=int(media.year or 0),
                    format=media.format or "",
                )
            )
        return AnalysisResult(
            files=files, candidates=[], recommendation="none", best_similarity=None
        )

    return fake_analyze
