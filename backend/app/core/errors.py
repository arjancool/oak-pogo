"""Application errors and their HTTP representation.

Every error response has the same shape: ``{"error": {"code", "message", "details", "data"}}``.
The code is stable and machine-readable; the message is Dutch and meant for the user.

The interface shows the message in the chosen language (ADR-0025): its catalog has a text per code
under ``server.errors``, and ``data`` holds every value that appears in the message. A code that is
raised with more than one message gets a ``context`` per message, sent as ``data.context``, so each
message has its own text (``server.errors.<CODE>_<context>``). Without a text in the catalog the
interface shows the Dutch message. ``details`` keeps the machine-readable extras, such as the
seconds until a retry.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code = 400
    code = "BAD_REQUEST"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        context: str | None = None,
        data: dict[str, Any] | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.context = context
        self.data = data or {}
        self.details = details

    def to_payload(self) -> dict[str, Any]:
        data = {**self.data, "context": self.context} if self.context else dict(self.data)
        return {"error": {"code": self.code, "message": self.message, "details": self.details, "data": data}}


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "PAYLOAD_TOO_LARGE"


class UnsupportedMediaError(AppError):
    status_code = 415
    code = "UNSUPPORTED_MEDIA_TYPE"


class ValidationFailedError(AppError):
    status_code = 422
    code = "VALIDATION_FAILED"


class RateLimitedError(AppError):
    status_code = 429
    code = "RATE_LIMITED"

    def __init__(self, message: str, *, retry_after: int, context: str | None = None) -> None:
        super().__init__(message, context=context, details={"retry_after_seconds": retry_after})
        self.retry_after = retry_after


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "SERVICE_UNAVAILABLE"
