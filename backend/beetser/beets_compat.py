"""Compatibility patches for the beets library.

beets 2.14 stores item paths *relative* to the configured library directory.
Beetser keeps a single central library while each origin imports into its own
destination, so relative paths are ambiguous. Storing absolute paths is
backwards compatible (beets reads absolute paths unchanged) and keeps the
central database coherent.
"""

from __future__ import annotations

_installed = False


def install_absolute_path_patch() -> None:
    """Disable beets' path relativisation against the library directory."""
    global _installed
    if _installed:
        return

    from beets.dbcore import pathutils

    pathutils.normalize_path_for_db = lambda path: path  # type: ignore[assignment]

    # migrations imported the function directly; keep it consistent too.
    from beets.library import migrations

    migrations.normalize_path_for_db = lambda path: path  # type: ignore[assignment]

    _installed = True
