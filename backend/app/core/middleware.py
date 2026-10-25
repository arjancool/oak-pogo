"""Security headers and request logging (spec §21.4, §26.1)."""

from __future__ import annotations

import logging
import time
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.logging import redact

log = logging.getLogger("oak.http")
HSTS_SECONDS = 31_536_000


def content_security_policy(sprite_template: str) -> str:
    img_sources = ["'self'", "data:", "blob:"]
    if sprite_template:
        parsed = urlparse(sprite_template)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            img_sources.append(f"{parsed.scheme}://{parsed.netloc}")
    return "; ".join(
        [
            "default-src 'self'",
            f"img-src {' '.join(img_sources)}",
            "script-src 'self'",
            "style-src 'self' 'unsafe-inline'",
            "font-src 'self' data:",
            "connect-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
    )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, https: bool, csp_provider: object) -> None:
        super().__init__(app)
        self.https = https
        self.csp_provider = csp_provider

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        # no-referrer keeps the webhook URL, which contains a secret, out of Referer headers.
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        headers.setdefault("Content-Security-Policy", self.csp_provider())  # type: ignore[operator]
        if self.https:
            headers.setdefault("Strict-Transport-Security", f"max-age={HSTS_SECONDS}")
        if request.url.path.startswith("/api/"):
            headers.setdefault("Cache-Control", "no-store")
        return response


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        path = request.url.path
        if not path.startswith("/health") and not path.startswith("/assets/"):
            log.info(
                "request",
                extra={
                    "method": request.method,
                    "path": redact(path),
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                },
            )
        return response
