"""CLI entrypoint used for subprocess imports.

Running ``python -m beetser.beets_cli`` is equivalent to ``beet`` but keeps
paths absolute in the central library database (see beets_compat).
"""

from __future__ import annotations

import sys

from .beets_compat import install_absolute_path_patch


def main() -> int:
    install_absolute_path_patch()
    from beets.ui import main as beets_main

    result = beets_main()
    return int(result) if isinstance(result, int) else 0


if __name__ == "__main__":
    sys.exit(main())
