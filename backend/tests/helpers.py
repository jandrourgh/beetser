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


def wait_for_job(
    client,
    origin_id: str,
    states: set[str],
    timeout: float = 45.0,
    job_id: str | None = None,
):
    import time

    deadline = time.time() + timeout
    jobs: list[dict] = []
    while time.time() < deadline:
        jobs = client.get("/api/jobs", params={"origin_id": origin_id}).json()["jobs"]
        target = next((job for job in jobs if job["id"] == job_id), None) if job_id else None
        if job_id is None:
            target = jobs[0] if jobs else None
        if target is not None and target["state"] in states:
            return target
        time.sleep(0.2)
    assert jobs, "no job was created"
    if job_id:
        return next((job for job in jobs if job["id"] == job_id), jobs[0])
    return jobs[0]
