"""Receiving an export, from the webhook or an upload, and turning it into a durable import job
(spec §4.6, steps 1–8). Webhook and upload share this module and everything after it.

Reading, summarizing, filtering and storing an export takes the most time and memory, so it
happens before the write transaction (``prepare_import``). The transaction only checks for a
duplicate and adds the job.
"""

from __future__ import annotations

import gzip
import hashlib
import hmac
import json
import logging
import math
import re
import uuid
import zlib
from collections.abc import Iterator
from contextlib import contextmanager
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
# Limits on the structure of an export, so reading one never costs much more memory than its size.
# They are far above a real export: one with about 1,000 Pokémon has some 8,400 objects and lists,
# 100,000 values, 9 levels and at most 82 fields in an object.
MAX_POKEMON_RECORDS = 25_000
MAX_CONTAINERS = 500_000
MAX_VALUES = 4_000_000
MAX_DEPTH = 32
MAX_KEYS = 1_000
STRUCTURE_MESSAGES = {
    "pokemons": "De export bevat meer dan {max} Pokémon-records.",
    "containers": "De export bevat meer dan {max} objecten en lijsten.",
    "values": "De export bevat meer dan {max} waarden.",
    "depth": "De export is dieper genest dan {max} niveaus.",
    "keys": "Een object in de export heeft meer dan {max} velden.",
    "number": "Een getal in de export heeft meer dan {max} cijfers.",
}
# Python's own limit on the digits of a number it reads (sys.get_int_max_str_digits).
MAX_NUMBER_DIGITS = 4300
_JSON_STRING = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"')


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
    too_large = _count_problem(text)
    if too_large:
        return _structure_rejected(body, meta, too_large)
    try:
        data = json.loads(text, parse_constant=_not_finite, parse_float=_finite_float)
    except NonFiniteNumberError:
        return DecodedPayload(
            body, None, "NUMBER_INVALID", "De export bevat een getal dat niet eindig is, zoals NaN of Infinity.", meta
        )
    except json.JSONDecodeError as exc:
        return DecodedPayload(
            body,
            None,
            "INVALID_JSON",
            f"Ongeldige JSON op regel {exc.lineno}, kolom {exc.colno}.",
            meta,
            {"line": exc.lineno, "column": exc.colno},
        )
    except RecursionError:
        return _structure_rejected(body, meta, "depth")
    except ValueError:
        return _structure_rejected(body, meta, "number")
    too_large = _shape_problem(data)
    if too_large == "text":
        # Valid JSON can still hold a lone surrogate ("\ud800"), which no file or database can
        # store as UTF-8 (issue #47).
        return DecodedPayload(
            body,
            None,
            "ENCODING_INVALID",
            "De export bevat tekst met een ongeldig teken.",
            meta,
            {"charset": "utf-8", "context": "character"},
        )
    if too_large:
        return _structure_rejected(body, meta, too_large)
    return DecodedPayload(body, data, None, None, meta)


class NonFiniteNumberError(ValueError):
    """NaN, Infinity or a number too large for a float: not a value an export can hold."""


def _not_finite(name: str) -> float:
    raise NonFiniteNumberError(name)


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise NonFiniteNumberError(text)
    return value


def _valid_text(value: str) -> bool:
    if value.isascii():
        return True
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _structure_rejected(body: bytes, meta: dict[str, Any], context: str) -> DecodedPayload:
    limit = {
        "pokemons": MAX_POKEMON_RECORDS,
        "containers": MAX_CONTAINERS,
        "values": MAX_VALUES,
        "depth": MAX_DEPTH,
        "keys": MAX_KEYS,
        "number": MAX_NUMBER_DIGITS,
    }[context]
    message = STRUCTURE_MESSAGES[context].format(max=f"{limit:,}".replace(",", "."))
    return DecodedPayload(body, None, "STRUCTURE_TOO_LARGE", message, meta, {"context": context, "max": limit})


