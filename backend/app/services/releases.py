"""The newest OAK release on GitHub next to the running version (issue #29).

Only the owner sees it, and ``OAK_RELEASE_CHECK=false`` switches the request off. OAK keeps the
answer in memory for a while, so a page view does not go outside every time. GitHub not
reachable means "onbekend" with the reason, never a guess.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from app import __version__
from app.core.config import Settings
from app.core.download import MEGABYTE, client, fetch

RELEASE_URL = "https://api.github.com/repos/arjancool/oak-pogo/releases/latest"
RELEASE_PAGE = "https://github.com/arjancool/oak-pogo/releases/"
USER_AGENT = "OAK-PokemonGO-Manager (+https://github.com/arjancool/oak-pogo)"
# A failed request is asked again sooner than a good answer.
FAILURE_SECONDS = 15 * 60
# The settings page waits for the answer, so not as long as a Game Data download.
TIMEOUT_SECONDS = 10
VERSION = re.compile(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?")
Fetcher = Callable[[], dict[str, Any]]


def parse_version(value: Any) -> tuple[int, int, int] | None:
    match = VERSION.fullmatch(value.strip()) if isinstance(value, str) else None
    return (int(match[1]), int(match[2]), int(match[3])) if match else None


def _text(code: str, text: str, **data: Any) -> dict[str, Any]:
    return {"code": code, "text": text, "data": data}


def fetch_latest() -> dict[str, Any]:
    """The newest published release, from the GitHub API. Raises httpx errors."""
    with client(TIMEOUT_SECONDS, USER_AGENT) as http:
        response = fetch(http, RELEASE_URL, max_bytes=MEGABYTE, headers={"Accept": "application/vnd.github+json"})
    data = json.loads(response.content)
    if not isinstance(data, dict):
        msg = "release is no object"
        raise ValueError(msg)
    return data


def compare(current: str, release: dict[str, Any], checked_at: str) -> dict[str, Any]:
    """Compare the running version with a release from GitHub."""
    tag = release.get("tag_name")
    published = release.get("published_at")
    url = release.get("html_url")
    latest = {
        "version": tag.removeprefix("v") if isinstance(tag, str) else None,
        "published_at": published if isinstance(published, str) else None,
        # Only a link to the releases of OAK itself goes to the interface.
        "url": url if isinstance(url, str) and url.startswith(RELEASE_PAGE) else None,
    }
    result: dict[str, Any] = {"current": current, "checked_at": checked_at, "latest": latest, "reason": None}
    running, newest = parse_version(current), parse_version(tag)
    if newest is None:
        text = "GitHub gaf een release zonder leesbaar versienummer."
        return {**result, "status": "unknown", "reason": _text("RELEASE_INVALID", text)}
    if running is None:
        text = f"De draaiende versie {current} is niet te vergelijken met een release."
        return {**result, "status": "unknown", "reason": _text("VERSION_UNREADABLE", text, version=current)}
    status = "newer" if newest > running else "same" if newest == running else "ahead"
    return {**result, "status": status}


def _failure(current: str, checked_at: str, exc: Exception) -> dict[str, Any]:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == httpx.codes.NOT_FOUND:
        reason = _text("RELEASE_NONE", "Er staat nog geen release van OAK op GitHub.")
    elif isinstance(exc, httpx.HTTPStatusError):
        error = f"HTTP {exc.response.status_code}"
        reason = _text("RELEASE_UNREACHABLE", f"GitHub was niet bereikbaar: {error}", error=error)
    elif isinstance(exc, httpx.HTTPError):
        error = type(exc).__name__
        reason = _text("RELEASE_UNREACHABLE", f"GitHub was niet bereikbaar: {error}", error=error)
    else:
        reason = _text("RELEASE_INVALID", "GitHub gaf een antwoord dat OAK niet kan lezen.")
    return {"current": current, "checked_at": checked_at, "latest": None, "status": "unknown", "reason": reason}


class ReleaseCheck:
    """The answer of the last request, for ``release_check_hours`` (shorter after a failure)."""

    def __init__(self, settings: Settings, fetcher: Fetcher = fetch_latest) -> None:
        self.settings = settings
        self.fetcher = fetcher
        self._lock = threading.Lock()
        self._result: dict[str, Any] | None = None
        self._until = 0.0

    def status(self) -> dict[str, Any]:
        if not self.settings.release_check:
            return {"enabled": False, "current": __version__}
        with self._lock:
            if self._result is None or time.monotonic() >= self._until:
                checked_at = datetime.now(UTC).isoformat()
                try:
                    self._result = compare(__version__, self.fetcher(), checked_at)
                    seconds = self.settings.release_check_hours * 3600
                except Exception as exc:  # any failure is "onbekend" with the reason
                    self._result = _failure(__version__, checked_at, exc)
                    seconds = FAILURE_SECONDS
                self._until = time.monotonic() + seconds
            return {"enabled": True, **self._result}
