"""Downloads from outside: Game Data and the event calendar (issue #49).

A download stops at a maximum size, also when the server does not say how large it is, so a
broken or taken-over source cannot fill the memory. Redirects are followed only to https on the
same host, at most a few times. The result records the URL the content really came from.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

MAX_REDIRECTS = 5
MEGABYTE = 1024 * 1024
# The Game Master is the largest source, some tens of megabytes.
GAMEDATA_MAX_BYTES = 150 * MEGABYTE
EVENTS_MAX_BYTES = 5 * MEGABYTE
CHUNK_BYTES = 64 * 1024


class DownloadRefused(httpx.HTTPError):
    """A download OAK stopped: too large, or redirected somewhere it does not follow."""


@dataclass(frozen=True, slots=True)
class Fetched:
    url: str
    status_code: int
    headers: httpx.Headers
    content: bytes


def client(timeout: float, user_agent: str) -> httpx.Client:
    """A client that follows no redirects by itself: :func:`fetch` decides which ones to follow."""
    return httpx.Client(timeout=timeout, headers={"User-Agent": user_agent}, follow_redirects=False)


def fetch(
    http: httpx.Client,
    url: str,
    *,
    max_bytes: int,
    method: str = "GET",
    headers: dict[str, str] | None = None,
) -> Fetched:
    """GET or HEAD ``url``. Raises :class:`DownloadRefused` for a body over ``max_bytes`` or a
    redirect to another host, and ``httpx.HTTPStatusError`` for an error status."""
    current = httpx.URL(url)
    for _ in range(MAX_REDIRECTS + 1):
        with http.stream(method, current, headers=headers) as response:
            if response.status_code == httpx.codes.NOT_MODIFIED:
                return Fetched(str(response.url), response.status_code, response.headers, b"")
            if response.is_redirect:
                current = _redirect_target(current, response)
                continue
            response.raise_for_status()
            if method == "HEAD":
                return Fetched(str(response.url), response.status_code, response.headers, b"")
            declared = response.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > max_bytes:
                raise DownloadRefused(f"{current.host}: groter dan {max_bytes // MEGABYTE} MB")
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_bytes(CHUNK_BYTES):
                size += len(chunk)
                if size > max_bytes:
                    raise DownloadRefused(f"{current.host}: groter dan {max_bytes // MEGABYTE} MB")
                chunks.append(chunk)
            return Fetched(str(response.url), response.status_code, response.headers, b"".join(chunks))
    raise DownloadRefused(f"{current.host}: meer dan {MAX_REDIRECTS} doorverwijzingen")


def _redirect_target(current: httpx.URL, response: httpx.Response) -> httpx.URL:
    location = response.headers.get("location")
    if not location:
        raise DownloadRefused(f"{current.host}: doorverwijzing zonder adres")
    target = current.join(location)
    if target.scheme != "https" or target.host != current.host:
        raise DownloadRefused(f"{current.host}: doorverwijzing naar een ander adres geweigerd")
    return target
