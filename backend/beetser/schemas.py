"""Pydantic request/response models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ImportMode = Literal["inherit", "move", "copy"]
AutoTagMode = Literal["inherit", "enabled", "disabled"]


class LoginRequest(BaseModel):
    password: str


class SetupRequest(BaseModel):
    password: str = Field(min_length=8)


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class OriginCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    path: str = Field(min_length=1)
    destination: str | None = None
    import_mode: ImportMode = "inherit"
    path_format: str | None = None
    singleton_path_format: str | None = None
    auto_tag: AutoTagMode = "inherit"
    auto_tag_threshold: float | None = Field(default=None, ge=0, le=1)
    settled_seconds: int | None = Field(default=None, ge=0, le=86400)
    watch: bool = True
    enabled: bool = True
    include_singletons: bool = True
    notes: str | None = None

    @field_validator("path", "destination")
    @classmethod
    def _absolute(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value.startswith("/"):
            raise ValueError("Path must be absolute")
        return value.rstrip("/") or "/"


class OriginUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    path: str | None = None
    destination: str | None = None
    import_mode: ImportMode | None = None
    path_format: str | None = None
    singleton_path_format: str | None = None
    auto_tag: AutoTagMode | None = None
    auto_tag_threshold: float | None = Field(default=None, ge=0, le=1)
    settled_seconds: int | None = Field(default=None, ge=0, le=86400)
    watch: bool | None = None
    enabled: bool | None = None
    include_singletons: bool | None = None
    notes: str | None = None

    @field_validator("path", "destination")
    @classmethod
    def _absolute(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value.startswith("/"):
            raise ValueError("Path must be absolute")
        return value.rstrip("/") or "/"


class OriginTestRequest(BaseModel):
    path: str | None = None
    destination: str | None = None


class ApplyRequest(BaseModel):
    mode: Literal["candidate", "asis", "manual", "reanalyze", "retry", "skip"]
    release_id: str | None = None
    fields: dict[str, str] = Field(default_factory=dict)
    tracks: dict[str, dict[str, Any]] = Field(default_factory=dict)
    force: bool = False


class AlbumUpdate(BaseModel):
    fields: dict[str, str] = Field(default_factory=dict)
    tracks: dict[int, dict[str, str]] = Field(default_factory=dict)
    write_tags: bool = True
    move_files: bool = True


class SettingsUpdate(BaseModel):
    values: dict[str, Any]


class BrowseEntry(BaseModel):
    name: str
    path: str
    is_dir: bool = True
