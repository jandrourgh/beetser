from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

FFMPEG = shutil.which("ffmpeg")


def make_flac(
    path: Path,
    *,
    title: str = "Song",
    artist: str = "Test Artist",
    album: str = "Test Album",
    albumartist: str | None = None,
    track: int = 1,
    year: int | None = None,
    duration: int = 3,
) -> Path:
    if not FFMPEG:
        pytest.skip("ffmpeg is required for this test")
    path.parent.mkdir(parents=True, exist_ok=True)
    args = [
        FFMPEG,
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency={300 + track * 40}:duration={duration}",
        "-metadata",
        f"title={title}",
        "-metadata",
        f"artist={artist}",
        "-metadata",
        f"album={album}",
        "-metadata",
        f"albumartist={albumartist or artist}",
        "-metadata",
        f"track={track}",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-y",
        str(path),
    ]
    if year:
        args += ["-metadata", f"date={year}"]
    subprocess.run(args, check=True)
    return path


def wait_for_job(client, origin_id: str, states: set[str], timeout: float = 45.0):
    import time

    deadline = time.time() + timeout
    jobs: list[dict] = []
    while time.time() < deadline:
        jobs = client.get("/api/jobs", params={"origin_id": origin_id}).json()["jobs"]
        if jobs and jobs[0]["state"] in states:
            return jobs[0]
        time.sleep(0.2)
    assert jobs, "no job was created"
    return jobs[0]
