"""Every request body has a size limit before a route reads it (security issue #37)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from app.core.middleware import MAX_REQUEST_BYTES


def _chunks(total: int, size: int = 64 * 1024) -> Iterator[bytes]:
    sent = 0
    while sent < total:
        part = min(size, total - sent)
        sent += part
        yield b" " * part


def test_a_declared_body_above_the_limit_is_refused_without_login(client: Any) -> None:
    body = b"[" + b"1," * (MAX_REQUEST_BYTES // 2) + b"1]"
    response = client.post("/api/v1/pokemon/compare", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert response.json()["error"]["data"] == {"context": "request"}
    # A refused body still gets the security headers.
    assert response.headers["x-content-type-options"] == "nosniff"


def test_a_streamed_body_above_the_limit_is_refused(client: Any) -> None:
    response = client.post(
        "/api/v1/auth/login",
        content=_chunks(MAX_REQUEST_BYTES + 1),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_a_normal_request_is_not_affected(client: Any) -> None:
    response = client.post("/api/v1/auth/login", json={"username": "niemand", "password": "x" * 12})
    assert response.status_code == 401


def test_the_webhook_and_uploads_keep_their_own_limit(client: Any) -> None:
    large = b" " * (MAX_REQUEST_BYTES + 1024)
    webhook = client.post("/api/v1/ingest/pgsharp/oakwh_onbekend_token", content=large)
    assert webhook.status_code != 413  # an unknown token, not a size problem
    upload = client.post("/api/v1/imports/upload", content=large, headers={"Content-Type": "multipart/form-data"})
    assert upload.status_code == 401  # the login check comes first; the upload limit is OAK_MAX_IMPORT_MB
