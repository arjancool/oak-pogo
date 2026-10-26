"""Receiving an export, from the webhook or an upload, and turning it into a durable import job
(spec §4.6, steps 1–8). Webhook and upload share this module and everything after it.
"""

from __future__ import annotations

import gzip
import hashlib
import hmac
import json
import logging
import re
import uuid
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import PayloadTooLargeError, UnsupportedMediaError
from app.models import BackgroundJob, ImportJob, TrainerAccount
from app.normalizers.pgsharp import player_identifier
from app.normalizers.sanitize import sanitize_export
from app.normalizers.schema import summarize_structure

log = logging.getLogger("oak.ingest")
GZIP_MAGIC = b"\x1f\x8b"
APPLIED_STATUSES = ("succeeded", "partial")
SAFE_HEADER_VALUES = (
    "content-type",
    "content-encoding",
    "content-length",
    "user-agent",
    "transfer-encoding",
)
MAX_FILENAME = 120
DIAGNOSTIC_LIST_SAMPLES = 20_000
# A real export always has a 'pokemons' list and is far larger than this. Smaller requests
# without one are a connection test, such as PGSharp's "Test Connection" button.
CONNECTION_TEST_MAX_BYTES = 4096
CONNECTION_TEST_ERRORS = ("EMPTY_BODY", "MULTIPART_WITHOUT_FILE", "INVALID_JSON")


@dataclass(slots=True)
class IncomingPayload:
    body: bytes
    source: str  # webhook | upload
    content_type: str | None = None
    content_encoding: str | None = None
    user_agent: str | None = None
    method: str = "POST"
    header_names: list[str] = field(default_factory=list)
    filename: str | None = None


@dataclass(frozen=True, slots=True)
class DecodedPayload:
    text_bytes: bytes
    data: Any | None
    error_code: str | None
    error_message: str | None
    meta: dict[str, Any]
    # The values in ``error_message``, for the interface in another language (ADR-0025).
    error_data: dict[str, Any] = field(default_factory=dict)


def decode_payload(payload: IncomingPayload, max_bytes: int) -> DecodedPayload:
    """Undo transport encodings and parse JSON. Never raises for bad content, only for
    requests OAK cannot accept at all (too large, unsupported encoding)."""
    meta: dict[str, Any] = {
        "method": payload.method,
        "content_type": payload.content_type,
        "content_encoding": payload.content_encoding,
        "user_agent": (payload.user_agent or "")[:200] or None,
        "received_bytes": len(payload.body),
        "header_names": sorted({h.lower() for h in payload.header_names})[:60],
    }
    body = payload.body
    encoding = (payload.content_encoding or "").lower().strip()
    compressed = encoding in ("gzip", "x-gzip") or body[:2] == GZIP_MAGIC
    if encoding and encoding not in ("gzip", "x-gzip", "deflate", "identity"):
        raise UnsupportedMediaError(
            f"Content-Encoding '{encoding}' wordt niet ondersteund.", context="encoding", data={"encoding": encoding}
        )
    if compressed:
        body = _bounded_decompress(body, max_bytes, wbits=31)
        meta["compression"] = "gzip"
    elif encoding == "deflate":
        body = _bounded_decompress(body, max_bytes, wbits=15)
        meta["compression"] = "deflate"
    if len(body) > max_bytes:
        raise PayloadTooLargeError("De export is groter dan de ingestelde limiet.", context="export")
    meta["decoded_bytes"] = len(body)

    content_type = (payload.content_type or "").lower()
    if content_type.startswith("multipart/form-data"):
        extracted = _first_multipart_file(body, payload.content_type or "")
        if extracted is None:
            return DecodedPayload(
                body,
                None,
                "MULTIPART_WITHOUT_FILE",
                "Het multipart-verzoek bevat geen bestand.",
                meta,
            )
        body = extracted
        meta["multipart"] = True

    charset = "utf-8"
    match = re.search(r"charset=([\w-]+)", content_type)
    if match:
        charset = match.group(1)
    meta["charset"] = charset
    if body.startswith(b"\xef\xbb\xbf"):
        meta["bom"] = True
        body = body[3:]
    try:
        text = body.decode(charset)
    except (UnicodeDecodeError, LookupError):
        return DecodedPayload(
            body,
            None,
            "ENCODING_INVALID",
            f"De inhoud is geen geldige {charset}-tekst.",
            meta,
            {"charset": charset},
        )
    if not text.strip():
        return DecodedPayload(body, None, "EMPTY_BODY", "Het verzoek bevat geen inhoud.", meta)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return DecodedPayload(
            body,
            None,
            "INVALID_JSON",
            f"Ongeldige JSON op regel {exc.lineno}, kolom {exc.colno}.",
            meta,
            {"line": exc.lineno, "column": exc.colno},
        )
    return DecodedPayload(body, data, None, None, meta)


def _bounded_decompress(body: bytes, max_bytes: int, *, wbits: int) -> bytes:
    decompressor = zlib.decompressobj(wbits)
    try:
        result = decompressor.decompress(body, max_bytes + 1)
    except zlib.error as exc:
        raise UnsupportedMediaError("De gecomprimeerde inhoud is beschadigd.", context="corrupt") from exc
    if len(result) > max_bytes or decompressor.unconsumed_tail:
        raise PayloadTooLargeError(
            "De uitgepakte export is groter dan de ingestelde limiet.", context="unpacked_export"
        )
    # A stream that stops before its end marker (and, for gzip, its checksum) is incomplete,
    # even when the part that arrived happens to be valid JSON (audit A07).
    if not decompressor.eof:
        raise UnsupportedMediaError(
            "De gecomprimeerde inhoud is onvolledig: het einde of de controlesom ontbreekt.", context="truncated"
        )
    if decompressor.unused_data.strip(b"\0"):
        raise UnsupportedMediaError(
            "Na de gecomprimeerde inhoud volgen nog onverwachte gegevens.", context="trailing_data"
        )
    return result


