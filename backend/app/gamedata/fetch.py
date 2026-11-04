"""Downloading the upstream sources. The only module in the game data layer that does I/O over
the network."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import Settings
from app.core.download import GAMEDATA_MAX_BYTES, client, fetch
from app.gamedata.cups import build_cups, ranking_downloads
from app.gamedata.transform import RANKING_FILES

log = logging.getLogger("oak.gamedata")

USER_AGENT = "OAK-PokemonGO-Manager/2.0 (+https://github.com/arjancool/oak-pogo)"


@dataclass(frozen=True, slots=True)
class Downloaded:
    id: str
    url: str
    content: bytes
    etag: str | None
    retrieved_at: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()

    def json(self) -> Any:
        return json.loads(self.content)

    def source_record(self, upstream_timestamp: str | None = None) -> dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "sha256": self.sha256,
            "etag": self.etag,
            "bytes": len(self.content),
            "retrieved_at": self.retrieved_at,
            "upstream_timestamp": upstream_timestamp,
        }


def source_urls(settings: Settings) -> dict[str, str]:
    base = settings.gamedata_pvpoke_base_url.rstrip("/")
    urls = {
        "pokeminers": settings.gamedata_pokeminers_url,
        "pvpoke": f"{base}/gamemaster.json",
    }
    for league, cap in RANKING_FILES.items():
        urls[f"pvpoke-rankings-{league}"] = f"{base}/rankings/all/overall/rankings-{cap}.json"
    return urls


def _client(settings: Settings) -> httpx.Client:
    return client(settings.gamedata_timeout_seconds, USER_AGENT)


def _download(http: httpx.Client, source_id: str, url: str) -> Downloaded:
    """At most GAMEDATA_MAX_BYTES, and the URL the content really came from (issue #49)."""
    response = fetch(http, url, max_bytes=GAMEDATA_MAX_BYTES)
    return Downloaded(
        id=source_id,
        url=response.url,
        content=response.content,
        etag=response.headers.get("etag"),
        retrieved_at=datetime.now(UTC).isoformat(),
    )


def download_all(settings: Settings) -> dict[str, Downloaded]:
    results: dict[str, Downloaded] = {}
    base = settings.gamedata_pvpoke_base_url.rstrip("/")
    with _client(settings) as http:
        for source_id, url in source_urls(settings).items():
            results[source_id] = _download(http, source_id, url)
        # The cups PvPoke shows decide which cup rankings exist (ADR-0027). A missing cup ranking
        # leaves that cup without species ranks; it does not stop the update.
        cups, _notes = build_cups(results["pvpoke"].json())
        for source_id, (cup, cp) in ranking_downloads(cups).items():
            url = f"{base}/rankings/{cup}/overall/rankings-{cp}.json"
            try:
                results[source_id] = _download(http, source_id, url)
            except httpx.HTTPError as exc:
                log.warning("cup ranking unavailable", extra={"source": source_id, "error": str(exc)[:200]})
    return results


def remote_etags(settings: Settings) -> dict[str, str | None]:
    """ETags of the two main sources, for the 'new version available' check without download."""
    urls = source_urls(settings)
    result: dict[str, str | None] = {}
    with _client(settings) as http:
        for source_id in ("pokeminers", "pvpoke"):
            response = fetch(http, urls[source_id], max_bytes=GAMEDATA_MAX_BYTES, method="HEAD")
            result[source_id] = response.headers.get("etag")
    return result
