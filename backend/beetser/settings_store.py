"""Read/write access to user-tunable settings."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from .db import Database
from .defaults import DEFAULT_SETTINGS
from .models import Setting


def _decode(value: str) -> Any:
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


class SettingsStore:
    def __init__(self, db: Database):
        self.db = db

    def ensure_defaults(self, overrides: dict[str, Any] | None = None) -> None:
        with self.db.session() as session:
            existing = {
                row.key
                for row in session.scalars(select(Setting)).all()
            }
            overrides = overrides or {}
            for key, value in DEFAULT_SETTINGS.items():
                if key not in existing:
                    session.add(
                        Setting(
                            key=key,
                            value_json=json.dumps(overrides.get(key, value)),
                        )
                    )

    def all(self) -> dict[str, Any]:
        with self.db.session() as session:
            rows = session.scalars(select(Setting)).all()
        stored = {row.key: _decode(row.value_json) for row in rows}
        return {**DEFAULT_SETTINGS, **stored}

    def get(self, key: str, default: Any = None) -> Any:
        with self.db.session() as session:
            row = session.get(Setting, key)
        if row is None:
            return DEFAULT_SETTINGS.get(key, default)
        return _decode(row.value_json)

    def get_float(self, key: str, default: float = 0.0) -> float:
        try:
            return float(self.get(key, default))
        except (TypeError, ValueError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        value = self.get(key, default)
        return bool(value) if isinstance(value, bool) else default

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(self.get(key, default))
        except (TypeError, ValueError):
            return default

    def set(self, key: str, value: Any) -> None:
        with self.db.session() as session:
            row = session.get(Setting, key)
            if row is None:
                session.add(Setting(key=key, value_json=json.dumps(value)))
            else:
                row.value_json = json.dumps(value)

    def set_many(self, values: dict[str, Any]) -> None:
        with self.db.session() as session:
            for key, value in values.items():
                row = session.get(Setting, key)
                if row is None:
                    session.add(Setting(key=key, value_json=json.dumps(value)))
                else:
                    row.value_json = json.dumps(value)
