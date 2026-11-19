"""Global settings endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..defaults import DEFAULT_SETTINGS, NUMERIC_BOUNDS, PROTECTED_SETTINGS
from ..events import EventBus
from ..schemas import SettingsUpdate
from ..settings_store import SettingsStore
from .deps import get_bus, get_store, require_auth

router = APIRouter(
    prefix="/settings", tags=["settings"], dependencies=[Depends(require_auth)]
)

BOOLEAN_KEYS = {
    "write_tags",
    "delete_empty_dirs",
    "auto_tag_enabled",
    "fetch_art",
    "embed_art",
    "include_singletons",
    "notify_on_review",
    "notify_on_import",
    "notify_on_error",
}
STRING_KEYS = {
    "path_format",
    "comp_path_format",
    "singleton_path_format",
    "notify_webhook_url",
}
LIST_KEYS = {"ignore_globs", "ignore_dirs"}


@router.get("")
def get_settings(store: SettingsStore = Depends(get_store)) -> dict:
    values = store.all()
    return {k: v for k, v in values.items() if k not in PROTECTED_SETTINGS}


@router.patch("")
def update_settings(
    payload: SettingsUpdate,
    store: SettingsStore = Depends(get_store),
    bus: EventBus = Depends(get_bus),
) -> dict:
    cleaned: dict[str, Any] = {}
    for key, value in payload.values.items():
        if key not in DEFAULT_SETTINGS or key in PROTECTED_SETTINGS:
            raise HTTPException(400, f"Unknown setting: {key}")
        if key in BOOLEAN_KEYS:
            if not isinstance(value, bool):
                raise HTTPException(400, f"{key} must be a boolean")
        elif key in NUMERIC_BOUNDS:
            low, high = NUMERIC_BOUNDS[key]
            try:
                number = float(value)
            except (TypeError, ValueError):
                raise HTTPException(400, f"{key} must be a number") from None
            if not low <= number <= high:
                raise HTTPException(400, f"{key} must be between {low} and {high}")
            value = int(number) if key in ("settle_seconds", "scan_interval_seconds") else number
        elif key == "import_mode":
            if value not in ("tag", "move", "copy"):
                raise HTTPException(400, "import_mode must be tag, move or copy")
        elif key in STRING_KEYS:
            if not isinstance(value, str):
                raise HTTPException(400, f"{key} must be a string")
            if key != "notify_webhook_url" and not value.strip():
                raise HTTPException(400, f"{key} must not be empty")
        elif key in LIST_KEYS:
            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                raise HTTPException(400, f"{key} must be a list of strings")
        cleaned[key] = value

    store.set_many(cleaned)
    bus.publish("settings")
    values = store.all()
    return {k: v for k, v in values.items() if k not in PROTECTED_SETTINGS}


@router.post("/reset")
def reset_settings(
    store: SettingsStore = Depends(get_store), bus: EventBus = Depends(get_bus)
) -> dict:
    store.set_many(DEFAULT_SETTINGS)
    bus.publish("settings")
    values = store.all()
    return {k: v for k, v in values.items() if k not in PROTECTED_SETTINGS}