def _count_problem(text: str) -> str | None:
    """Count objects, lists and values before parsing, because parsing makes every '{}' a full
    dictionary. The quick count includes brackets and commas inside strings, so it is never too
    low. Only when it is over a limit does OAK count again without the strings."""
    containers = text.count("{") + text.count("[")
    values = text.count(",") + containers + 1
    if containers > MAX_CONTAINERS or values > MAX_VALUES:
        bare = _JSON_STRING.sub('""', text)
        containers = bare.count("{") + bare.count("[")
        values = bare.count(",") + containers + 1
    if containers > MAX_CONTAINERS:
        return "containers"
    if values > MAX_VALUES:
        return "values"
    return None


def _shape_problem(data: Any) -> str | None:
    """Depth, fields per object, text that cannot be stored and Pokémon records, checked
    without recursion."""
    if isinstance(data, str):
        return None if _valid_text(data) else "text"
    stack: list[tuple[Any, int]] = [(data, 1)]
    while stack:
        node, depth = stack.pop()
        if depth > MAX_DEPTH:
            return "depth"
        if isinstance(node, dict):
            if len(node) > MAX_KEYS:
                return "keys"
            if not all(_valid_text(key) for key in node):
                return "text"
            children: Any = node.values()
        elif isinstance(node, list):
            children = node
        else:
            continue
        for child in children:
            if isinstance(child, dict | list):
                stack.append((child, depth + 1))
            elif isinstance(child, str) and not _valid_text(child):
                return "text"
    records = data.get("pokemons") if isinstance(data, dict) else None
    if isinstance(records, list) and len(records) > MAX_POKEMON_RECORDS:
        return "pokemons"
    return None


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
    """Write through a temporary file, so a reader sees either the old or the new export. A
    write that fails, for example on a full disk, leaves no temporary file behind."""
    tmp = imports_dir / f".{file_name}.tmp"
    try:
        with gzip.open(tmp, "wb", compresslevel=6) as handle:
            handle.write(json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        tmp.replace(imports_dir / file_name)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


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


@dataclass(slots=True)
class PreparedImport:
    """The work on an export that needs no database. ``payload_file`` is the filtered copy on
    disk; it stays only when a queued job uses it."""

    digest: str
    summary: dict[str, Any] | None = None
    fingerprint: str | None = None
    payload_file: str | None = None
    used: bool = False


@contextmanager
def prepare_import(
    decoded: DecodedPayload, *, secret: str, imports_dir: Path, detailed_structure: bool = False
) -> Iterator[PreparedImport]:
    """Summarize, filter and store the export before the write transaction starts. Open the
    transaction inside this block: when it fails, or the export turns out to be a duplicate, the
    stored copy is removed again."""
    prepared = PreparedImport(digest=hashlib.sha256(decoded.text_bytes).hexdigest())
    if decoded.data is not None:
        summary = summarize_structure(
            decoded.data, max_list_samples=DIAGNOSTIC_LIST_SAMPLES if detailed_structure else None
        )
        if detailed_structure:
            summary["diagnostics"] = True
        prepared.summary = summary
        prepared.fingerprint = fingerprint_for(secret, player_identifier(decoded.data))
        prepared.payload_file = store_payload(imports_dir, sanitize_export(decoded.data))
    try:
        yield prepared
    except BaseException:
        _discard(imports_dir, prepared)
        raise
    if not prepared.used:
        _discard(imports_dir, prepared)


def _discard(imports_dir: Path, prepared: PreparedImport) -> None:
    if prepared.payload_file:
        (imports_dir / prepared.payload_file).unlink(missing_ok=True)


def create_import_job(
    session: Session,
    *,
    account: TrainerAccount,
    user_id: int | None,
    incoming: IncomingPayload,
    decoded: DecodedPayload,
    prepared: PreparedImport,
    now: datetime,
) -> ImportJob:
    digest = prepared.digest
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

    job.schema_summary = prepared.summary
    job.fingerprint = prepared.fingerprint

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

    job.payload_file = prepared.payload_file
    prepared.used = True
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
