"""Random tokens and their stored form. Plain tokens are only ever held by the client."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import string

WEBHOOK_PREFIX = "oakwh"
WEBHOOK_IDENTIFIER_LENGTH = 10
WEBHOOK_SECRET_BYTES = 32
SESSION_TOKEN_BYTES = 32
_ALPHANUMERIC = string.ascii_letters + string.digits


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_session_token() -> str:
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def csrf_token_for(secret: str, session_token: str) -> str:
    return hmac.new(secret.encode(), b"csrf:" + session_token.encode(), hashlib.sha256).hexdigest()[:40]


def new_webhook_token() -> tuple[str, str]:
    """Return ``(token, identifier)``. 256 bits of secret entropy plus a public identifier."""
    identifier = "".join(secrets.choice(_ALPHANUMERIC) for _ in range(WEBHOOK_IDENTIFIER_LENGTH))
    secret = secrets.token_urlsafe(WEBHOOK_SECRET_BYTES)
    return f"{WEBHOOK_PREFIX}_{identifier}_{secret}", identifier


def parse_webhook_token(token: str) -> str | None:
    """Return the identifier part, or ``None`` when the token is malformed."""
    parts = token.split("_", 2)
    if len(parts) != 3 or parts[0] != WEBHOOK_PREFIX or len(parts[1]) != WEBHOOK_IDENTIFIER_LENGTH:
        return None
    if not parts[1].isalnum() or not parts[2]:
        return None
    return parts[1]


def constant_time_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