def _first_multipart_file(body: bytes, content_type: str) -> bytes | None:
    match = re.search(r'boundary="?([^";]+)"?', content_type)
    if not match:
        return None
    boundary = b"--" + match.group(1).encode("latin-1")
    for part in body.split(boundary):
        head, sep, content = part.partition(b"\r\n\r\n")
        if not sep:
            continue
        if b"filename=" in head or b"application/json" in head.lower():
            return content.removesuffix(b"\r\n").removesuffix(b"--")
    return None


def fingerprint_for(secret: str, identifier: str | None) -> str | None:
    if not identifier:
        return None
    return hmac.new(secret.encode(), b"pgsharp-player:" + identifier.encode(), hashlib.sha256).hexdigest()


def safe_filename(name: str | None) -> str | None:
    if not name:
        return None
    base = Path(name).name
    cleaned = re.sub(r"[^\w.\- ]", "_", base)[:MAX_FILENAME]
    return cleaned or None


def store_payload(imports_dir: Path, data: Any) -> str:
    """Write the sanitized export, gzip-compressed. Returns the file name."""
    file_name = f"{uuid.uuid4().hex}.json.gz"
    write_payload(imports_dir, file_name, data)
    return file_name


def write_payload(imports_dir: Path, file_name: str, data: Any) -> None:
    """Write through a temporary file, so a reader sees either the old or the new export."""
    tmp = imports_dir / f".{file_name}.tmp"
    with gzip.open(tmp, "wb", compresslevel=6) as handle:
        handle.write(json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    tmp.replace(imports_dir / file_name)


def load_payload(imports_dir: Path, file_name: str) -> Any:
    with gzip.open(imports_dir / file_name, "rb") as handle:
        return json.loads(handle.read())


def is_connection_test(decoded: DecodedPayload) -> bool:
    """A small request without an export. What PGSharp's "Test Connection" sends is not
    documented, so this accepts an empty body, plain text, form fields without a file and JSON
    without a 'pokemons' list. Text that starts like JSON but does not parse stays an error,
    because that looks like a broken export."""
    if len(decoded.text_bytes) > CONNECTION_TEST_MAX_BYTES:
        return False
    if decoded.data is None:
        if decoded.error_code not in CONNECTION_TEST_ERRORS:
            return False
        return decoded.error_code != "INVALID_JSON" or not decoded.text_bytes.lstrip().startswith((b"{", b"["))
    return not (isinstance(decoded.data, dict) and "pokemons" in decoded.data)


def create_import_job(
    session: Session,
    *,
    account: TrainerAccount,
    user_id: int | None,
    incoming: IncomingPayload,
    decoded: DecodedPayload,
    secret: str,
    imports_dir: Path,
    now: datetime,
    detailed_structure: bool = False,
) -> ImportJob:
    digest = hashlib.sha256(decoded.text_bytes).hexdigest()
    job = ImportJob(
        trainer_account_id=account.id,
        user_id=user_id,
        source=incoming.source,
        status="received",
        payload_sha256=digest,
        payload_size=len(decoded.text_bytes),
        filename=safe_filename(incoming.filename),
        request_meta=decoded.meta,
        received_at=now,
    )
    account.last_import_attempt_at = now
    if decoded.data is None:
        job.status = "rejected"
        job.error_code = decoded.error_code
        job.error_message = decoded.error_message
        job.error_data = decoded.error_data
        job.finished_at = now
        session.add(job)
        session.flush()
        log.info("import rejected", extra={"import_id": job.id, "code": decoded.error_code})
        return job

    summary = summarize_structure(
        decoded.data, max_list_samples=DIAGNOSTIC_LIST_SAMPLES if detailed_structure else None
    )
    if detailed_structure:
        summary["diagnostics"] = True
    job.schema_summary = summary
    job.fingerprint = fingerprint_for(secret, player_identifier(decoded.data))

    duplicate_of = session.scalar(
        select(ImportJob.id)
        .where(
            ImportJob.trainer_account_id == account.id,
            ImportJob.payload_sha256 == digest,
            ImportJob.status.in_(APPLIED_STATUSES),
        )
        .order_by(ImportJob.id.desc())
        .limit(1)
    )
    if duplicate_of is not None:
        job.status = "duplicate"
        job.classification = "duplicate"
        job.duplicate_of_id = duplicate_of
        job.finished_at = now
        session.add(job)
        session.flush()
        log.info("import duplicate", extra={"import_id": job.id, "duplicate_of": duplicate_of})
        return job

    job.payload_file = store_payload(imports_dir, sanitize_export(decoded.data))
    job.status = "queued"
    job.stage = "queued"
    session.add(job)
    session.flush()
    session.add(
        BackgroundJob(
            kind="import",
            status="queued",
            trainer_account_id=account.id,
            ref_id=job.id,
            created_at=now,
        )
    )
    log.info(
        "import queued",
        extra={
            "import_id": job.id,
            "account_id": account.id,
            "source": incoming.source,
            "bytes": job.payload_size,
        },
    )
    return job
