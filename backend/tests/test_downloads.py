"""Downloads from outside stop at a maximum size and follow redirects only on the same host
(issue #49)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.download import MAX_REDIRECTS, DownloadRefused, fetch

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def _stream(size: int) -> Iterator[bytes]:
    sent = 0
    while sent < size:
        part = min(65536, size - sent)
        sent += part
        yield b"x" * part


def test_a_download_over_the_maximum_stops() -> None:
    declared = _client(lambda _r: httpx.Response(200, headers={"content-length": "2000"}, content=b"x" * 2000))
    with pytest.raises(DownloadRefused):
        fetch(declared, "https://data.example/big.json", max_bytes=1000)
    # Without a length the counting stops it, before the whole body is in memory.
    undeclared = _client(lambda _r: httpx.Response(200, content=_stream(10_000_000)))
    with pytest.raises(DownloadRefused):
        fetch(undeclared, "https://data.example/big.json", max_bytes=100_000)


def test_a_redirect_to_another_host_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://elsewhere.example/data.json"})

    with pytest.raises(DownloadRefused, match="ander adres"):
        fetch(_client(handler), "https://data.example/data.json", max_bytes=1000)


def test_a_redirect_to_http_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(301, headers={"location": "http://data.example/data.json"})

    with pytest.raises(DownloadRefused):
        fetch(_client(handler), "https://data.example/data.json", max_bytes=1000)


def test_a_redirect_on_the_same_host_is_followed_and_recorded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old.json":
            return httpx.Response(301, headers={"location": "/new.json"})
        return httpx.Response(200, content=b'{"ok": true}', headers={"etag": "v2"})

    result = fetch(_client(handler), "https://data.example/old.json", max_bytes=1000)
    assert result.url == "https://data.example/new.json", "the URL the content really came from"
    assert result.content == b'{"ok": true}' and result.headers["etag"] == "v2"


def test_endless_redirects_stop() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": f"/{len(request.url.path)}x"})

    with pytest.raises(DownloadRefused, match=str(MAX_REDIRECTS)):
        fetch(_client(handler), "https://data.example/a", max_bytes=1000)


def test_not_modified_and_errors() -> None:
    assert fetch(_client(lambda _r: httpx.Response(304)), "https://d.example/e.json", max_bytes=10).status_code == 304
    with pytest.raises(httpx.HTTPStatusError):
        fetch(_client(lambda _r: httpx.Response(500)), "https://d.example/e.json", max_bytes=10)


@pytest.mark.parametrize("field", ["gamedata_pokeminers_url", "gamedata_pvpoke_base_url", "events_url"])
def test_source_settings_must_use_https(tmp_path: Path, field: str) -> None:
    with pytest.raises(ValidationError, match="https://"):
        Settings(data_dir=tmp_path, **{field: "http://mirror.example/data.json"})  # type: ignore[arg-type]
