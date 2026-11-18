"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from ..beets_engine import BeetsEngine
from ..db import Database
from ..events import EventBus
from ..jobs import ImportService
from ..security import AuthService
from ..settings import Settings
from ..settings_store import SettingsStore


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_store(request: Request) -> SettingsStore:
    return request.app.state.store


def get_engine(request: Request) -> BeetsEngine:
    return request.app.state.engine


def get_bus(request: Request) -> EventBus:
    return request.app.state.bus


def get_service(request: Request) -> ImportService:
    return request.app.state.service


def get_auth(request: Request) -> AuthService:
    return request.app.state.auth


def is_secure_request(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", "")
    return (
        request.app.state.settings.secure_cookies
        or request.url.scheme == "https"
        or proto.split(",")[0].strip() == "https"
    )


def require_auth(request: Request) -> None:
    auth: AuthService = request.app.state.auth
    token = request.cookies.get(auth.cookie_name)
    if not auth.validate_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )


def client_id(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
