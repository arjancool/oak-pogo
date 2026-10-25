"""PGSharp webhook (spec §4.2). Authenticated by the token in the URL, because PGSharp cannot
send headers. The token is never logged (see app/core/logging.py)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.deps import get_container
from app.auth.tokens import constant_time_equal, parse_webhook_token, sha256_hex
from app.core.container import Container
from app.core.errors import NotFoundError, PayloadTooLargeError, RateLimitedError
from app.ingestion.receive import IncomingPayload, create_import_job, decode_payload, is_connection_test
from app.models import TrainerAccount, WebhookCredential

router = APIRouter(prefix="/ingest", tags=["ingest"])
log = logging.getLogger("oak.ingest")


async def read_limited_body(request: Request, max_bytes: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > max_bytes:
        raise PayloadTooLargeError("De export is groter dan de ingestelde limiet.")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > max_bytes:
            raise PayloadTooLargeError("De export is groter dan de ingestelde limiet.")
        chunks.append(chunk)
    return b"".join(chunks)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/pgsharp/{token}", status_code=202)
async def pgsharp_webhook(token: str, request: Request, container: Container = Depends(get_container)) -> JSONResponse:
    ip = _client_ip(request)
    blocked = container.webhook_invalid_by_ip.blocked(f"ip:{ip}")
    if blocked:
        raise RateLimitedError("Te veel ongeldige verzoeken.", retry_after=blocked)
    identifier = parse_webhook_token(token)
    credential = await run_in_threadpool(_find_credential, container, identifier, token)
    if credential is None:
        container.webhook_invalid_by_ip.hit(f"ip:{ip}")
        log.warning("webhook with unknown token", extra={"client": ip})
        raise NotFoundError("Onbekende webhook.", code="UNKNOWN_WEBHOOK")
    credential_id, account_id = credential
    retry = container.webhook_by_token.hit(f"wh:{credential_id}")
    if retry:
        raise RateLimitedError("Te veel exports in korte tijd voor deze webhook.", retry_after=retry)

    body = await read_limited_body(request, container.settings.max_import_bytes)
    incoming = IncomingPayload(
        body=body,
        source="webhook",
        content_type=request.headers.get("content-type"),
        content_encoding=request.headers.get("content-encoding"),
        user_agent=request.headers.get("user-agent"),
        method=request.method,
        header_names=list(request.headers.keys()),
    )
    result = await run_in_threadpool(_accept, container, credential_id, account_id, incoming)
    if result["status"] == "connection_test":
        return JSONResponse(result, status_code=200)
    container.runner.notify()
    status_code = 202 if result["status"] in ("queued", "duplicate") else 400
    return JSONResponse(result, status_code=status_code)


def _find_credential(container: Container, identifier: str | None, token: str) -> tuple[int, int] | None:
    if identifier is None:
        return None
    with container.db.transaction() as session:
        cred = session.scalars(
            select(WebhookCredential).where(
                WebhookCredential.token_identifier == identifier,
                WebhookCredential.status == "active",
            )
        ).first()
        if cred is None or not constant_time_equal(cred.token_hash, sha256_hex(token)):
            return None
        return cred.id, cred.trainer_account_id


def _accept(container: Container, credential_id: int, account_id: int, incoming: IncomingPayload) -> dict[str, Any]:
    decoded = decode_payload(incoming, container.settings.max_import_bytes)
    with container.db.transaction() as session:
        account = session.get(TrainerAccount, account_id)
        cred = session.get(WebhookCredential, credential_id)
        if account is None or cred is None:
            raise NotFoundError("Onbekende webhook.", code="UNKNOWN_WEBHOOK")
        now = container.clock.now()
        cred.last_used_at = now
        if is_connection_test(decoded):
            log.info(
                "webhook connection test",
                extra={
                    "account_id": account.id,
                    "method": incoming.method,
                    "content_type": incoming.content_type,
                    "bytes": len(decoded.text_bytes),
                },
            )
            return {
                "status": "connection_test",
                "message": "De verbinding met OAK werkt. Een testverzoek wordt niet geïmporteerd.",
            }
        diagnostics = account.diagnostics_until is not None and account.diagnostics_until > now
        job = create_import_job(
            session,
            account=account,
            user_id=None,
            incoming=incoming,
            decoded=decoded,
            secret=container.secret,
            imports_dir=container.settings.imports_dir,
            now=now,
            detailed_structure=diagnostics,
        )
        return {
            "import_id": job.id,
            "status": job.status,
            "error": job.error_code,
            "message": job.error_message,
        }
