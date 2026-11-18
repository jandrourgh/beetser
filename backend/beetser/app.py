"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from . import __version__
from .api import api_router
from .beets_engine import BeetsEngine
from .db import Database
from .events import EventBus
from .jobs import ImportService
from .logging_setup import configure_logging
from .notify import Notifier
from .security import AuthService, load_or_create_secret
from .settings import Settings, load_settings
from .settings_store import SettingsStore

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.ensure_dirs()
        db = Database(settings)
        db.create_all()

        store = SettingsStore(db)
        store.ensure_defaults(
            {"scan_interval_seconds": settings.scan_interval}
        )

        secret = load_or_create_secret(settings.secret_file, settings.secret_key)
        auth = AuthService(
            store,
            env_password=settings.password,
            env_password_hash=settings.password_hash,
            secret=secret,
            max_age=settings.session_max_age,
            cookie_secure=settings.secure_cookies,
        )

        engine = BeetsEngine(settings, store)
        bus = EventBus()
        notifier = Notifier(store)
        service = ImportService(settings, db, store, engine, bus, notifier)

        app.state.settings = settings
        app.state.db = db
        app.state.store = store
        app.state.auth = auth
        app.state.engine = engine
        app.state.bus = bus
        app.state.notifier = notifier
        app.state.service = service

        await service.start()
        try:
            yield
        finally:
            await service.stop()

    app = FastAPI(
        title="Beetser",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )

    app.include_router(api_router)

    static_dir = settings.static_dir
    if not static_dir.is_absolute():
        static_dir = Path.cwd() / static_dir
    app.state.static_dir = static_dir
    index = static_dir / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(404, "Not found")
        candidate = static_dir / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        if full_path and Path(full_path).suffix and not candidate.is_file():
            raise HTTPException(404, "Not found")
        if index.is_file():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return JSONResponse(
            {
                "name": "Beetser",
                "version": __version__,
                "message": "Frontend assets are not built. Run `npm run build` in frontend/, "
                "or use the API at /api/docs.",
            }
        )

    return app

