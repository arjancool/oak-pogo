"""Security headers, request logging and the request size limit (spec §21.4, §26.1)."""

from __future__ import annotations

import logging
import time

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import PayloadTooLargeError
from app.core.logging import redact
from app.core.sprites import sprite_origin

log = logging.getLogger("oak.http")
HSTS_SECONDS = 31_536_000


def content_security_policy(sprite_template: str) -> str:
    img_sources = ["'self'", "data:", "blob:"]
    # Built from the checked host and port, never from the raw text (issue #51).
    origin = sprite_origin(sprite_template)
    if origin:
        img_sources.append(origin)
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
        add_security_headers(response, request.url.path, https=self.https, csp=self.csp_provider())  # type: ignore[operator]
        return response


def add_security_headers(response: Response, path: str, *, https: bool, csp: str) -> None:
    """Also used for an error 500, which the error handler builds outside this middleware."""
    headers = response.headers
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("X-Frame-Options", "DENY")
    # no-referrer keeps the webhook URL, which contains a secret, out of Referer headers.
    headers.setdefault("Referrer-Policy", "no-referrer")
    headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
    headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    headers.setdefault("Content-Security-Policy", csp)
    if https:
        headers.setdefault("Strict-Transport-Security", f"max-age={HSTS_SECONDS}")
    if path.startswith("/api/"):
        headers.setdefault("Cache-Control", "no-store")


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


# Enough for every JSON request the interface sends. The webhook and the two uploads stream far
# larger bodies and check their own limit before they read it (audit A04, OAK_MAX_IMPORT_MB).
MAX_REQUEST_BYTES = 1024 * 1024
SIZE_LIMIT_EXEMPT = ("/api/v1/ingest/", "/api/v1/imports/upload", "/api/v1/gamedata/upload")


def request_too_large() -> PayloadTooLargeError:
    return PayloadTooLargeError("Het verzoek is groter dan toegestaan.", context="request")


class RequestBodyTooLarge(StarletteHTTPException):
    """Raised while a body is read. FastAPI passes an HTTP exception on unchanged."""

    def __init__(self) -> None:
        super().__init__(status_code=413)


class RequestSizeLimitMiddleware:
    """Refuse a request body above the limit before a route reads it (security issue #37).

    FastAPI reads and parses a JSON body before the login and rate-limit checks run, so without
    this a large body costs memory even when the request is refused afterwards. A declared length
    above the limit is refused at once; a streamed body is counted while it arrives.
    """

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_REQUEST_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or str(scope["path"]).startswith(SIZE_LIMIT_EXEMPT):
            await self.app(scope, receive, send)
            return
        declared = _content_length(scope)
        if declared is not None and declared > self.max_bytes:
            error = request_too_large()
            await JSONResponse(error.to_payload(), status_code=error.status_code)(scope, receive, send)
            return
        received = 0

        async def counted() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise RequestBodyTooLarge
            return message

        await self.app(scope, counted, send)


def _content_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", []):
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None
