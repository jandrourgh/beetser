"""Process-level configuration (environment variables)."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration that comes from the environment.

    Everything here is deployment-level. User-tunable behaviour lives in the
    ``app_settings`` database table (see :mod:`beetser.defaults`).
    """

    model_config = SettingsConfigDict(
        env_prefix="BEETSER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Path("/config")
    library_db: Path | None = None
    static_dir: Path = Path("static")

    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"

    # Authentication. Prefer `password_hash`; `password` is accepted for
    # convenience and is hashed on first startup.
    password: str | None = None
    password_hash: str | None = None
    secret_key: str | None = None
    session_max_age: int = 14 * 24 * 3600
    secure_cookies: bool = False

    scan_interval: int = 300
    import_timeout: int = 900

    musicbrainz_user_agent: str | None = None

    @property
    def library_path(self) -> Path:
        return self.library_db or self.data_dir / "library.db"

    @property
    def beets_dir(self) -> Path:
        return self.data_dir / "beets"

    @property
    def origin_config_dir(self) -> Path:
        return self.beets_dir / "origins"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "beetser.db"

    @property
    def secret_file(self) -> Path:
        return self.data_dir / "secret.key"

    def ensure_dirs(self) -> None:
        for path in (
            self.data_dir,
            self.beets_dir,
            self.origin_config_dir,
            self.library_path.parent,
        ):
            path.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}
