"""Multipart uploads with a hard cap on the bytes received (audit A04).

Declaring ``UploadFile`` or ``Form`` parameters makes FastAPI parse the whole body before any
dependency runs, so the login check and the size limit would only apply after the upload was
already spooled to disk. Upload routes therefore take no body parameters, let their
dependencies check the user first, and then call :func:`bounded_form`.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Request
from starlette.datastructures import FormData, UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from app.core.errors import PayloadTooLargeError, UnsupportedMediaError, ValidationFailedError

# Room for the multipart boundaries, part headers and small form fields around the files.
MULTIPART_OVERHEAD = 64 * 1024
TOO_LARGE = "Het bestand is groter dan de ingestelde limiet."


class _TooLarge(MultiPartException):
    """Raised from the body stream, so the parser closes its temporary files before stopping."""


async def bounded_form(request: Request, limit: int, *, max_files: int, max_fields: int = 10) -> FormData:
    """Parse a multipart body of at most ``limit`` bytes plus a small overhead."""
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data"):
        raise UnsupportedMediaError("Verwacht een upload als multipart/form-data.", context="multipart_required")
    cap = limit + MULTIPART_OVERHEAD
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > cap:
        raise PayloadTooLargeError(TOO_LARGE, context="file")

    async def stream() -> AsyncGenerator[bytes]:
        received = 0
        async for chunk in request.stream():
            received += len(chunk)
            if received > cap:
                raise _TooLarge(TOO_LARGE)
            yield chunk

    parser = MultiPartParser(request.headers, stream(), max_files=max_files, max_fields=max_fields)
    try:
        return await parser.parse()
    except _TooLarge as exc:
        raise PayloadTooLargeError(TOO_LARGE, context="file") from exc
    except MultiPartException as exc:
        raise ValidationFailedError(
            f"De upload is ongeldig: {exc.message}", context="upload", data={"reason": exc.message}
        ) from exc


def form_file(form: FormData, name: str) -> UploadFile | None:
    value = form.get(name)
    return value if isinstance(value, UploadFile) else None


def form_text(form: FormData, name: str) -> str | None:
    value = form.get(name)
    return value if isinstance(value, str) else None
