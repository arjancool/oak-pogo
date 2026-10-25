"""Container entrypoint: ``python -m app``.

Runs uvicorn with the port from ``OAK_PORT``. Uvicorn's access log stays off (request lines
could contain a webhook token; OAK logs requests itself, redacted) and so does its logging
setup, so every line goes through OAK's JSON logger. Forwarded headers are handled by OAK
itself, only for the proxies in ``OAK_TRUSTED_PROXY_CIDRS``.
"""

from __future__ import annotations

import uvicorn

from app.core.config import Settings

# Inside the container the app listens on every interface; Docker publishes the port.
LISTEN_HOST = "0.0.0.0"


def main() -> None:
    settings = Settings()
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=LISTEN_HOST,
        port=settings.port,
        access_log=False,
        log_config=None,
        proxy_headers=False,
        server_header=False,
    )


if __name__ == "__main__":
    main()
