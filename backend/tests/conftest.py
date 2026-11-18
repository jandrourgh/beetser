from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from beetser.app import create_app
from beetser.db import Database
from beetser.settings import Settings
from beetser.settings_store import SettingsStore


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    settings = Settings(
        data_dir=tmp_path / "config",
        library_db=tmp_path / "config" / "library.db",
        static_dir=tmp_path / "static",
        log_level="WARNING",
        scan_interval=3600,
    )
    settings.ensure_dirs()
    return settings


@pytest.fixture
def db(settings: Settings) -> Database:
    database = Database(settings)
    database.create_all()
    return database


@pytest.fixture
def store(db: Database) -> SettingsStore:
    store = SettingsStore(db)
    store.ensure_defaults()
    store.set("settle_seconds", 0)
    store.set("fetch_art", False)
    return store


@pytest.fixture
def engine(db, store, settings):
    from beetser.beets_engine import BeetsEngine

    return BeetsEngine(settings, store)


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/auth/setup", json={"password": "testpassword"}
        )
        assert response.status_code == 200
        test_client.patch(
            "/api/settings",
            json={
                "values": {
                    "settle_seconds": 0,
                    "fetch_art": False,
                    "auto_tag_enabled": False,
                }
            },
        )
        yield test_client


