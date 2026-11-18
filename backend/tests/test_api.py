from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from beetser.app import create_app
from beetser.settings import Settings


def test_status_and_auth_required(app):
    with TestClient(app) as client:
        status = client.get("/api/auth/status").json()
        assert status == {"authenticated": False, "setup_required": True}
        assert client.get("/api/origins").status_code == 401
        assert client.get("/api/system/health").status_code == 200


def test_setup_login_logout(app):
    with TestClient(app) as client:
        assert client.post("/api/auth/setup", json={"password": "short"}).status_code == 422
        assert client.post("/api/auth/setup", json={"password": "longenough"}).status_code == 200
        assert client.get("/api/origins").status_code == 200
        client.post("/api/auth/logout")
        assert client.get("/api/origins").status_code == 401
        assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
        assert client.post("/api/auth/login", json={"password": "longenough"}).status_code == 200
        assert client.get("/api/origins").status_code == 200


def test_origin_crud_and_validation(client, tmp_path: Path):
    root = tmp_path / "incoming"
    root.mkdir()

    assert client.post("/api/origins", json={"name": "Bad", "path": "relative"}).status_code == 422
    assert client.post("/api/origins", json={"name": "Bad", "path": str(tmp_path / "nope")}).status_code == 400

    created = client.post("/api/origins", json={"name": "Downloads", "path": str(root)})
    assert created.status_code == 201
    origin = created.json()
    assert origin["path"] == str(root)
    assert origin["destination"] == str(root)
    assert origin["effective_import_mode"] == "move"

    nested = root / "nested"
    nested.mkdir()
    conflict = client.post("/api/origins", json={"name": "Nested", "path": str(nested)})
    assert conflict.status_code == 409

    updated = client.patch(f"/api/origins/{origin['id']}", json={"name": "Renamed", "import_mode": "copy"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed"
    assert updated.json()["effective_import_mode"] == "copy"

    assert client.delete(f"/api/origins/{origin['id']}").status_code == 204
    assert client.get("/api/origins").json()["origins"] == []


def test_settings_validation(client):
    assert client.patch("/api/settings", json={"values": {"nope": 1}}).status_code == 400
    assert (
        client.patch("/api/settings", json={"values": {"auto_tag_threshold": 2}}).status_code
        == 400
    )
    assert (
        client.patch("/api/settings", json={"values": {"admin_password_hash": "x"}}).status_code
        == 400
    )
    assert (
        client.patch("/api/settings", json={"values": {"import_mode": "sideways"}}).status_code
        == 400
    )
    response = client.patch(
        "/api/settings",
        json={"values": {"auto_tag_threshold": 0.9, "scan_interval_seconds": 120}},
    )
    assert response.status_code == 200
    assert response.json()["auto_tag_threshold"] == 0.9
    assert response.json()["scan_interval_seconds"] == 120


def test_library_is_empty_initially(client):
    stats = client.get("/api/library/stats").json()
    assert stats["albums"] == 0
    assert stats["tracks"] == 0
    assert client.get("/api/library/albums").json()["albums"] == []
    assert client.get("/api/library/singles").json()["tracks"] == []
    assert client.get("/api/library/albums/999").status_code == 404
    assert client.get("/api/library/albums/999/cover").status_code == 404


def test_job_endpoints_empty(client):
    assert client.get("/api/jobs").json()["jobs"] == []
    stats = client.get("/api/jobs/stats").json()
    assert stats["total"] == 0
    assert client.get("/api/jobs/nope").status_code == 404


def test_browse_and_info(client, tmp_path: Path):
    browse = client.get("/api/system/browse", params={"path": str(tmp_path)})
    assert browse.status_code == 200
    assert browse.json()["parent"] is not None
    assert client.get("/api/system/browse", params={"path": str(tmp_path / "missing")}).status_code == 400

    info = client.get("/api/system/info").json()
    assert info["beets_version"]
    assert info["library_exists"] is True

    logs = client.get("/api/system/logs").json()
    assert "logs" in logs


def test_password_change(client):
    assert (
        client.post(
            "/api/auth/password",
            json={"current_password": "wrong", "new_password": "anotherpass"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/password",
            json={"current_password": "testpassword", "new_password": "anotherpass"},
        ).status_code
        == 200
    )
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"password": "anotherpass"}).status_code == 200


def test_env_password_is_accepted(settings: Settings):
    settings.password = "fromenv123"
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/auth/status").json()["setup_required"] is False
        assert client.post("/api/auth/login", json={"password": "fromenv123"}).status_code == 200
