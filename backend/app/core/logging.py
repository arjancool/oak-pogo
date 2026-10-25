"""Structured JSON logging with redaction of webhook tokens.

Webhook tokens travel in the URL path because PGSharp cannot send headers. Every log record
passes through :class:`RedactingFilter`, which replaces the token segment before anything is
written. Request bodies are never logged.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

WEBHOOK_PATH_PATTERN = re.compile(r"(/api/v1/ingest/pgsharp/)[^/\s?\"']+")
TOKEN_PATTERN = re.compile(r"oakwh_[A-Za-z0-9]+_[A-Za-z0-9_\-]+")
REDACTED = "[redacted]"

_STANDARD_ATTRS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None)).keys() | {"message", "asctime"})


def redact(text: str) -> str:
    text = WEBHOOK_PATH_PATTERN.sub(rf"\g<1>{REDACTED}", text)
    return TOKEN_PATTERN.sub(REDACTED, text)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: _redact_value(v) for k, v in record.args.items()}
            else:
                record.args = tuple(_redact_value(a) for a in record.args)
        return True


def _redact_value(value: Any) -> Any:
    return redact(value) if isinstance(value, str) else value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = _redact_value(value) if isinstance(value, str) else value
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # Uvicorn's error logger goes through the same redacting handler. Its access log stays off:
    # a request line can hold a webhook token, and OAK logs requests itself, redacted.
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False
    access.disabled = True
    logging.getLogger("httpx").setLevel(logging.WARNING)
