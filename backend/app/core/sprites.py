"""Checking a sprite source before it goes into the Content-Security-Policy (issue #51).

The owner can choose an own sprite source, as a URL template with ``{dex}``. Its host goes into
the ``img-src`` of the CSP header on every response. A value with a semicolon, a comma, a space
or a quote could add or break directives there, so only a plain https URL with an ordinary host
name passes, and the CSP is built from the parsed host and port, never from the raw text.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

# Characters that have a meaning in a CSP header, or never belong in a URL.
_FORBIDDEN = frozenset(";, \t\r\n\"'`<>\\")
_HOST = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*")


def sprite_origin(template: str) -> str | None:
    """``https://host[:port]`` of a sprite URL template, or ``None`` when it is not safe to use."""
    if not template or "{dex}" not in template or any(c in _FORBIDDEN for c in template):
        return None
    try:
        parts = urlsplit(template)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        return None
    try:
        host = parts.hostname.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return None
    if not _HOST.fullmatch(host):
        return None
    return f"https://{host}:{port}" if port else f"https://{host}"
