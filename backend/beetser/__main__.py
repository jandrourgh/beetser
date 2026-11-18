"""Run the Beetser web server."""

from __future__ import annotations

import uvicorn

from .settings import load_settings


def main() -> None:
    settings = load_settings()
    uvicorn.run(
        "beetser.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        workers=1,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
