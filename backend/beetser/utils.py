"""Small shared helpers."""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AUDIO_EXTENSIONS = {
    ".aac",
    ".aif",
    ".aiff",
    ".alac",
    ".ape",
    ".flac",
    ".m4a",
    ".m4b",
    ".m4p",
    ".mp3",
    ".mp4",
    ".mpc",
    ".oga",
    ".ogg",
    ".opus",
    ".wav",
    ".wma",
    ".wv",
}

_NON_WORD = re.compile(r"[^a-z0-9]+")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def normalize_text(value: str | None) -> str:
    """Normalise a title/artist/album for fuzzy comparison."""
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _NON_WORD.sub(" ", ascii_value.lower()).strip()


def is_audio_file(path: Path | str) -> bool:
    return Path(path).suffix.lower() in AUDIO_EXTENSIONS


def loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def human_bytes(size: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(size) < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PiB"


def tail(value: str, max_chars: int = 8000) -> str:
    if len(value) <= max_chars:
        return value
    return value[-max_chars:]
