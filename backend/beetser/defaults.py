"""Default values for user-tunable settings."""

from __future__ import annotations

from typing import Any

DEFAULT_SETTINGS: dict[str, Any] = {
    # Import behaviour
    "import_mode": "move",  # move | copy
    "path_format": "$albumartist/$album%aunique{}/$track $title",
    "comp_path_format": "Compilations/$album%aunique{}/$track $title",
    "singleton_path_format": "Singletons/$artist/$title",
    "write_tags": True,
    "delete_empty_dirs": True,
    # Tagging
    "auto_tag_enabled": True,
    "auto_tag_threshold": 0.85,
    "auto_tag_min_gap": 0.03,
    "fetch_art": True,
    "embed_art": False,
    # Scanning
    "settle_seconds": 30,
    "scan_interval_seconds": 300,
    "include_singletons": True,
    # Notifications
    "notify_webhook_url": "",
    "notify_on_review": True,
    "notify_on_import": False,
    "notify_on_error": True,
    # Advanced
    "ignore_globs": [".*", "*~", "Thumbs.db", ".DS_Store"],
    "ignore_dirs": [
        "@eaDir",
        "#recycle",
        "#snapshot",
        "lost+found",
        "System Volume Information",
    ],
}

# Settings that must never be exposed or overwritten through the generic
# settings endpoint.
PROTECTED_SETTINGS = {"admin_password_hash", "setup_completed"}

# Validation bounds for numeric settings.
NUMERIC_BOUNDS: dict[str, tuple[float, float]] = {
    "auto_tag_threshold": (0.0, 1.0),
    "auto_tag_min_gap": (0.0, 1.0),
    "settle_seconds": (0, 86400),
    "scan_interval_seconds": (10, 86400),
}
